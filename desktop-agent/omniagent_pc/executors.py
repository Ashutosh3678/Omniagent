"""The real Windows executors behind each plan action."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from omniagent_pc import actions
from omniagent_pc.plan_runner import Executor, RunContext, StepOutcome
from omniagent_pc.screenshot import capture_screen


def _outcome(result) -> StepOutcome:
    return StepOutcome(result.status == "Success", result.detail)


def open_app(action: dict[str, Any], ctx: RunContext) -> StepOutcome:
    app = action.get("app")
    if app != "notepad":
        return StepOutcome(False, f"Cannot open {app!r}")
    session, result = actions.launch_notepad()
    if session is not None:
        ctx.session = session
    return _outcome(result)


def type_text(action: dict[str, Any], ctx: RunContext) -> StepOutcome:
    if ctx.session is None:
        return StepOutcome(False, "No app is open")
    observed, result = actions.append_text(ctx.session, str(action.get("text", "")))
    ctx.observed_text = observed or ctx.observed_text
    return _outcome(result)


def press_key(action: dict[str, Any], ctx: RunContext) -> StepOutcome:
    if ctx.session is None:
        return StepOutcome(False, "No app is open")
    return _outcome(actions.press_key(ctx.session, str(action.get("key", "")), list(action.get("modifiers") or [])))


def wait(action: dict[str, Any], ctx: RunContext) -> StepOutcome:
    seconds = min(float(action.get("seconds", 0)), 10.0)
    time.sleep(seconds)
    return StepOutcome(True, f"Waited {seconds:g}s")


def screenshot(action: dict[str, Any], ctx: RunContext) -> StepOutcome:
    path, result = capture_screen()
    if path is not None:
        ctx.screenshot_path = str(Path(path))
    return _outcome(result)


def build_executors() -> dict[str, Executor]:
    """Exactly the actions this agent can run. The backend's EXECUTABLE_ACTIONS must match."""
    return {
        "open_app": open_app,
        "type_text": type_text,
        "press_key": press_key,
        "wait": wait,
        "screenshot": screenshot,
    }
