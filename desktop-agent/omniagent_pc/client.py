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

from omniagent_pc.plan_runner import Executor, PlanOutcome, RunContext, run_plan

logger = logging.getLogger(__name__)

DEFAULT_API = os.environ.get("OMNIAGENT_API", "http://127.0.0.1:8000")
CREDENTIALS_FILE = Path(os.environ.get("OMNIAGENT_HOME", Path.home() / ".omniagent")) / "agent.json"


def _request(method: str, url: str, token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            **({"Authorization": f"Bearer {token}"} if token else {}),
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode())


def pair(api: str, code: str, name: str, hostname: str) -> dict[str, Any]:
    """Exchange the one-time code from the phone app for this PC's device token."""
    return _request(
        "POST",
        f"{api.rstrip('/')}/api/v1/agents/pair",
        "",
        {"code": code, "name": name, "hostname": hostname},
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


def ensure_credentials(api: str, name: str, hostname: str, code: str) -> dict[str, str]:
    """Reuse the saved device credentials, or pair once with a code from the phone app."""
    saved = load_credentials(api)
    if saved:
        return saved
    code = code or input("Pairing code from the OmniAgent app (Devices > Add PC): ").strip()
    paired = pair(api, code, name, hostname)
    save_credentials(api, paired["id"], paired["device_token"])
    logger.info("Paired %s (%s); device credentials saved to %s", name, paired["id"], CREDENTIALS_FILE)
    return load_credentials(api) or {}


def _ws_url(api: str, agent_id: str) -> str:
    base = api.rstrip("/").replace("https://", "wss://").replace("http://", "ws://")
    return f"{base}/api/v1/agents/{agent_id}/ws"


def _run_blocking(
    plan: list[dict[str, Any]],
    executors: dict[str, Executor],
    context: RunContext,
    report: Any,
) -> PlanOutcome:
    """Runs on a worker thread: UI automation blocks."""
    outcome = run_plan(plan, executors, context, report)
    if context.screenshot_path is None:
        try:
            from omniagent_pc.screenshot import capture_screen

            path, _ = capture_screen()
            context.screenshot_path = str(path) if path else None
        except Exception:  # noqa: BLE001 - a missing final screenshot must not fail the task
            logger.exception("Final screenshot failed")
    return outcome


def _well_formed(plan: Any) -> bool:
    return isinstance(plan, list) and all(
        isinstance(step, dict) and isinstance(step.get("index"), int) and isinstance(step.get("action"), dict)
        for step in plan
    )


async def handle_task(ws: Any, message: dict[str, Any], executors: dict[str, Executor] | None = None) -> None:
    task_id = message["task_id"]
    plan = message.get("plan")
    await ws.send(json.dumps({"type": "ack", "task_id": task_id}))

    if not _well_formed(plan) or not plan:
        await ws.send(
            json.dumps({"type": "result", "task_id": task_id, "status": "failed", "error": "Malformed plan"})
        )
        return

    if executors is None:
        from omniagent_pc.executors import build_executors

        executors = build_executors()

    loop = asyncio.get_running_loop()
    sent: list[Any] = []

    def report(index: int, status: str, detail: str) -> None:
        payload = {"type": "step", "task_id": task_id, "index": index, "status": status, "detail": detail}
        sent.append(asyncio.run_coroutine_threadsafe(ws.send(json.dumps(payload)), loop))

    context = RunContext()
    outcome = await asyncio.to_thread(_run_blocking, plan, executors, context, report)
    for future in sent:  # keep step updates ahead of the result
        await asyncio.wrap_future(future)

    screenshot_b64 = None
    if context.screenshot_path:
        path = Path(context.screenshot_path)
        if path.is_file():
            screenshot_b64 = base64.b64encode(path.read_bytes()).decode()

    await ws.send(
        json.dumps(
            {
                "type": "result",
                "task_id": task_id,
                "status": outcome.status,
                "summary": outcome.summary,
                "error": outcome.error,
                "screenshot_b64": screenshot_b64,
            }
        )
    )


async def run_client(api: str, name: str, hostname: str, code: str = "") -> None:
    creds = await asyncio.to_thread(ensure_credentials, api, name, hostname, code)
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
    parser.add_argument("--code", default=os.environ.get("OMNIAGENT_PAIRING_CODE", ""), help="pairing code from the app")
    parser.add_argument("--reset", action="store_true", help="forget saved device credentials")
    parser.add_argument("--name", default=os.environ.get("OMNIAGENT_PC_NAME", "Office PC"))
    parser.add_argument("--hostname", default=socket.gethostname())
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.reset:
        CREDENTIALS_FILE.unlink(missing_ok=True)
    try:
        asyncio.run(run_client(args.api, args.name, args.hostname, args.code))
    except KeyboardInterrupt:
        return 0
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            logger.error("Too many pairing attempts. Wait a few minutes and try again.")
        else:
            logger.error("Pairing failed (%s). The code may be wrong, used, or expired: make a new one in the app.", exc.code)
        return 1
    except websockets.exceptions.InvalidStatus as exc:
        logger.error(
            "Backend rejected this PC (%s). It may have been removed or expired. Run with --reset and pair again.",
            exc.response.status_code,
        )
        return 1
    except (urllib.error.URLError, OSError) as exc:
        logger.error("Could not reach backend: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
