"""Screen capture using MSS."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import mss

from omniagent_pc.models import StepResult

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MIN_SCREENSHOT_BYTES = 1024


def default_output_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "output"


def capture_screen(output_dir: Path | None = None) -> tuple[Path | None, StepResult]:
    """Capture the primary monitor and save a PNG under `output/`."""
    destination = output_dir or default_output_dir()
    try:
        destination.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = destination / f"screenshot_{stamp}.png"

        with mss.mss() as sct:
            if len(sct.monitors) < 2:
                return None, StepResult(
                    "Capture screenshot",
                    "Failed",
                    "MSS did not find a primary monitor",
                )
            sct.shot(mon=1, output=str(path))

        if not path.is_file():
            return None, StepResult(
                "Capture screenshot",
                "Failed",
                f"Screenshot file was not created: {path}",
            )

        size = path.stat().st_size
        if size < MIN_SCREENSHOT_BYTES:
            return path, StepResult(
                "Capture screenshot",
                "Failed",
                f"Screenshot is too small ({size} bytes)",
            )

        if not _is_png(path):
            return path, StepResult(
                "Capture screenshot",
                "Failed",
                "Screenshot is not a valid PNG",
            )

        return path, StepResult(
            "Capture screenshot",
            "Success",
            f"Saved {path} ({size} bytes)",
        )
    except Exception as exc:  # noqa: BLE001
        return None, StepResult("Capture screenshot", "Failed", str(exc))


def screenshot_looks_valid(path: Path) -> bool:
    return path.is_file() and path.stat().st_size >= MIN_SCREENSHOT_BYTES and _is_png(path)


def _is_png(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(8) == PNG_SIGNATURE
    except OSError:
        return False
