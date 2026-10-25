"""Connect the Windows agent to the FastAPI backend over WebSocket."""

from __future__ import annotations

import argparse
import asyncio
import base64
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
DEFAULT_TOKEN = os.environ.get("OMNIAGENT_AGENT_TOKEN", "dev-agent-token")
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


def register_agent(api: str, token: str, name: str, hostname: str) -> str:
    body = _request(
        "POST",
        f"{api.rstrip('/')}/v1/agents/register",
        token,
        {"name": name, "hostname": hostname},
    )
    return str(body["id"])


def _ws_url(api: str, agent_id: str, token: str) -> str:
    base = api.rstrip("/").replace("https://", "wss://").replace("http://", "ws://")
    return f"{base}/v1/agents/{agent_id}/ws?token={token}"


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


async def run_client(api: str, token: str, name: str, hostname: str) -> None:
    agent_id = register_agent(api, token, name, hostname)
    url = _ws_url(api, agent_id, token)
    logger.info("Registered %s (%s)", name, agent_id)
    async with websockets.connect(url) as ws:
        logger.info("Connected to %s", url)
        async for raw in ws:
            message = json.loads(raw)
            if message.get("type") == "task":
                await handle_task(ws, message)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OmniAgent Windows PC connector")
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--token", default=DEFAULT_TOKEN)
    parser.add_argument("--name", default=os.environ.get("OMNIAGENT_PC_NAME", "Office PC"))
    parser.add_argument("--hostname", default=socket.gethostname())
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        asyncio.run(run_client(args.api, args.token, args.name, args.hostname))
    except KeyboardInterrupt:
        return 0
    except (urllib.error.URLError, OSError) as exc:
        logger.error("Could not reach backend: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
