from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.store import store


def setup_function() -> None:
    store.reset()


def _signup(client: TestClient, email: str = "alex@example.com", password: str = "correct-horse") -> dict:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _register(client: TestClient, user: dict) -> tuple[str, dict]:
    response = client.post(
        "/api/v1/agents/register", headers=user, json={"name": "Office PC", "hostname": "DESKTOP-7K2M"}
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
        assert create.status_code == 409


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
            assert inbound["action"]["type"] == "open_notepad"
            assert inbound["action"]["message"] == "Hello from OmniAgent"

            png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 32).decode()
            ws.send_json(
                {
                    "type": "result",
                    "task_id": inbound["task_id"],
                    "status": "completed",
                    "summary": "Opened Notepad",
                    "steps": [{"name": "Open Notepad", "status": "success"}],
                    "screenshot_b64": png,
                }
            )

            fetched = client.get(f"/api/v1/tasks/{inbound['task_id']}", headers=user).json()
            assert fetched["status"] == "completed"
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
            assert hijack.status_code == 409

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
