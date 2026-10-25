from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from app.main import app
from app.store import store

APP = {"Authorization": "Bearer dev-app-token"}
AGENT = {"Authorization": "Bearer dev-agent-token"}


def setup_function() -> None:
    store.reset()


def test_health() -> None:
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"


def test_unauthorized_app_request() -> None:
    with TestClient(app) as client:
        response = client.get("/v1/agents")
        assert response.status_code == 401


def test_reject_invalid_instruction() -> None:
    with TestClient(app) as client:
        _register_and_connect(client)
        response = client.post(
            "/v1/tasks",
            headers=APP,
            json={"instruction": "run calc.exe"},
        )
        assert response.status_code == 400


def test_disconnected_agent_rejected() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/v1/agents/register",
            headers=AGENT,
            json={"name": "Office PC", "hostname": "DESKTOP-7K2M"},
        )
        agent_id = response.json()["id"]
        create = client.post(
            "/v1/tasks",
            headers=APP,
            json={"instruction": "Open Notepad and type Hello from OmniAgent", "agent_id": agent_id},
        )
        assert create.status_code == 409


def test_task_roundtrip_with_connected_agent() -> None:
    with TestClient(app) as client:
        agent_id = _register(client)
        with client.websocket_connect(f"/v1/agents/{agent_id}/ws?token=dev-agent-token") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello_ok"

            create = client.post(
                "/v1/tasks",
                headers=APP,
                json={"instruction": "Open Notepad and type Hello from OmniAgent"},
            )
            assert create.status_code == 201
            task = create.json()
            assert task["status"] == "running"

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

            fetched = client.get(f"/v1/tasks/{inbound['task_id']}", headers=APP).json()
            assert fetched["status"] == "completed"
            assert fetched["screenshot_url"]
            shot = client.get(fetched["screenshot_url"], headers=APP)
            assert shot.status_code == 200
            assert shot.headers["content-type"] == "image/png"


def test_agent_disconnect_fails_running_task() -> None:
    with TestClient(app) as client:
        agent_id = _register(client)
        with client.websocket_connect(f"/v1/agents/{agent_id}/ws?token=dev-agent-token") as ws:
            ws.receive_json()
            create = client.post(
                "/v1/tasks",
                headers=APP,
                json={"instruction": "Open Notepad and type Hello from OmniAgent"},
            )
            task_id = create.json()["id"]
            ws.receive_json()
        fetched = client.get(f"/v1/tasks/{task_id}", headers=APP).json()
        assert fetched["status"] == "failed"
        assert fetched["error"] == "Agent disconnected"


def test_failed_result_from_agent() -> None:
    with TestClient(app) as client:
        agent_id = _register(client)
        with client.websocket_connect(f"/v1/agents/{agent_id}/ws?token=dev-agent-token") as ws:
            ws.receive_json()
            create = client.post(
                "/v1/tasks",
                headers=APP,
                json={"instruction": "open notepad"},
            )
            inbound = ws.receive_json()
            ws.send_json(
                {
                    "type": "result",
                    "task_id": inbound["task_id"],
                    "status": "failed",
                    "error": "Could not open Notepad",
                }
            )
            fetched = client.get(f"/v1/tasks/{create.json()['id']}", headers=APP).json()
            assert fetched["status"] == "failed"
            assert fetched["error"] == "Could not open Notepad"


def _register(client: TestClient) -> str:
    response = client.post(
        "/v1/agents/register",
        headers=AGENT,
        json={"name": "Office PC", "hostname": "DESKTOP-7K2M"},
    )
    assert response.status_code == 200
    return response.json()["id"]


def _register_and_connect(client: TestClient):
    agent_id = _register(client)
    return agent_id
