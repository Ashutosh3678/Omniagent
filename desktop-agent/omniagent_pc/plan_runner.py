"""Runs a validated plan one step at a time. Pure logic: no UI libraries are imported here."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

logger = logging.getLogger(__name__)

PlanStatus = Literal["completed", "partial", "failed"]


@dataclass
class StepOutcome:
    ok: bool
    detail: str = ""


@dataclass
class RunContext:
    """State shared by the steps of one plan (the open window, the last screenshot...)."""

    session: Any = None
    screenshot_path: str | None = None
    observed_text: str = ""


Executor = Callable[[dict[str, Any], RunContext], StepOutcome]
Report = Callable[[int, str, str], None]


@dataclass
class PlanOutcome:
    status: PlanStatus
    summary: str
    error: str = ""
    results: list[tuple[int, str, str]] = field(default_factory=list)


def run_plan(
    plan: list[dict[str, Any]],
    executors: dict[str, Executor],
    context: RunContext,
    report: Report,
    should_stop: Callable[[], bool] = lambda: False,
) -> PlanOutcome:
    """Executes steps in order and stops at the first failure.

    `report(index, status, detail)` is called with running/success/failed/skipped.
    Anything the agent has no executor for is refused, never guessed at.
    """
    results: list[tuple[int, str, str]] = []
    done = 0

    def finish_rest(start: int) -> None:
        for later in plan[start:]:
            report(later["index"], "skipped", "")
            results.append((later["index"], "skipped", ""))

    for position, step in enumerate(plan):
        index = step["index"]
        action = step.get("action") or {}
        action_type = action.get("type")

        if should_stop():
            finish_rest(position)
            return _outcome(done, len(plan), "Stopped before finishing", results)

        executor = executors.get(action_type)
        if executor is None:
            detail = f"This PC cannot run {action_type!r}"
            report(index, "failed", detail)
            results.append((index, "failed", detail))
            finish_rest(position + 1)
            return _outcome(done, len(plan), detail, results)

        report(index, "running", "")
        try:
            outcome = executor(action, context)
        except Exception as exc:  # noqa: BLE001 - UI automation fails in many ways
            logger.exception("Step %s (%s) crashed", index, action_type)
            outcome = StepOutcome(False, f"Unexpected error: {exc}")

        if outcome.ok:
            report(index, "success", outcome.detail)
            results.append((index, "success", outcome.detail))
            done += 1
            continue

        report(index, "failed", outcome.detail)
        results.append((index, "failed", outcome.detail))
        finish_rest(position + 1)
        return _outcome(done, len(plan), outcome.detail, results)

    return PlanOutcome("completed", f"Completed {len(plan)} step(s)", results=results)


def _outcome(done: int, total: int, error: str, results: list[tuple[int, str, str]]) -> PlanOutcome:
    status: PlanStatus = "partial" if done else "failed"
    return PlanOutcome(status, f"Completed {done} of {total} step(s)", error, results)
