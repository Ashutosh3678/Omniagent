"""Connect the Windows agent to the FastAPI backend over WebSocket."""

from __future__ import annotations

import argparse
import asyncio
import base64
import getpass
import json
import logging
import os
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import websockets

from omniagent_pc.runner import run_phase1_task

logger = logging.getLogger(__name__)

DEFAULT_API = os.environ.get("OMNIAGENT_API", "http://127.0.0.1:8000")
CREDENTIALS_FILE = Path(os.environ.get("OMNIAGENT_HOME", Path.home() / ".omniagent")) / "agent.json"
ALLOWED_ACTIONS = frozenset({"open_notepad"})


def _request(method: str, url: str, token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode())


def login(api: str, email: str, password: str) -> str:
    body = _request(
        "POST", f"{api.rstrip('/')}/api/v1/auth/login", "", {"email": email, "password": password}
    )
    return str(body["access_token"])


def register_agent(api: str, user_token: str, name: str, hostname: str) -> dict[str, Any]:
    return _request(
        "POST",
        f"{api.rstrip('/')}/api/v1/agents/register",
        user_token,
        {"name": name, "hostname": hostname},
    )


def load_credentials(api: str) -> dict[str, str] | None:
    try:
        data = json.loads(CREDENTIALS_FILE.read_text())
    except (OSError, ValueError):
        return None
    if data.get("api") != api.rstrip("/") or not data.get("agent_id") or not data.get("device_token"):
        return None
    return data


def save_credentials(api: str, agent_id: str, device_token: str) -> None:
    CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_FILE.write_text(
        json.dumps({"api": api.rstrip("/"), "agent_id": agent_id, "device_token": device_token})
    )


def ensure_credentials(api: str, name: str, hostname: str, email: str, password: str) -> dict[str, str]:
    """Reuse the saved device credentials, or sign in once to register this PC."""
    saved = load_credentials(api)
    if saved:
        return saved
    email = email or input("OmniAgent account email: ").strip()
    password = password or getpass.getpass("Password: ")
    registered = register_agent(api, login(api, email, password), name, hostname)
    save_credentials(api, registered["id"], registered["device_token"])
    logger.info("Registered %s (%s); device credentials saved to %s", name, registered["id"], CREDENTIALS_FILE)
    return load_credentials(api) or {}


def _ws_url(api: str, agent_id: str) -> str:
    base = api.rstrip("/").replace("https://", "wss://").replace("http://", "ws://")
    return f"{base}/api/v1/agents/{agent_id}/ws"


async def handle_task(ws: Any, message: dict[str, Any]) -> None:
    task_id = message["task_id"]
    action = message.get("action") or {}
    action_type = action.get("type")
    await ws.send(json.dumps({"type": "ack", "task_id": task_id}))

    if action_type not in ALLOWED_ACTIONS:
        await ws.send(
            json.dumps(
                {
                    "type": "result",
                    "task_id": task_id,
                    "status": "failed",
                    "error": f"Rejected action: {action_type}",
                }
            )
        )
        return

    await ws.send(
        json.dumps(
            {
                "type": "progress",
                "task_id": task_id,
                "log": "Starting Notepad task",
                "steps": [{"name": "Open Notepad", "status": "running"}],
            }
        )
    )

    typed = str(action.get("message") or "Hello from OmniAgent")
    result = await asyncio.to_thread(run_phase1_task, typed)
    screenshot_b64 = None
    if result.screenshot_path:
        path = Path(result.screenshot_path)
        if path.is_file():
            screenshot_b64 = base64.b64encode(path.read_bytes()).decode()

    steps = [
        {
            "name": step.name,
            "status": "success" if step.status == "Success" else "failed",
            "detail": step.detail,
        }
        for step in result.steps
    ]
    await ws.send(
        json.dumps(
            {
                "type": "result",
                "task_id": task_id,
                "status": "completed" if result.succeeded else "failed",
                "summary": result.message,
                "error": "" if result.succeeded else result.message,
                "steps": steps,
                "screenshot_b64": screenshot_b64,
            }
        )
    )


async def run_client(api: str, name: str, hostname: str, email: str = "", password: str = "") -> None:
    creds = await asyncio.to_thread(ensure_credentials, api, name, hostname, email, password)
    agent_id, token = creds["agent_id"], creds["device_token"]
    url = _ws_url(api, agent_id)
    async with websockets.connect(
        url, additional_headers={"Authorization": f"Bearer {token}"}
    ) as ws:
        logger.info("Connected to %s", url)
        async for raw in ws:
            message = json.loads(raw)
            if message.get("type") == "task":
                await handle_task(ws, message)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OmniAgent Windows PC connector")
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--email", default=os.environ.get("OMNIAGENT_EMAIL", ""))
    parser.add_argument("--password", default=os.environ.get("OMNIAGENT_PASSWORD", ""))
    parser.add_argument("--reset", action="store_true", help="forget saved device credentials")
    parser.add_argument("--name", default=os.environ.get("OMNIAGENT_PC_NAME", "Office PC"))
    parser.add_argument("--hostname", default=socket.gethostname())
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.reset:
        CREDENTIALS_FILE.unlink(missing_ok=True)
    try:
        asyncio.run(run_client(args.api, args.name, args.hostname, args.email, args.password))
    except KeyboardInterrupt:
        return 0
    except urllib.error.HTTPError as exc:
        logger.error("Backend refused the request (%s). Check your email and password.", exc.code)
        return 1
    except websockets.exceptions.InvalidStatus as exc:
        logger.error("Backend rejected this PC (%s). Run again with --reset to sign in and re-register.", exc.response.status_code)
        return 1
    except (urllib.error.URLError, OSError) as exc:
        logger.error("Could not reach backend: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
