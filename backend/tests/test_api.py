from __future__ import annotations

import base64
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.models import utcnow
from app.ratelimit import pairing_limiter, planner_limiter
from app.store import store


def setup_function() -> None:
    store.reset()
    pairing_limiter.reset()
    planner_limiter.reset()


def _signup(client: TestClient, email: str = "alex@example.com", password: str = "correct-horse") -> dict:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _pairing_code(client: TestClient, user: dict) -> str:
    response = client.post("/api/v1/agents/pairing-code", headers=user)
    assert response.status_code == 201, response.text
    return response.json()["code"]


def _register(client: TestClient, user: dict) -> tuple[str, dict]:
    response = client.post(
        "/api/v1/agents/pair",
        json={"code": _pairing_code(client, user), "name": "Office PC", "hostname": "DESKTOP-7K2M"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return body["id"], {"Authorization": f"Bearer {body['device_token']}"}


def _ws(client: TestClient, agent_id: str, device: dict):
    return client.websocket_connect(f"/api/v1/agents/{agent_id}/ws", headers=device)


def test_health() -> None:
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"


# accounts
def test_register_login_and_me() -> None:
    with TestClient(app) as client:
        user = _signup(client, "Alex@Example.com")
        me = client.get("/api/v1/auth/me", headers=user)
        assert me.status_code == 200
        assert me.json()["email"] == "alex@example.com"

        login = client.post(
            "/api/v1/auth/login", json={"email": "ALEX@example.com", "password": "correct-horse"}
        )
        assert login.status_code == 200
        assert login.json()["token_type"] == "bearer"

        form = client.post("/api/v1/auth/token", data={"username": "alex@example.com", "password": "correct-horse"})
        assert form.status_code == 200


def test_duplicate_email_rejected() -> None:
    with TestClient(app) as client:
        _signup(client)
        again = client.post(
            "/api/v1/auth/register", json={"email": "alex@example.com", "password": "another-pass"}
        )
        assert again.status_code == 409


def test_weak_input_rejected() -> None:
    with TestClient(app) as client:
        assert client.post("/api/v1/auth/register", json={"email": "nope", "password": "longenough"}).status_code == 422
        assert client.post("/api/v1/auth/register", json={"email": "a@b.co", "password": "short"}).status_code == 422


def test_wrong_password_and_unknown_email_look_the_same() -> None:
    with TestClient(app) as client:
        _signup(client)
        wrong = client.post("/api/v1/auth/login", json={"email": "alex@example.com", "password": "bad-password"})
        unknown = client.post("/api/v1/auth/login", json={"email": "who@example.com", "password": "bad-password"})
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json() == unknown.json()


def test_password_is_stored_hashed() -> None:
    with TestClient(app) as client:
        _signup(client)
        user = store.get_user_by_email("alex@example.com")
        assert user is not None
        assert user.password_hash.startswith("$argon2")
        assert "correct-horse" not in user.password_hash


def test_missing_or_bad_token_rejected() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/agents").status_code == 401
        assert client.post("/api/v1/agents/pairing-code").status_code == 401
        assert client.get("/api/v1/audit").status_code == 401
        assert client.get("/api/v1/agents", headers={"Authorization": "Bearer garbage"}).status_code == 401
        assert client.get("/api/v1/tasks").status_code == 401


def test_expired_token_rejected(monkeypatch) -> None:
    from app import auth

    with TestClient(app) as client:
        user = _signup(client)
        monkeypatch.setattr(auth, "JWT_EXPIRE_MINUTES", -1)
        stale = auth.create_access_token(store.get_user_by_email("alex@example.com").id)
        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {stale}"})
        assert response.status_code == 401
        assert client.get("/api/v1/auth/me", headers=user).status_code == 200


# tasks
def test_reject_invalid_instruction() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            response = client.post("/api/v1/tasks", headers=user, json={"instruction": "run calc.exe"})
            assert response.status_code == 400


def test_disconnected_agent_rejected() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, _ = _register(client, user)
        create = client.post(
            "/api/v1/tasks",
            headers=user,
            json={"instruction": "Open Notepad and type Hello from OmniAgent", "agent_id": agent_id},
        )
        assert create.status_code == 503


def test_task_roundtrip_with_connected_agent() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            assert ws.receive_json()["type"] == "hello_ok"

            create = client.post(
                "/api/v1/tasks",
                headers=user,
                json={"instruction": "Open Notepad and type Hello from OmniAgent"},
            )
            assert create.status_code == 201
            assert create.json()["status"] == "running"

            inbound = ws.receive_json()
            assert inbound["type"] == "task"
            assert inbound["plan"] == [
                {"index": 0, "action": {"type": "open_app", "app": "notepad"}},
                {"index": 1, "action": {"type": "type_text", "text": "Hello from OmniAgent"}},
            ]
            assert [st["status"] for st in create.json()["steps"]] == ["pending", "pending"]
            assert create.json()["confidence"] == 1.0

            ws.send_json({"type": "ack", "task_id": inbound["task_id"]})
            ws.send_json({"type": "step", "task_id": inbound["task_id"], "index": 0, "status": "running"})
            ws.send_json({"type": "step", "task_id": inbound["task_id"], "index": 0, "status": "success", "detail": "ok"})
            mid = client.get(f"/api/v1/tasks/{inbound['task_id']}", headers=user).json()
            assert [st["status"] for st in mid["steps"]] == ["success", "pending"]
            assert mid["steps"][0]["detail"] == "ok"
            ws.send_json({"type": "step", "task_id": inbound["task_id"], "index": 1, "status": "success"})

            png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 32).decode()
            ws.send_json(
                {
                    "type": "result",
                    "task_id": inbound["task_id"],
                    "status": "completed",
                    "summary": "Opened Notepad",
                    "screenshot_b64": png,
                }
            )

            fetched = client.get(f"/api/v1/tasks/{inbound['task_id']}", headers=user).json()
            assert fetched["status"] == "completed"
            assert [st["status"] for st in fetched["steps"]] == ["success", "success"]
            shot = client.get(fetched["screenshot_url"], headers=user)
            assert shot.status_code == 200
            assert shot.headers["content-type"] == "image/png"


def test_agent_disconnect_fails_running_task() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            task_id = client.post(
                "/api/v1/tasks", headers=user, json={"instruction": "open notepad"}
            ).json()["id"]
            ws.receive_json()
        fetched = client.get(f"/api/v1/tasks/{task_id}", headers=user).json()
        assert fetched["status"] == "failed"
        assert fetched["error"] == "Agent disconnected"


def test_failed_result_from_agent() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            create = client.post("/api/v1/tasks", headers=user, json={"instruction": "open notepad"})
            inbound = ws.receive_json()
            ws.send_json(
                {
                    "type": "result",
                    "task_id": inbound["task_id"],
                    "status": "failed",
                    "error": "Could not open Notepad",
                }
            )
            fetched = client.get(f"/api/v1/tasks/{create.json()['id']}", headers=user).json()
            assert fetched["status"] == "failed"
            assert fetched["error"] == "Could not open Notepad"


def test_restart_marks_agents_offline_and_fails_running_tasks() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            task_id = client.post(
                "/api/v1/tasks", headers=user, json={"instruction": "open notepad"}
            ).json()["id"]
            ws.receive_json()
            store.mark_all_offline()  # what the lifespan hook does on boot
            fetched = client.get(f"/api/v1/tasks/{task_id}", headers=user).json()
            assert fetched["status"] == "failed"
            assert fetched["error"] == "Backend restarted"
            assert client.get("/api/v1/agents", headers=user).json()[0]["online"] is False


# isolation between users
def test_users_cannot_see_each_others_data() -> None:
    with TestClient(app) as client:
        alice = _signup(client, "alice@example.com")
        bob = _signup(client, "bob@example.com")
        agent_id, device = _register(client, alice)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            task = client.post("/api/v1/tasks", headers=alice, json={"instruction": "open notepad"}).json()
            inbound = ws.receive_json()
            png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 8).decode()
            ws.send_json(
                {"type": "result", "task_id": inbound["task_id"], "status": "completed", "screenshot_b64": png}
            )

            assert client.get("/api/v1/agents", headers=bob).json() == []
            assert client.get("/api/v1/tasks", headers=bob).json() == []
            assert client.get(f"/api/v1/tasks/{task['id']}", headers=bob).status_code == 404
            assert client.get(f"/api/v1/tasks/{task['id']}/screenshot", headers=bob).status_code == 404
            assert client.post(f"/api/v1/tasks/{task['id']}/cancel", headers=bob).status_code == 404

            # Bob cannot dispatch to Alice's PC, even by guessing its id.
            hijack = client.post(
                "/api/v1/tasks", headers=bob, json={"instruction": "open notepad", "agent_id": agent_id}
            )
            assert hijack.status_code == 404

            assert client.get(f"/api/v1/tasks/{task['id']}", headers=alice).status_code == 200


# device tokens
def test_websocket_rejects_wrong_or_user_token() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        for headers in ({}, {"Authorization": "Bearer nope"}, user):
            with pytest.raises(WebSocketDisconnect):
                with _ws(client, agent_id, headers):
                    pass


def test_device_token_only_works_for_its_own_agent() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        first_id, _ = _register(client, user)
        _, second_device = _register(client, user)
        with pytest.raises(WebSocketDisconnect):
            with _ws(client, first_id, second_device):
                pass


def test_device_token_is_stored_hashed() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        stored = store.get_agent_token_hash(agent_id)
        assert stored and stored not in device["Authorization"]


# pairing
def test_pairing_code_is_single_use() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        code = _pairing_code(client, user)
        first = client.post("/api/v1/agents/pair", json={"code": code})
        assert first.status_code == 200
        again = client.post("/api/v1/agents/pair", json={"code": code})
        assert again.status_code == 400
        assert len(client.get("/api/v1/agents", headers=user).json()) == 1


def test_pairing_code_accepts_sloppy_typing_but_not_wrong_codes() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        code = _pairing_code(client, user)
        assert client.post("/api/v1/agents/pair", json={"code": "ZZZZ-ZZZZ"}).status_code == 400
        sloppy = code.lower().replace("-", " ")
        assert client.post("/api/v1/agents/pair", json={"code": sloppy}).status_code == 200


def test_pairing_code_expires() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        code = _pairing_code(client, user)
        from sqlalchemy import update

        from app.db import session_scope
        from app.orm import PairingCodeRow

        with session_scope() as db:
            db.execute(update(PairingCodeRow).values(expires_at=utcnow() - timedelta(seconds=1)))
        assert client.post("/api/v1/agents/pair", json={"code": code}).status_code == 400


def test_pairing_binds_device_to_the_code_owner() -> None:
    with TestClient(app) as client:
        alice = _signup(client, "alice@example.com")
        bob = _signup(client, "bob@example.com")
        _register(client, alice)
        assert len(client.get("/api/v1/agents", headers=alice).json()) == 1
        assert client.get("/api/v1/agents", headers=bob).json() == []


def test_pairing_is_rate_limited() -> None:
    with TestClient(app) as client:
        for _ in range(8):
            assert client.post("/api/v1/agents/pair", json={"code": "BADCODE1"}).status_code == 400
        blocked = client.post("/api/v1/agents/pair", json={"code": "BADCODE1"})
        assert blocked.status_code == 429


def test_old_open_registration_is_gone() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        response = client.post("/api/v1/agents/register", headers=user, json={"name": "x"})
        assert response.status_code in (404, 405)


# scope, expiry, revocation
def _connected(client: TestClient, user: dict):
    agent_id, device = _register(client, user)
    return agent_id, _ws(client, agent_id, device)


def test_new_device_defaults_to_notepad_only() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        _register(client, user)
        agent = client.get("/api/v1/agents", headers=user).json()[0]
        assert agent["status"] == "active"
        assert agent["permitted_apps"] == ["notepad"]


def test_dispatch_denied_when_app_not_permitted() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, ctx = _connected(client, user)
        with ctx as ws:
            ws.receive_json()
            patch = client.patch(f"/api/v1/agents/{agent_id}", headers=user, json={"permitted_apps": []})
            assert patch.status_code == 200
            response = client.post("/api/v1/tasks", headers=user, json={"instruction": "open notepad"})
            assert response.status_code == 403
            events = client.get("/api/v1/audit", headers=user).json()
            assert events[0]["decision"] == "deny"
            assert events[0]["reason"] == "app_not_permitted"
            assert client.get("/api/v1/tasks", headers=user).json() == []


def test_patch_rejects_unknown_apps_and_past_expiry() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, _ = _register(client, user)
        url = f"/api/v1/agents/{agent_id}"
        assert client.patch(url, headers=user, json={"permitted_apps": ["chrome"]}).status_code == 422
        past = (utcnow() - timedelta(hours=1)).isoformat()
        assert client.patch(url, headers=user, json={"expires_at": past}).status_code == 422


def test_dispatch_denied_when_device_expired() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, ctx = _connected(client, user)
        with ctx as ws:
            ws.receive_json()
            soon = (utcnow() + timedelta(hours=1)).isoformat()
            assert client.patch(f"/api/v1/agents/{agent_id}", headers=user, json={"expires_at": soon}).status_code == 200
            assert client.post("/api/v1/tasks", headers=user, json={"instruction": "open notepad"}).status_code == 201
            ws.receive_json()

            agent = store.get_agent(agent_id)
            agent.expires_at = utcnow() - timedelta(seconds=1)
            store.update_agent(agent)
            denied = client.post("/api/v1/tasks", headers=user, json={"instruction": "open notepad"})
            assert denied.status_code == 403
            assert client.get("/api/v1/audit", headers=user).json()[0]["reason"] == "device_expired"


def test_revoke_drops_connection_fails_tasks_and_blocks_reconnect() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            task_id = client.post("/api/v1/tasks", headers=user, json={"instruction": "open notepad"}).json()["id"]
            ws.receive_json()

            revoked = client.post(f"/api/v1/agents/{agent_id}/revoke", headers=user)
            assert revoked.status_code == 200
            assert revoked.json()["status"] == "revoked"
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()

        task = client.get(f"/api/v1/tasks/{task_id}", headers=user).json()
        assert task["status"] == "failed"
        assert task["error"] == "PC was removed"

        with pytest.raises(WebSocketDisconnect):
            with _ws(client, agent_id, device):
                pass
        denied = client.post(
            "/api/v1/tasks", headers=user, json={"instruction": "open notepad", "agent_id": agent_id}
        )
        assert denied.status_code == 403
        reasons = [e["reason"] for e in client.get("/api/v1/audit", headers=user).json()]
        assert "device_revoked" in reasons


def test_other_users_cannot_revoke_or_edit_a_device() -> None:
    with TestClient(app) as client:
        alice = _signup(client, "alice@example.com")
        bob = _signup(client, "bob@example.com")
        agent_id, _ = _register(client, alice)
        assert client.post(f"/api/v1/agents/{agent_id}/revoke", headers=bob).status_code == 404
        assert client.patch(f"/api/v1/agents/{agent_id}", headers=bob, json={"name": "mine"}).status_code == 404
        assert client.get("/api/v1/agents", headers=alice).json()[0]["status"] == "active"


# audit trail
def test_every_dispatch_decision_is_audited() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, ctx = _connected(client, user)
        client.post("/api/v1/tasks", headers=user, json={"instruction": "open notepad", "agent_id": agent_id})  # offline
        with ctx as ws:
            ws.receive_json()
            client.post("/api/v1/tasks", headers=user, json={"instruction": "format c:"})  # invalid
            ok = client.post("/api/v1/tasks", headers=user, json={"instruction": "open notepad"})  # permitted
            ws.receive_json()
        events = client.get("/api/v1/audit", headers=user).json()
        outcomes = [(e["event"], e["decision"], e["reason"]) for e in events if e["event"].startswith("dispatch")]
        assert ("dispatch_permitted", "permit", "1 step(s) via rules") in outcomes
        assert ("dispatch_denied", "deny", "invalid_instruction") in outcomes
        assert ("dispatch_denied", "deny", "device_offline") in outcomes
        permitted = next(e for e in events if e["event"] == "dispatch_permitted")
        assert permitted["task_id"] == ok.json()["id"]


def test_audit_is_private_to_each_user() -> None:
    with TestClient(app) as client:
        alice = _signup(client, "alice@example.com")
        bob = _signup(client, "bob@example.com")
        _register(client, alice)
        assert client.get("/api/v1/audit", headers=alice).json()
        assert client.get("/api/v1/audit", headers=bob).json() == []


# plans
def test_result_overwrite_is_ignored_after_task_finished() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            task = client.post("/api/v1/tasks", headers=user, json={"instruction": "open notepad"}).json()
            inbound = ws.receive_json()
            client.post(f"/api/v1/tasks/{task['id']}/cancel", headers=user)
            ws.send_json({"type": "result", "task_id": inbound["task_id"], "status": "completed"})
            ws.send_json({"type": "step", "task_id": inbound["task_id"], "index": 0, "status": "success"})
            fetched = client.get(f"/api/v1/tasks/{task['id']}", headers=user).json()
            assert fetched["status"] == "failed"
            assert fetched["error"] == "Cancelled"


def test_agent_reported_partial_and_unfinished_steps_are_skipped() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            task = client.post(
                "/api/v1/tasks", headers=user, json={"instruction": "open notepad and type hi"}
            ).json()
            inbound = ws.receive_json()
            ws.send_json({"type": "step", "task_id": inbound["task_id"], "index": 0, "status": "success"})
            ws.send_json({"type": "step", "task_id": inbound["task_id"], "index": 1, "status": "failed", "detail": "no focus"})
            ws.send_json({"type": "result", "task_id": inbound["task_id"], "status": "partial", "summary": "Stopped at step 2"})
            fetched = client.get(f"/api/v1/tasks/{task['id']}", headers=user).json()
            assert fetched["status"] == "partial"
            assert [st["status"] for st in fetched["steps"]] == ["success", "failed"]


def test_step_updates_with_bad_index_or_status_are_ignored() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            task = client.post("/api/v1/tasks", headers=user, json={"instruction": "open notepad"}).json()
            inbound = ws.receive_json()
            for bad in ({"index": 5, "status": "success"}, {"index": -1, "status": "success"}, {"index": 0, "status": "held_back"}, {"index": "0", "status": "success"}):
                ws.send_json({"type": "step", "task_id": inbound["task_id"], **bad})
            fetched = client.get(f"/api/v1/tasks/{task['id']}", headers=user).json()
            assert [st["status"] for st in fetched["steps"]] == ["pending"]


def test_agent_cannot_update_another_agents_task() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        first_id, first_device = _register(client, user)
        second_id, second_device = _register(client, user)
        with _ws(client, first_id, first_device) as ws1, _ws(client, second_id, second_device) as ws2:
            ws1.receive_json()
            ws2.receive_json()
            task = client.post(
                "/api/v1/tasks", headers=user, json={"instruction": "open notepad", "agent_id": first_id}
            ).json()
            inbound = ws1.receive_json()
            ws2.send_json({"type": "result", "task_id": inbound["task_id"], "status": "completed"})
            ws2.send_json({"type": "step", "task_id": inbound["task_id"], "index": 0, "status": "success"})
            fetched = client.get(f"/api/v1/tasks/{task['id']}", headers=user).json()
            assert fetched["status"] == "running"
            assert fetched["steps"][0]["status"] == "pending"


def test_held_back_steps_are_audited_and_result_is_partial() -> None:
    plan = [
        {"action": {"type": "open_app", "app": "notepad"}, "confidence": 0.9},
        {"action": {"type": "click", "target": "Save"}, "confidence": 0.4},
        {"action": {"type": "type_text", "text": "later"}},
    ]
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            created = client.post("/api/v1/tasks", headers=user, json={"instruction": "anything", "plan": plan})
            assert created.status_code == 201
            body = created.json()
            assert [st["status"] for st in body["steps"]] == ["pending", "held_back", "held_back"]
            assert [h["reason"] for h in body["held_back"]] == ["not_supported", "blocked_by_earlier_step"]
            assert body["confidence"] == 0.9

            inbound = ws.receive_json()
            assert [s["action"]["type"] for s in inbound["plan"]] == ["open_app"]
            ws.send_json({"type": "step", "task_id": inbound["task_id"], "index": 0, "status": "success"})
            ws.send_json({"type": "result", "task_id": inbound["task_id"], "status": "completed"})
            fetched = client.get(f"/api/v1/tasks/{body['id']}", headers=user).json()
            assert fetched["status"] == "partial"
            assert [st["status"] for st in fetched["steps"]] == ["success", "held_back", "held_back"]

        events = client.get("/api/v1/audit", headers=user).json()
        held = [e["reason"] for e in events if e["event"] == "plan_step_held_back"]
        assert sorted(held) == ["step 2: not_supported", "step 3: blocked_by_earlier_step"]


def test_plan_with_nothing_runnable_is_refused_and_creates_no_task() -> None:
    plan = [{"action": {"type": "click", "target": "Save"}}]
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            response = client.post("/api/v1/tasks", headers=user, json={"instruction": "anything", "plan": plan})
            assert response.status_code == 422
            assert client.get("/api/v1/tasks", headers=user).json() == []
            events = client.get("/api/v1/audit", headers=user).json()
            assert events[0]["event"] == "dispatch_denied" and events[0]["reason"] == "not_supported"


# planner integration (the LLM is always faked here)
class FakePlanner:
    name = "groq"

    def __init__(self, steps=None, note="", error: Exception | None = None) -> None:
        self.steps = steps or []
        self.note = note
        self.error = error
        self.calls: list[tuple[str, list[str]]] = []

    async def plan(self, instruction: str, permitted_apps: list[str]):
        from app.planner import PlannerResult

        self.calls.append((instruction, list(permitted_apps)))
        if self.error:
            raise self.error
        return PlannerResult(steps=self.steps, planner="groq", note=self.note)


def _use(monkeypatch, fake: FakePlanner | None) -> None:
    monkeypatch.setattr("app.planner.get_planner", lambda: fake)


COMPOSE = [
    {"action": {"type": "open_app", "app": "notepad"}, "confidence": 0.95},
    {"action": {"type": "type_text", "text": "Dear team"}, "confidence": 0.9},
    {"action": {"type": "press_key", "key": "enter"}, "confidence": 0.8},
    {"action": {"type": "type_text", "text": "Thanks"}, "confidence": 0.9},
]


def test_llm_plan_runs_as_a_multi_step_task(monkeypatch) -> None:
    fake = FakePlanner(COMPOSE)
    _use(monkeypatch, fake)
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            created = client.post(
                "/api/v1/tasks", headers=user, json={"instruction": "write a short thank-you note in notepad"}
            )
            assert created.status_code == 201, created.text
            assert [s["name"] for s in created.json()["steps"]][:2] == ["Open Notepad", "Type \u201cDear team\u201d"]
            inbound = ws.receive_json()
            assert [s["action"]["type"] for s in inbound["plan"]] == ["open_app", "type_text", "press_key", "type_text"]
            assert fake.calls == [("write a short thank-you note in notepad", ["notepad"])]
            assert created.json()["confidence"] == pytest.approx(0.89, abs=0.01)
        reasons = [(e["event"], e["reason"]) for e in client.get("/api/v1/audit", headers=user).json()]
        assert ("plan_created", "groq: 4 step(s)") in reasons
        assert ("dispatch_permitted", "4 step(s) via groq") in reasons


def test_exact_rule_phrases_never_call_the_llm(monkeypatch) -> None:
    fake = FakePlanner(COMPOSE)
    _use(monkeypatch, fake)
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            assert client.post("/api/v1/tasks", headers=user, json={"instruction": "open notepad"}).status_code == 201
            assert fake.calls == []


def test_model_output_cannot_exceed_the_devices_scope(monkeypatch) -> None:
    _use(monkeypatch, FakePlanner([{"action": {"type": "open_app", "app": "chrome"}, "confidence": 1}]))
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            response = client.post("/api/v1/tasks", headers=user, json={"instruction": "open my browser"})
            assert response.status_code == 403
            assert client.get("/api/v1/tasks", headers=user).json() == []
            assert client.get("/api/v1/audit", headers=user).json()[0]["reason"] == "unknown_app"


def test_hostile_model_output_is_held_back_not_run(monkeypatch) -> None:
    _use(
        monkeypatch,
        FakePlanner(
            [
                {"action": {"type": "open_app", "app": "notepad"}, "confidence": 1},
                {"action": {"type": "shell", "command": "del /s /q c:\\"}, "confidence": 1},
                {"action": {"type": "type_text", "text": "after"}, "confidence": 1},
            ]
        ),
    )
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            created = client.post("/api/v1/tasks", headers=user, json={"instruction": "tidy my disk"})
            assert created.status_code == 201
            assert [h["reason"] for h in created.json()["held_back"]] == ["unknown_action", "blocked_by_earlier_step"]
            assert [s["action"]["type"] for s in ws.receive_json()["plan"]] == ["open_app"]


def test_planner_declining_is_a_clear_refusal(monkeypatch) -> None:
    _use(monkeypatch, FakePlanner([], note="I can only use Notepad here"))
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            response = client.post("/api/v1/tasks", headers=user, json={"instruction": "book a flight"})
            assert response.status_code == 422
            assert response.json()["detail"] == "I can only use Notepad here"
            assert client.get("/api/v1/tasks", headers=user).json() == []


def test_planner_outage_is_a_503_and_creates_no_task(monkeypatch) -> None:
    from app.planner import PlannerError

    _use(monkeypatch, FakePlanner(error=PlannerError("down")))
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            response = client.post("/api/v1/tasks", headers=user, json={"instruction": "write a poem"})
            assert response.status_code == 503
            assert "down" not in response.text
            assert client.get("/api/v1/audit", headers=user).json()[0]["reason"] == "planner_failed"
            # The rule phrases still work while the planner is down.
            assert client.post("/api/v1/tasks", headers=user, json={"instruction": "open notepad"}).status_code == 201


def test_without_a_key_unknown_instructions_are_rejected_as_before(monkeypatch) -> None:
    _use(monkeypatch, None)
    with TestClient(app) as client:
        user = _signup(client)
        response = client.post("/api/v1/tasks", headers=user, json={"instruction": "write a poem"})
        assert response.status_code == 400


def test_planner_calls_are_rate_limited_per_user(monkeypatch) -> None:
    from app.ratelimit import planner_limiter

    monkeypatch.setattr(planner_limiter, "max_events", 2)
    _use(monkeypatch, FakePlanner(COMPOSE))
    with TestClient(app) as client:
        alice = _signup(client, "alice@example.com")
        bob = _signup(client, "bob@example.com")
        agent_id, _ = _register(client, alice)
        _register(client, bob)
        for _ in range(2):
            assert client.post("/api/v1/plans/preview", headers=alice, json={"instruction": "write a note"}).status_code == 200
        assert client.post("/api/v1/plans/preview", headers=alice, json={"instruction": "write a note"}).status_code == 429
        assert client.post("/api/v1/plans/preview", headers=bob, json={"instruction": "write a note"}).status_code == 200


# preview and confirm
def test_preview_shows_the_plan_without_running_anything(monkeypatch) -> None:
    fake = FakePlanner(COMPOSE)
    _use(monkeypatch, fake)
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        # The PC is offline: previewing must still work and must not dispatch.
        preview = client.post("/api/v1/plans/preview", headers=user, json={"instruction": "write a thank-you note"})
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["planner"] == "groq" and body["runnable"] is True and body["low_confidence"] is False
        assert [s["description"] for s in body["steps"]][:2] == ["Open Notepad", "Type \u201cDear team\u201d"]
        assert client.get("/api/v1/tasks", headers=user).json() == []

        # Confirming sends the previewed plan back; the planner is not asked again.
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            created = client.post(
                "/api/v1/tasks", headers=user, json={"instruction": "write a thank-you note", "plan": body["plan"]}
            )
            assert created.status_code == 201
            assert len(ws.receive_json()["plan"]) == 4
        assert len(fake.calls) == 1
        events = [e["event"] for e in client.get("/api/v1/audit", headers=user).json()]
        assert "plan_previewed" in events


def test_preview_flags_low_confidence_and_held_back_steps(monkeypatch) -> None:
    _use(
        monkeypatch,
        FakePlanner(
            [
                {"action": {"type": "open_app", "app": "notepad"}, "confidence": 0.4},
                {"action": {"type": "click", "target": "File"}, "confidence": 0.3},
            ]
        ),
    )
    with TestClient(app) as client:
        user = _signup(client)
        _register(client, user)
        body = client.post("/api/v1/plans/preview", headers=user, json={"instruction": "open the file menu"}).json()
        assert body["runnable"] is True and body["low_confidence"] is True
        assert [h["reason"] for h in body["held_back"]] == ["not_supported"]
        assert len(body["plan"]) == 2


def test_preview_of_a_declined_request_is_not_runnable(monkeypatch) -> None:
    _use(monkeypatch, FakePlanner([], note="Cannot do that"))
    with TestClient(app) as client:
        user = _signup(client)
        _register(client, user)
        body = client.post("/api/v1/plans/preview", headers=user, json={"instruction": "launch a rocket"}).json()
        assert body["runnable"] is False and body["note"] == "Cannot do that" and body["steps"] == []


def test_preview_uses_rules_for_exact_phrases(monkeypatch) -> None:
    fake = FakePlanner(COMPOSE)
    _use(monkeypatch, fake)
    with TestClient(app) as client:
        user = _signup(client)
        _register(client, user)
        body = client.post(
            "/api/v1/plans/preview", headers=user, json={"instruction": "Open Notepad and type hi"}
        ).json()
        assert body["planner"] == "rules" and len(body["steps"]) == 2
        assert fake.calls == []


def test_preview_device_rules(monkeypatch) -> None:
    _use(monkeypatch, FakePlanner(COMPOSE))
    with TestClient(app) as client:
        alice = _signup(client, "alice@example.com")
        bob = _signup(client, "bob@example.com")
        body = {"instruction": "write a note"}
        assert client.post("/api/v1/plans/preview", json=body).status_code == 401
        assert client.post("/api/v1/plans/preview", headers=alice, json=body).status_code == 503  # nothing paired
        first, _ = _register(client, alice)
        assert client.post("/api/v1/plans/preview", headers=alice, json=body).status_code == 200
        _register(client, alice)
        assert client.post("/api/v1/plans/preview", headers=alice, json=body).status_code == 409  # which PC?
        assert client.post("/api/v1/plans/preview", headers=bob, json={**body, "agent_id": first}).status_code == 404
        client.post(f"/api/v1/agents/{first}/revoke", headers=alice)
        assert client.post("/api/v1/plans/preview", headers=alice, json={**body, "agent_id": first}).status_code == 403


def test_preview_respects_the_devices_scope(monkeypatch) -> None:
    fake = FakePlanner(COMPOSE)
    _use(monkeypatch, fake)
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, _ = _register(client, user)
        client.patch(f"/api/v1/agents/{agent_id}", headers=user, json={"permitted_apps": []})
        body = client.post("/api/v1/plans/preview", headers=user, json={"instruction": "write a note"}).json()
        assert body["runnable"] is False
        assert body["held_back"][0]["reason"] == "app_not_permitted"
        assert fake.calls == [("write a note", [])]


def test_client_supplied_plans_are_validated_like_any_other() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            evil = [{"action": {"type": "open_app", "app": "cmd"}}]
            assert client.post("/api/v1/tasks", headers=user, json={"instruction": "x", "plan": evil}).status_code == 403
            assert client.post("/api/v1/tasks", headers=user, json={"instruction": "x", "plan": []}).status_code == 422
            too_many = [{"action": {"type": "wait", "seconds": 1}}] * 51
            assert client.post("/api/v1/tasks", headers=user, json={"instruction": "x", "plan": too_many}).status_code == 422
            assert client.get("/api/v1/tasks", headers=user).json() == []
