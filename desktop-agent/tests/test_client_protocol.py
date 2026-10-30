from __future__ import annotations

import asyncio
import json

from omniagent_pc import client
from omniagent_pc.plan_runner import StepOutcome


class FakeWs:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))


def run(message: dict, executors: dict) -> list[dict]:
    ws = FakeWs()
    asyncio.run(client.handle_task(ws, message, executors))
    return ws.sent


def task(*types: str) -> dict:
    return {"type": "task", "task_id": "t1", "plan": [{"index": i, "action": {"type": t}} for i, t in enumerate(types)]}


def test_reports_each_step_then_the_result_in_order() -> None:
    ok = lambda a, c: StepOutcome(True, "fine")  # noqa: E731
    sent = run(task("a", "b"), {"a": ok, "b": ok})
    kinds = [(m["type"], m.get("index"), m.get("status")) for m in sent]
    assert kinds == [
        ("ack", None, None),
        ("step", 0, "running"),
        ("step", 0, "success"),
        ("step", 1, "running"),
        ("step", 1, "success"),
        ("result", None, "completed"),
    ]


def test_failed_step_gives_a_partial_result() -> None:
    sent = run(task("a", "b", "c"), {"a": lambda a, c: StepOutcome(True), "b": lambda a, c: StepOutcome(False, "nope"), "c": lambda a, c: StepOutcome(True)})
    assert sent[-1]["status"] == "partial"
    assert sent[-1]["error"] == "nope"
    assert {"type": "step", "task_id": "t1", "index": 2, "status": "skipped", "detail": ""} in sent


def test_unknown_action_is_refused() -> None:
    sent = run(task("shell"), {})
    assert sent[-1]["status"] == "failed"
    assert "shell" in sent[-1]["error"]


def test_malformed_or_empty_plans_fail_without_running_anything() -> None:
    for plan in (None, [], "open notepad", [{"index": 0}], [{"action": {"type": "wait"}}]):
        sent = run({"type": "task", "task_id": "t1", "plan": plan}, {"wait": lambda a, c: StepOutcome(True)})
        assert [m["type"] for m in sent] == ["ack", "result"]
        assert sent[-1]["status"] == "failed"
