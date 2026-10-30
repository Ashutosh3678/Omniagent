"""Connect the Windows agent to the FastAPI backend and run the plans it sends.

The connection is kept alive for as long as the program runs: if it drops it is
re-opened with growing waits, unless the backend says this PC was removed. Tasks run
one at a time on a worker thread; the receive loop stays free so a cancel from the
phone is heard while a task is running.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import os
import random
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

import websockets

from omniagent_pc.plan_runner import Executor, PlanOutcome, RunContext, run_plan

logger = logging.getLogger(__name__)

DEPLOYED_API = "https://omniagent-backend-22fj.onrender.com"
DEFAULT_API = os.environ.get("OMNIAGENT_API", DEPLOYED_API)
CREDENTIALS_FILE = Path(os.environ.get("OMNIAGENT_HOME", Path.home() / ".omniagent")) / "agent.json"

# Close codes and HTTP statuses that mean "this PC is not allowed": reconnecting will not help.
FATAL_CLOSE_CODES = frozenset({4401, 4403, 4404})
FATAL_HTTP_STATUSES = frozenset({401, 403, 404})
MAX_BACKOFF_SECONDS = 30.0
# A free Render service sleeps when idle and needs up to a minute to wake: be patient with the first contact.
REQUEST_TIMEOUT_SECONDS = 90
CONNECT_TIMEOUT_SECONDS = 60

# on_event(kind, text) lets a window show what the agent is doing. Kinds: connecting, connected,
# disconnected, step, task_started, task_finished. It is called from several threads and must not block.
EventCallback = Callable[[str, str], None]


def _notify(on_event: EventCallback | None, kind: str, text: str = "") -> None:
    if on_event is None:
        return
    try:
        on_event(kind, text)
    except Exception:  # noqa: BLE001 - a broken window must never stop the agent
        logger.exception("Event callback failed")


class RejectedByBackend(Exception):
    """The backend refused this PC (removed, expired, or unknown). Pair again."""


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
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
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


def _default_executors() -> dict[str, Executor]:
    from omniagent_pc.executors import build_executors

    return build_executors()


def _default_catalog() -> dict[str, Any]:
    """The apps and folder names the owner has set up on this PC (see apps.py), read fresh on every connect."""
    from omniagent_pc import apps

    return apps.catalog()


def _default_capture() -> Callable[[], bytes | None]:
    def capture() -> bytes | None:
        from omniagent_pc.screenshot import capture_jpeg

        return capture_jpeg()

    return capture


def _run_blocking(
    plan: list[dict[str, Any]],
    executors: dict[str, Executor],
    context: RunContext,
    report: Any,
    stop: threading.Event,
) -> PlanOutcome:
    """Runs on a worker thread: UI automation blocks."""
    try:
        outcome = run_plan(plan, executors, context, report, should_stop=stop.is_set)
        if context.screenshot_path is None:
            try:
                from omniagent_pc.screenshot import capture_screen

                path, _ = capture_screen()
                context.screenshot_path = str(path) if path else None
            except Exception:  # noqa: BLE001 - a missing final screenshot must not fail the task
                logger.exception("Final screenshot failed")
        return outcome
    finally:
        context.cleanup()


def _well_formed(plan: Any) -> bool:
    return isinstance(plan, list) and all(
        isinstance(step, dict) and isinstance(step.get("index"), int) and isinstance(step.get("action"), dict)
        for step in plan
    )


async def _send(ws: Any, payload: dict[str, Any]) -> bool:
    """Sends one message; False if the connection is gone (the task is then abandoned)."""
    try:
        await ws.send(json.dumps(payload))
        return True
    except websockets.exceptions.ConnectionClosed:
        return False


async def handle_task(
    ws: Any,
    message: dict[str, Any],
    executors: dict[str, Executor] | None = None,
    stop: threading.Event | None = None,
    capture: Callable[[], bytes | None] | None = None,
    on_event: EventCallback | None = None,
) -> None:
    task_id = message["task_id"]
    plan = message.get("plan")
    stop = stop or threading.Event()
    await _send(ws, {"type": "ack", "task_id": task_id})

    if not _well_formed(plan) or not plan:
        await _send(ws, {"type": "result", "task_id": task_id, "status": "failed", "error": "Malformed plan"})
        return

    executors = executors if executors is not None else _default_executors()

    loop = asyncio.get_running_loop()
    sent: list[Any] = []

    def report(index: int, status: str, detail: str, shot: bytes | None = None) -> None:
        payload: dict[str, Any] = {"type": "step", "task_id": task_id, "index": index, "status": status, "detail": detail}
        if shot:
            payload["screenshot_b64"] = base64.b64encode(shot).decode()
            payload["content_type"] = "image/jpeg"
        sent.append(asyncio.run_coroutine_threadsafe(_send(ws, payload), loop))
        if status != "running":
            _notify(on_event, "step", f"Step {index + 1}: {status}" + (f" ({detail[:90]})" if detail else ""))

    _notify(on_event, "task_started", f"Running {len(plan)} step(s)")
    context = RunContext(capture_jpeg=capture if capture is not None else _default_capture())
    outcome = await asyncio.to_thread(_run_blocking, plan, executors, context, report, stop)
    for future in sent:  # keep step updates ahead of the result
        await asyncio.wrap_future(future)

    screenshot_b64 = None
    if context.screenshot_path:
        path = Path(context.screenshot_path)
        if path.is_file():
            screenshot_b64 = base64.b64encode(path.read_bytes()).decode()

    _notify(on_event, "task_finished", f"{outcome.status}: {outcome.summary}" + (f" ({outcome.error})" if outcome.error else ""))
    await _send(
        ws,
        {
            "type": "result",
            "task_id": task_id,
            "status": outcome.status,
            "summary": outcome.summary,
            "error": outcome.error,
            "screenshot_b64": screenshot_b64,
        },
    )


async def serve(
    ws: Any,
    executors: dict[str, Executor] | None = None,
    capture: Callable[[], bytes | None] | None = None,
    on_event: EventCallback | None = None,
    catalog: Callable[[], dict[str, Any]] | None = None,
) -> None:
    """Handles one connection until it closes: reports what this PC can do, runs tasks, hears cancels."""
    executors = executors if executors is not None else _default_executors()
    report: dict[str, Any] = {"type": "capabilities", "actions": sorted(executors)}
    if catalog is not None:  # which apps and folder names the owner set up here; never paths
        try:
            report.update(catalog())
        except Exception:  # noqa: BLE001 - a damaged settings file must not stop the agent connecting
            logger.exception("Could not read the apps and folders list")
    await _send(ws, report)

    running: dict[str, threading.Event] = {}
    workers: set[asyncio.Task] = set()

    async def run_one(message: dict[str, Any], stop: threading.Event) -> None:
        try:
            await handle_task(ws, message, executors, stop, capture, on_event)
        except Exception:  # noqa: BLE001 - one bad task must not take the connection down
            logger.exception("Task %s crashed", message.get("task_id"))
        finally:
            running.pop(message["task_id"], None)

    try:
        async for raw in ws:
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            kind = message.get("type")
            task_id = message.get("task_id")
            if kind == "task" and isinstance(task_id, str):
                if running:
                    await _send(ws, {"type": "ack", "task_id": task_id})
                    await _send(ws, {"type": "result", "task_id": task_id, "status": "failed", "error": "This PC is busy with another task"})
                    continue
                stop = threading.Event()
                running[task_id] = stop
                worker = asyncio.create_task(run_one(message, stop))
                workers.add(worker)
                worker.add_done_callback(workers.discard)
            elif kind == "cancel":
                event = running.get(task_id)
                if event is not None:
                    logger.info("Cancel requested for task %s", task_id)
                    event.set()
            elif kind == "ping":
                await _send(ws, {"type": "pong"})
    finally:
        for event in running.values():  # the connection is gone: stop acting on the PC
            event.set()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)


def _close_code(exc: BaseException | None, ws: Any = None) -> int | None:
    received = getattr(exc, "rcvd", None)
    if received is not None:
        return received.code
    return getattr(ws, "close_code", None)


async def run_client(
    api: str,
    name: str,
    hostname: str,
    code: str = "",
    *,
    connect: Callable[..., Any] | None = None,
    sleep: Callable[[float], Any] = asyncio.sleep,
    executors: dict[str, Executor] | None = None,
    capture: Callable[[], bytes | None] | None = None,
    jitter: Callable[[], float] = random.random,
    on_event: EventCallback | None = None,
    catalog: Callable[[], dict[str, Any]] | None = _default_catalog,
) -> None:
    """Stays connected. Returns only by raising RejectedByBackend (or on Ctrl+C)."""
    creds = await asyncio.to_thread(ensure_credentials, api, name, hostname, code)
    agent_id, token = creds["agent_id"], creds["device_token"]
    url = _ws_url(api, agent_id)
    connect = connect or websockets.connect
    executors = executors if executors is not None else _default_executors()
    backoff = 1.0

    while True:
        ws = None
        close_code: int | None = None
        _notify(on_event, "connecting", "Connecting to the server")
        try:
            async with connect(
                url,
                additional_headers={"Authorization": f"Bearer {token}"},
                open_timeout=CONNECT_TIMEOUT_SECONDS,
            ) as ws:
                logger.info("Connected to %s", url)
                backoff = 1.0
                _notify(on_event, "connected", "Connected. Waiting for tasks")
                await serve(ws, executors, capture, on_event, catalog)
            close_code = _close_code(None, ws)
        except websockets.exceptions.InvalidStatus as exc:
            if exc.response.status_code in FATAL_HTTP_STATUSES:
                raise RejectedByBackend(f"Backend rejected this PC ({exc.response.status_code})") from exc
            logger.warning("Backend answered %s", exc.response.status_code)
        except websockets.exceptions.ConnectionClosed as exc:
            close_code = _close_code(exc, ws)
        except (OSError, TimeoutError, websockets.exceptions.WebSocketException) as exc:
            logger.warning("Connection failed: %s", exc)

        if close_code in FATAL_CLOSE_CODES:
            raise RejectedByBackend(f"This PC was removed or is no longer allowed (code {close_code})")

        wait = backoff + jitter()
        logger.info("Disconnected. Reconnecting in %.0fs", wait)
        _notify(on_event, "disconnected", f"Disconnected. Reconnecting in {wait:.0f}s")
        await sleep(wait)
        backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)


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
    except RejectedByBackend as exc:
        logger.error("%s. Run again with --reset and a new pairing code.", exc)
        return 1
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            logger.error("Too many pairing attempts. Wait a few minutes and try again.")
        else:
            logger.error("Pairing failed (%s). The code may be wrong, used, or expired: make a new one in the app.", exc.code)
        return 1
    except (urllib.error.URLError, OSError) as exc:
        logger.error("Could not reach backend: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
