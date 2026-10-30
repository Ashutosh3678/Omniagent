from __future__ import annotations

import asyncio
import base64
import json
import threading

import pytest
import websockets
from websockets.datastructures import Headers
from websockets.frames import Close
from websockets.http11 import Response

from omniagent_pc import client
from omniagent_pc.plan_runner import StepOutcome


class FakeWs:
    """Stands in for a websocket: `incoming` is an async generator of raw messages."""

    def __init__(self, incoming=None, end_with: BaseException | None = None) -> None:
        self.sent: list[dict] = []
        self._incoming = incoming
        self._end_with = end_with

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        if self._incoming is not None:
            async for raw in self._incoming():
                yield raw
        if self._end_with is not None:
            raise self._end_with


def task(*types: str, task_id: str = "t1") -> dict:
    return {"type": "task", "task_id": task_id, "plan": [{"index": i, "action": {"type": t}} for i, t in enumerate(types)]}


ok = lambda a, c: StepOutcome(True, "fine")  # noqa: E731


def kinds(ws: FakeWs) -> list[tuple]:
    return [(m["type"], m.get("index"), m.get("status")) for m in ws.sent]


# --- one task
def test_reports_each_step_then_the_result_in_order() -> None:
    ws = FakeWs()
    asyncio.run(client.handle_task(ws, task("a", "b"), {"a": ok, "b": ok}))
    assert kinds(ws) == [
        ("ack", None, None),
        ("step", 0, "running"),
        ("step", 0, "success"),
        ("step", 1, "running"),
        ("step", 1, "success"),
        ("result", None, "completed"),
    ]


def test_every_finished_step_carries_its_screenshot() -> None:
    ws = FakeWs()
    asyncio.run(client.handle_task(ws, task("a"), {"a": ok}, capture=lambda: b"\xff\xd8jpeg"))
    done = next(m for m in ws.sent if m["type"] == "step" and m["status"] == "success")
    assert base64.b64decode(done["screenshot_b64"]) == b"\xff\xd8jpeg"
    assert done["content_type"] == "image/jpeg"
    running = next(m for m in ws.sent if m["type"] == "step" and m["status"] == "running")
    assert "screenshot_b64" not in running


def test_failed_step_gives_a_partial_result_and_skips_the_rest() -> None:
    ws = FakeWs()
    executors = {"a": ok, "b": lambda a, c: StepOutcome(False, "nope"), "c": ok}
    asyncio.run(client.handle_task(ws, task("a", "b", "c"), executors))
    assert ws.sent[-1]["status"] == "partial" and ws.sent[-1]["error"] == "nope"
    assert any(m.get("index") == 2 and m.get("status") == "skipped" for m in ws.sent)


def test_unconfirmed_step_is_reported_as_unverified() -> None:
    class Blank:
        def observe_text(self) -> str:
            return "nothing relevant"

    def typed(_a, ctx):
        ctx.driver = Blank()
        return StepOutcome(True, "typed", expected="Dear team thank you")

    ws = FakeWs()
    asyncio.run(client.handle_task(ws, task("t"), {"t": typed}))
    assert ("step", 0, "unverified") in kinds(ws)
    assert ws.sent[-1]["status"] == "partial"


def test_unknown_action_is_refused() -> None:
    ws = FakeWs()
    asyncio.run(client.handle_task(ws, task("shell"), {}))
    assert ws.sent[-1]["status"] == "failed" and "shell" in ws.sent[-1]["error"]


@pytest.mark.parametrize("plan", [None, [], "open notepad", [{"index": 0}], [{"action": {"type": "wait"}}]])
def test_malformed_or_empty_plans_fail_without_running_anything(plan) -> None:
    ws = FakeWs()
    asyncio.run(client.handle_task(ws, {"type": "task", "task_id": "t1", "plan": plan}, {"wait": ok}))
    assert [m["type"] for m in ws.sent] == ["ack", "result"] and ws.sent[-1]["status"] == "failed"


def test_cleanups_run_even_when_the_plan_fails() -> None:
    cleaned: list[str] = []

    def opener(_a, ctx):
        if not ctx.cleanups:  # the step is retried; register the browser once
            ctx.cleanups.append(lambda: cleaned.append("browser closed"))
        return StepOutcome(False, "boom")

    asyncio.run(client.handle_task(FakeWs(), task("open"), {"open": opener}))
    assert cleaned == ["browser closed"]


# --- one connection
def test_the_connection_starts_by_reporting_what_this_pc_can_do() -> None:
    ws = FakeWs()
    asyncio.run(client.serve(ws, {"open_app": ok, "click": ok}))
    assert ws.sent[0] == {"type": "capabilities", "actions": ["click", "open_app"]}


def test_a_cancel_is_heard_while_a_task_is_running() -> None:
    started, release = threading.Event(), threading.Event()

    def slow(_a, _c):
        started.set()
        release.wait(5)
        return StepOutcome(True, "done")

    ws = FakeWs()

    async def incoming():
        yield json.dumps(task("slow", "later"))
        await asyncio.to_thread(started.wait, 5)
        yield json.dumps({"type": "cancel", "task_id": "t1"})
        release.set()
        for _ in range(200):
            if any(m["type"] == "result" for m in ws.sent):
                break
            await asyncio.sleep(0.02)

    ws._incoming = incoming
    asyncio.run(client.serve(ws, {"slow": slow, "later": ok}))
    result = ws.sent[-1]
    assert result["type"] == "result" and result["status"] == "partial" and "Stopped" in result["error"]
    assert ("step", 1, "skipped") in kinds(ws)
    assert not any(m.get("index") == 1 and m.get("status") == "running" for m in ws.sent)


def test_a_cancel_for_an_unknown_task_is_ignored() -> None:
    async def incoming():
        yield json.dumps({"type": "cancel", "task_id": "nope"})

    ws = FakeWs(incoming)
    asyncio.run(client.serve(ws, {"a": ok}))
    assert [m["type"] for m in ws.sent] == ["capabilities"]


def test_a_second_task_while_busy_is_refused_not_queued() -> None:
    started, release = threading.Event(), threading.Event()

    def slow(_a, _c):
        started.set()
        release.wait(5)
        return StepOutcome(True)

    ws = FakeWs()

    async def incoming():
        yield json.dumps(task("slow", task_id="one"))
        await asyncio.to_thread(started.wait, 5)
        yield json.dumps(task("slow", task_id="two"))
        release.set()
        for _ in range(200):
            if sum(m["type"] == "result" for m in ws.sent) == 2:
                break
            await asyncio.sleep(0.02)

    ws._incoming = incoming
    asyncio.run(client.serve(ws, {"slow": slow}))
    busy = next(m for m in ws.sent if m["type"] == "result" and m["task_id"] == "two")
    assert busy["status"] == "failed" and "busy" in busy["error"]
    assert next(m for m in ws.sent if m["type"] == "result" and m["task_id"] == "one")["status"] == "completed"


def test_losing_the_connection_stops_the_running_task_before_its_next_step() -> None:
    started, release = threading.Event(), threading.Event()
    ran: list[str] = []

    def first(_a, _c):
        started.set()
        release.wait(5)
        ran.append("first")
        return StepOutcome(True)

    def second(_a, _c):
        ran.append("second")
        return StepOutcome(True)

    async def incoming():
        yield json.dumps(task("first", "second"))
        await asyncio.to_thread(started.wait, 5)

    ws = FakeWs(incoming, end_with=websockets.exceptions.ConnectionClosedError(None, None))

    async def go():
        loop = asyncio.get_running_loop()
        loop.call_later(0.2, release.set)
        with pytest.raises(websockets.exceptions.ConnectionClosed):
            await client.serve(ws, {"first": first, "second": second})

    asyncio.run(go())
    assert ran == ["first"]  # the PC stopped acting once the phone could no longer be told


def test_a_ping_is_answered() -> None:
    async def incoming():
        yield json.dumps({"type": "ping"})

    ws = FakeWs(incoming)
    asyncio.run(client.serve(ws, {}))
    assert {"type": "pong"} in ws.sent


def test_garbage_messages_are_ignored() -> None:
    async def incoming():
        yield "not json"
        yield json.dumps({"type": "task"})  # no id

    ws = FakeWs(incoming)
    asyncio.run(client.serve(ws, {}))
    assert [m["type"] for m in ws.sent] == ["capabilities"]


# --- staying connected
class FakeConnect:
    """Each call returns the next scripted connection (or raises the next scripted error)."""

    def __init__(self, *script) -> None:
        self.script = list(script)
        self.calls: list[dict] = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return _Ctx(item)


class _Ctx:
    def __init__(self, ws: FakeWs) -> None:
        self.ws = ws

    async def __aenter__(self):
        return self.ws

    async def __aexit__(self, *exc):
        return False


def closed(code: int) -> websockets.exceptions.ConnectionClosedError:
    return websockets.exceptions.ConnectionClosedError(Close(code, ""), None)


def rejected(status: int) -> websockets.exceptions.InvalidStatus:
    return websockets.exceptions.InvalidStatus(Response(status, "x", Headers(), b""))


@pytest.fixture
def creds(monkeypatch, tmp_path):
    monkeypatch.setattr(client, "CREDENTIALS_FILE", tmp_path / "agent.json")
    client.save_credentials("http://api", "agent-1", "device-secret")


def drive(connect: FakeConnect, **kw):
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    async def go():
        await client.run_client("http://api", "PC", "HOST", connect=connect, sleep=fake_sleep, executors={"a": ok}, jitter=lambda: 0.0, **kw)

    return go, sleeps


def test_it_reconnects_with_growing_waits_and_resets_after_a_good_connection(creds) -> None:
    connect = FakeConnect(
        OSError("network down"),
        OSError("network down"),
        FakeWs(end_with=closed(1006)),  # connected, then dropped
        OSError("still down"),
        rejected(403),  # ends the test: refused for good
    )
    go, sleeps = drive(connect)
    with pytest.raises(client.RejectedByBackend):
        asyncio.run(go())
    assert sleeps == [1.0, 2.0, 1.0, 2.0]  # the wait started over after the successful connection


def test_waits_stop_growing_at_the_cap(creds) -> None:
    connect = FakeConnect(*[OSError("down")] * 8, rejected(404))
    go, sleeps = drive(connect)
    with pytest.raises(client.RejectedByBackend):
        asyncio.run(go())
    assert sleeps[:5] == [1.0, 2.0, 4.0, 8.0, 16.0]
    assert max(sleeps) == client.MAX_BACKOFF_SECONDS


def test_the_device_token_goes_in_a_header_never_the_url(creds) -> None:
    connect = FakeConnect(rejected(403))
    go, _ = drive(connect)
    with pytest.raises(client.RejectedByBackend):
        asyncio.run(go())
    call = connect.calls[0]
    assert call["url"] == "ws://api/api/v1/agents/agent-1/ws"
    assert "device-secret" not in call["url"]
    assert call["additional_headers"] == {"Authorization": "Bearer device-secret"}


@pytest.mark.parametrize("code", [4401, 4403, 4404])
def test_being_removed_stops_reconnecting(creds, code: int) -> None:
    go, sleeps = drive(FakeConnect(FakeWs(end_with=closed(code))))
    with pytest.raises(client.RejectedByBackend, match="removed"):
        asyncio.run(go())
    assert sleeps == []


@pytest.mark.parametrize("status", [401, 403, 404])
def test_a_refused_handshake_stops_reconnecting(creds, status: int) -> None:
    go, sleeps = drive(FakeConnect(rejected(status)))
    with pytest.raises(client.RejectedByBackend):
        asyncio.run(go())
    assert sleeps == []


def test_a_server_error_during_the_handshake_is_retried(creds) -> None:
    go, sleeps = drive(FakeConnect(rejected(502), rejected(403)))
    with pytest.raises(client.RejectedByBackend):
        asyncio.run(go())
    assert sleeps == [1.0]


def test_a_backend_restart_close_code_is_retried(creds) -> None:
    go, sleeps = drive(FakeConnect(FakeWs(end_with=closed(1012)), rejected(403)))
    with pytest.raises(client.RejectedByBackend):
        asyncio.run(go())
    assert sleeps == [1.0]


def test_jitter_is_added_to_each_wait(creds) -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    async def go():
        await client.run_client(
            "http://api", "PC", "HOST", connect=FakeConnect(OSError("x"), rejected(403)), sleep=fake_sleep,
            executors={}, jitter=lambda: 0.25,
        )  # fmt: skip

    with pytest.raises(client.RejectedByBackend):
        asyncio.run(go())
    assert sleeps == [1.25]
