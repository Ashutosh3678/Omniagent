"""Screenshot storage on Cloudinary, delivered through its CDN.

Images are uploaded by the backend (the API secret never reaches a PC or a phone) as
*authenticated* assets: they cannot be fetched from a plain URL, only from a URL signed
with the API secret. The backend signs URLs only for the task's owner, so a desktop
screenshot is never publicly guessable, yet the phone loads it straight from the CDN.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from typing import Any, Callable

from app.config import CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET, CLOUDINARY_CLOUD_NAME, CLOUDINARY_FOLDER

logger = logging.getLogger(__name__)

UPLOAD_TIMEOUT_SECONDS = 8.0
_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png"}
_REF = re.compile(r"^v(\d+)/(.+)\.(jpg|png)$")


class CdnError(Exception):
    """The image could not be stored on the CDN."""


class Cloudinary:
    name = "cloudinary"

    def __init__(
        self,
        cloud_name: str,
        api_key: str,
        api_secret: str,
        folder: str = "omniagent",
        uploader: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self._credentials = {"cloud_name": cloud_name, "api_key": api_key, "api_secret": api_secret}
        self._folder = folder.strip("/")
        self._uploader = uploader

    def public_id(self, user_id: str, task_id: str, name: str) -> str:
        return f"{self._folder}/{user_id}/{task_id}/{name}"

    async def upload(self, data: bytes, content_type: str, user_id: str, task_id: str, name: str) -> str:
        """Stores the image and returns a reference to keep with the task (see `url`)."""
        extension = _EXTENSIONS.get(content_type)
        if extension is None:
            raise CdnError(f"Unsupported image type {content_type!r}")
        public_id = self.public_id(user_id, task_id, name)
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._upload_sync, data, content_type, public_id),
                UPLOAD_TIMEOUT_SECONDS + 2,
            )
        except Exception as exc:  # noqa: BLE001 - network, quota, bad credentials: all mean "use the database instead"
            logger.warning("Cloudinary upload failed: %s", type(exc).__name__)
            raise CdnError("Upload failed") from exc
        return f"v{result['version']}/{result['public_id']}.{extension}"

    def _upload_sync(self, data: bytes, content_type: str, public_id: str) -> dict[str, Any]:
        upload = self._uploader
        if upload is None:
            import cloudinary.uploader

            upload = cloudinary.uploader.upload
        encoded = base64.b64encode(data).decode()
        result = upload(
            f"data:{content_type};base64,{encoded}",
            public_id=public_id,
            type="authenticated",
            resource_type="image",
            overwrite=True,
            invalidate=True,
            timeout=UPLOAD_TIMEOUT_SECONDS,
            **self._credentials,
        )
        if not isinstance(result, dict) or "version" not in result or "public_id" not in result:
            raise CdnError("Unexpected response from Cloudinary")
        return result

    def url(self, ref: str, max_width: int | None = None) -> str | None:
        """A signed https CDN address for a stored image, or None if the reference is not one of ours."""
        match = _REF.match(ref or "")
        if match is None:
            return None
        version, public_id, extension = match.groups()
        import cloudinary.utils

        transformation = {"quality": "auto"}
        if max_width:
            transformation.update(width=max_width, crop="limit")
        url, _ = cloudinary.utils.cloudinary_url(
            public_id,
            type="authenticated",
            resource_type="image",
            format=extension,
            version=int(version),
            sign_url=True,
            secure=True,
            transformation=[transformation],
            **self._credentials,
        )
        return url


def get_cdn() -> Cloudinary | None:
    """The CDN, or None when Cloudinary is not configured (screenshots then stay in the database)."""
    if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
        return Cloudinary(CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET, CLOUDINARY_FOLDER)
    return None
