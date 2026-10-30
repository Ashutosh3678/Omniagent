from __future__ import annotations

import asyncio
import base64

import pytest
from fastapi.testclient import TestClient
from test_api import _register, _signup, _ws

from app import cdn as cdn_module
from app import config
from app.cdn import CdnError, Cloudinary
from app.main import app
from app.ratelimit import pairing_limiter, planner_limiter
from app.store import store

SECRET = "super-secret-value-123"
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 40
JPEG = b"\xff\xd8\xff" + b"y" * 40 + b"\xff\xd9"


def setup_function() -> None:
    store.reset()
    pairing_limiter.reset()
    planner_limiter.reset()


class FakeUploader:
    def __init__(self, fail: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self.fail = fail

    def __call__(self, file, **options):
        self.calls.append({"file": file, **options})
        if self.fail:
            raise self.fail
        return {"public_id": options["public_id"], "version": 1730000000 + len(self.calls), "format": "png"}


def make_cdn(uploader: FakeUploader | None = None) -> tuple[Cloudinary, FakeUploader]:
    uploader = uploader or FakeUploader()
    return Cloudinary("democloud", "123456789012345", SECRET, "omniagent", uploader=uploader), uploader


# --- settings
def test_settings_from_three_variables(monkeypatch) -> None:
    for name, value in {
        "OMNIAGENT_CLOUDINARY_CLOUD_NAME": "mycloud",
        "OMNIAGENT_CLOUDINARY_API_KEY": "111",
        "OMNIAGENT_CLOUDINARY_API_SECRET": "sss",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("CLOUDINARY_URL", raising=False)
    assert config._cloudinary_settings() == ("mycloud", "111", "sss")


def test_settings_from_the_standard_cloudinary_url(monkeypatch) -> None:
    for name in ("OMNIAGENT_CLOUDINARY_CLOUD_NAME", "OMNIAGENT_CLOUDINARY_API_KEY", "OMNIAGENT_CLOUDINARY_API_SECRET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CLOUDINARY_URL", "cloudinary://222:topsecret@urlcloud")
    assert config._cloudinary_settings() == ("urlcloud", "222", "topsecret")


def test_explicit_variables_win_over_the_url(monkeypatch) -> None:
    monkeypatch.setenv("OMNIAGENT_CLOUDINARY_API_SECRET", "explicit")
    monkeypatch.delenv("OMNIAGENT_CLOUDINARY_CLOUD_NAME", raising=False)
    monkeypatch.delenv("OMNIAGENT_CLOUDINARY_API_KEY", raising=False)
    monkeypatch.setenv("CLOUDINARY_URL", "cloudinary://222:fromurl@urlcloud")
    assert config._cloudinary_settings() == ("urlcloud", "222", "explicit")


def test_no_settings_means_no_cdn(monkeypatch) -> None:
    monkeypatch.setattr(cdn_module, "CLOUDINARY_API_SECRET", "")
    assert cdn_module.get_cdn() is None


def test_complete_settings_give_a_cdn(monkeypatch) -> None:
    monkeypatch.setattr(cdn_module, "CLOUDINARY_CLOUD_NAME", "c")
    monkeypatch.setattr(cdn_module, "CLOUDINARY_API_KEY", "k")
    monkeypatch.setattr(cdn_module, "CLOUDINARY_API_SECRET", "s")
    assert cdn_module.get_cdn() is not None


# --- signed addresses
def test_urls_are_signed_authenticated_https_cdn_addresses() -> None:
    cdn, _ = make_cdn()
    url = cdn.url("v1730000001/omniagent/u1/t1/final.png", max_width=1080)
    assert url.startswith("https://res.cloudinary.com/democloud/image/authenticated/s--")
    assert "/c_limit,q_auto,w_1080/" in url and url.endswith("/v1730000001/omniagent/u1/t1/final.png")
    assert SECRET not in url and "123456789012345" not in url


def test_a_url_cannot_be_forged_without_the_secret() -> None:
    cdn, _ = make_cdn()
    other = Cloudinary("democloud", "123456789012345", "a-different-secret", uploader=FakeUploader())
    ref = "v1730000001/omniagent/u1/t1/final.png"
    assert cdn.url(ref) != other.url(ref)
    assert cdn.url(ref) == cdn.url(ref)  # stable, so the app's image cache works
    assert cdn.url(ref) != cdn.url("v1730000001/omniagent/u1/OTHER/final.png")


@pytest.mark.parametrize("ref", ["", "garbage", "omniagent/x/final.png", "v1/x/final.gif"])
def test_unknown_references_give_no_url(ref: str) -> None:
    cdn, _ = make_cdn()
    assert cdn.url(ref) is None


# --- uploads
def test_upload_is_private_overwritable_and_namespaced() -> None:
    cdn, uploader = make_cdn()
    ref = asyncio.run(cdn.upload(PNG, "image/png", "user-1", "task-1", "final"))
    call = uploader.calls[0]
    assert call["type"] == "authenticated" and call["public_id"] == "omniagent/user-1/task-1/final"
    assert call["overwrite"] is True and call["api_secret"] == SECRET
    assert call["file"].startswith("data:image/png;base64,") and base64.b64decode(call["file"].split(",", 1)[1]) == PNG
    assert ref == "v1730000001/omniagent/user-1/task-1/final.png"


def test_jpeg_uploads_keep_their_extension() -> None:
    cdn, _ = make_cdn()
    assert asyncio.run(cdn.upload(JPEG, "image/jpeg", "u", "t", "step-0")).endswith("/step-0.jpg")


def test_only_png_and_jpeg_are_uploaded() -> None:
    cdn, uploader = make_cdn()
    with pytest.raises(CdnError):
        asyncio.run(cdn.upload(b"<svg/>", "image/svg+xml", "u", "t", "final"))
    assert uploader.calls == []


def test_upload_failures_become_cdn_errors_that_do_not_leak_the_secret() -> None:
    cdn, _ = make_cdn(FakeUploader(fail=RuntimeError(f"bad signature for secret {SECRET}")))
    with pytest.raises(CdnError) as info:
        asyncio.run(cdn.upload(PNG, "image/png", "u", "t", "final"))
    assert SECRET not in str(info.value)


def test_a_malformed_response_is_an_error() -> None:
    cdn = Cloudinary("c", "k", "s", uploader=lambda file, **o: {"oops": True})
    with pytest.raises(CdnError):
        asyncio.run(cdn.upload(PNG, "image/png", "u", "t", "final"))


# --- through the whole backend
@pytest.fixture
def cdn_on(monkeypatch):
    cdn, uploader = make_cdn()
    monkeypatch.setattr(cdn_module, "get_cdn", lambda: cdn)
    return cdn, uploader


def run_one_task(client: TestClient, user: dict, ws, step_image: bytes | None, final_image: bytes | None):
    task = client.post("/api/v1/tasks", headers=user, json={"instruction": "open notepad"}).json()
    tid = ws.receive_json()["task_id"]
    step: dict = {"type": "step", "task_id": tid, "index": 0, "status": "success"}
    if step_image is not None:
        step["screenshot_b64"] = base64.b64encode(step_image).decode()
    ws.send_json(step)
    result: dict = {"type": "result", "task_id": tid, "status": "completed"}
    if final_image is not None:
        result["screenshot_b64"] = base64.b64encode(final_image).decode()
    ws.send_json(result)
    return task["id"]


def test_screenshots_go_to_the_cdn_not_the_database(cdn_on) -> None:
    cdn, uploader = cdn_on
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            tid = run_one_task(client, user, ws, JPEG, PNG)
            task = client.get(f"/api/v1/tasks/{tid}", headers=user).json()

            assert task["screenshot_url"].startswith("https://res.cloudinary.com/democloud/image/authenticated/s--")
            assert "w_1080" in task["screenshot_url"] and task["screenshot_url"].endswith("/final.png")
            assert task["steps"][0]["has_screenshot"] is True
            assert task["steps"][0]["screenshot_url"].endswith("/step-0.jpg")
            assert "screenshot_ref" in task["steps"][0]  # the owner may see where it lives; never a secret
            assert store.get_screenshot(tid) is None and store.get_step_screenshot(tid, 0) is None
        assert [c["public_id"].rsplit("/", 1)[1] for c in uploader.calls] == ["step-0", "final"]
        assert SECRET not in str(task)


def test_the_old_endpoints_redirect_to_the_cdn_for_the_owner_only(cdn_on) -> None:
    with TestClient(app) as client:
        alice = _signup(client, "alice@example.com")
        bob = _signup(client, "bob@example.com")
        agent_id, device = _register(client, alice)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            tid = run_one_task(client, alice, ws, JPEG, PNG)

        final = client.get(f"/api/v1/tasks/{tid}/screenshot", headers=alice, follow_redirects=False)
        assert final.status_code == 307 and final.headers["location"].startswith("https://res.cloudinary.com/")
        step = client.get(f"/api/v1/tasks/{tid}/steps/0/screenshot", headers=alice, follow_redirects=False)
        assert step.status_code == 307 and step.headers["location"].endswith("/step-0.jpg")

        assert client.get(f"/api/v1/tasks/{tid}/screenshot", headers=bob, follow_redirects=False).status_code == 404
        assert client.get(f"/api/v1/tasks/{tid}/steps/0/screenshot", headers=bob, follow_redirects=False).status_code == 404
        assert client.get(f"/api/v1/tasks/{tid}/screenshot", follow_redirects=False).status_code == 401


def test_the_cdn_address_is_pushed_to_the_phone(cdn_on) -> None:
    from test_events import authed, listen

    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as pc, listen(client, user) as events:
            pc.receive_json()
            authed(events, user)
            client.post("/api/v1/tasks", headers=user, json={"instruction": "open notepad"})
            events.receive_json(), events.receive_json()
            tid = pc.receive_json()["task_id"]
            pc.send_json({"type": "step", "task_id": tid, "index": 0, "status": "success", "screenshot_b64": base64.b64encode(JPEG).decode()})
            pushed = events.receive_json()["task"]["steps"][0]
            assert pushed["screenshot_url"].startswith("https://res.cloudinary.com/democloud/")


def test_a_failed_upload_falls_back_to_the_database(monkeypatch) -> None:
    cdn, _ = make_cdn(FakeUploader(fail=RuntimeError("quota exceeded")))
    monkeypatch.setattr(cdn_module, "get_cdn", lambda: cdn)
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            tid = run_one_task(client, user, ws, JPEG, PNG)
            task = client.get(f"/api/v1/tasks/{tid}", headers=user).json()
            assert task["status"] == "completed"
            assert task["screenshot_url"] == f"/api/v1/tasks/{tid}/screenshot"
            assert task["steps"][0]["screenshot_url"] == f"/api/v1/tasks/{tid}/steps/0/screenshot"
            assert client.get(task["screenshot_url"], headers=user).content == PNG
            assert client.get(task["steps"][0]["screenshot_url"], headers=user).content == JPEG
            assert any("CDN upload failed" in log["message"] for log in task["logs"])


def test_without_a_cdn_nothing_changes(monkeypatch) -> None:
    monkeypatch.setattr(cdn_module, "get_cdn", lambda: None)
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            tid = run_one_task(client, user, ws, JPEG, PNG)
            task = client.get(f"/api/v1/tasks/{tid}", headers=user).json()
            assert task["screenshot_url"] == f"/api/v1/tasks/{tid}/screenshot"
            assert client.get(task["screenshot_url"], headers=user).content == PNG


def test_unrecognised_image_bytes_stay_in_the_database(cdn_on) -> None:
    _, uploader = cdn_on
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            tid = run_one_task(client, user, ws, None, b"<html>not an image</html>")
        assert uploader.calls == []
        assert store.get_screenshot(tid) == b"<html>not an image</html>"


def test_oversized_or_broken_final_screenshots_are_rejected(cdn_on) -> None:
    from app.ws import MAX_FINAL_SCREENSHOT_BYTES

    _, uploader = cdn_on
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            tid = run_one_task(client, user, ws, None, b"\x89PNG" + b"z" * (MAX_FINAL_SCREENSHOT_BYTES + 1))
            task = client.get(f"/api/v1/tasks/{tid}", headers=user).json()
            assert task["status"] == "completed" and task["screenshot_url"] is None
            assert any("invalid" in log["message"] for log in task["logs"])
        assert uploader.calls == []


def test_the_cdn_address_changes_only_with_the_image(cdn_on) -> None:
    """Same task, same image: the phone sees the same address, so its cache is reused."""
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            tid = run_one_task(client, user, ws, JPEG, PNG)
        first = client.get(f"/api/v1/tasks/{tid}", headers=user).json()["screenshot_url"]
        second = client.get(f"/api/v1/tasks/{tid}", headers=user).json()["screenshot_url"]
        assert first == second
