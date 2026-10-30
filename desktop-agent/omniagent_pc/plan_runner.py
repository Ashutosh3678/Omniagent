"""Runs a validated plan one step at a time: observe, act, verify, retry.

Pure logic: no UI libraries are imported here. Drivers, executors and the clock are
injected, so the whole loop is tested without a desktop.

Per step:
  1. Act. If the executor reports failure (nothing happened), act again, up to MAX_ATTEMPTS.
  2. Observe and verify. If the step says what should now be on screen, compare it with
     what is on screen using local hashed embeddings (threshold VERIFY_THRESHOLD). If it does
     not match, observe again after a short wait, up to MAX_ATTEMPTS looks. The action is
     never repeated at this point: typing twice would be worse than not confirming.
  3. A step that acted but could not be confirmed is "unverified" and stops the plan.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from omniagent_pc.embeddings import VERIFY_THRESHOLD, similarity

logger = logging.getLogger(__name__)

PlanStatus = Literal["completed", "partial", "failed"]
MAX_ATTEMPTS = 3
SETTLE_SECONDS = 0.5


@dataclass
class StepOutcome:
    ok: bool
    detail: str = ""
    # What should now be visible. None means there is nothing to compare, so the step is
    # confirmed by the executor alone.
    expected: str | None = None


@dataclass
class RunContext:
    """State shared by the steps of one plan."""

    driver: Any = None  # the open app (Notepad window, browser page...)
    screenshot_path: str | None = None
    # Returns a small JPEG of the screen, or None. Injected by the client.
    capture_jpeg: Callable[[], bytes | None] = lambda: None
    cleanups: list[Callable[[], None]] = field(default_factory=list)

    def observe(self) -> str:
        return self.driver.observe_text() if self.driver is not None else ""

    def cleanup(self) -> None:
        for fn in reversed(self.cleanups):
            try:
                fn()
            except Exception:  # noqa: BLE001
                logger.exception("Cleanup failed")
        self.cleanups.clear()


Executor = Callable[[dict[str, Any], RunContext], StepOutcome]
# report(index, status, detail, screenshot_jpeg)
Report = Callable[[int, str, str, "bytes | None"], None]


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
    sleep: Callable[[float], None] = time.sleep,
) -> PlanOutcome:
    """Executes steps in order and stops at the first one that fails or cannot be confirmed."""
    results: list[tuple[int, str, str]] = []
    acted = 0  # steps that changed something, confirmed or not
    confirmed = 0

    def emit(index: int, status: str, detail: str, shot: bytes | None = None) -> None:
        report(index, status, detail, shot)
        results.append((index, status, detail))

    def skip_rest(start: int) -> None:
        for later in plan[start:]:
            emit(later["index"], "skipped", "")

    def finish(error: str) -> PlanOutcome:
        status: PlanStatus = "partial" if acted else "failed"
        return PlanOutcome(status, f"Completed {confirmed} of {len(plan)} step(s)", error, results)

    for position, step in enumerate(plan):
        index = step["index"]
        action = step.get("action") or {}
        action_type = action.get("type")

        if should_stop():
            skip_rest(position)
            return finish("Stopped before finishing")

        executor = executors.get(action_type)
        if executor is None:
            detail = f"This PC cannot run {action_type!r}"
            emit(index, "failed", detail)
            skip_rest(position + 1)
            return finish(detail)

        report(index, "running", "", None)
        status, detail = _run_step(executor, action, context, should_stop, sleep)
        if status in ("success", "unverified"):
            acted += 1
        if status == "success":
            confirmed += 1
        emit(index, status, detail, _safe_capture(context))
        if status != "success":
            skip_rest(position + 1)
            return finish(detail)

    return PlanOutcome("completed", f"Completed {len(plan)} step(s)", results=results)


def _run_step(
    executor: Executor,
    action: dict[str, Any],
    context: RunContext,
    should_stop: Callable[[], bool],
    sleep: Callable[[float], None],
) -> tuple[str, str]:
    outcome = StepOutcome(False, "Did not run")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            outcome = executor(action, context)
        except Exception as exc:  # noqa: BLE001 - UI automation fails in many ways
            logger.exception("Step %s crashed", action.get("type"))
            outcome = StepOutcome(False, f"Unexpected error: {exc}")
        if outcome.ok:
            break
        if attempt < MAX_ATTEMPTS and not should_stop():
            sleep(SETTLE_SECONDS * attempt)
    if not outcome.ok:
        return "failed", outcome.detail

    if outcome.expected is None:
        return "success", outcome.detail

    score = 0.0
    for look in range(1, MAX_ATTEMPTS + 1):
        try:
            score = similarity(outcome.expected, context.observe())
        except Exception as exc:  # noqa: BLE001
            logger.exception("Could not read the screen")
            return "unverified", f"{outcome.detail}; could not read the screen: {exc}"
        if score >= VERIFY_THRESHOLD:
            return "success", f"{outcome.detail}; confirmed on screen ({score:.2f})"
        if look < MAX_ATTEMPTS and not should_stop():
            sleep(SETTLE_SECONDS * look)
    return "unverified", f"{outcome.detail}; could not confirm it on screen (best match {score:.2f})"


def _safe_capture(context: RunContext) -> bytes | None:
    try:
        return context.capture_jpeg()
    except Exception:  # noqa: BLE001 - a missing thumbnail must never fail a step
        logger.exception("Step screenshot failed")
        return None
