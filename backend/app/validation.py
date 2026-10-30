"""Action validation: whitelist, typed parameters, app scope. Fails closed.

A plan is checked step by step. The first step that fails is held back with a
reason, and every step after it is held back too, because later steps assume the
earlier ones happened. Only the clean prefix is ever dispatched.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.models import HeldBack, PlanStep, PlanVerdict
from app.schema import (
    ACTION_TYPES,
    EXECUTABLE_ACTIONS,
    KNOWN_APPS,
    NEEDS_OPEN_APP,
    OpenApp,
    WORKSPACE_APPS,
    app_label,
    action_adapter,
    describe,
)

MAX_STEPS = 20


def _first_error(exc: ValidationError) -> tuple[str, str]:
    error = exc.errors()[0]
    if error["type"] in {"union_tag_invalid", "union_tag_not_found"}:
        return "unknown_action", "Not an action this system knows"
    where = ".".join(str(part) for part in error["loc"][1:]) or "action"
    message = error["msg"].removeprefix("Value error, ")
    return "invalid_parameters", f"{where}: {message}"


def validate_plan(
    raw_steps: list[Any],
    permitted_apps: list[str],
    executable: frozenset[str] | set[str] | None = None,
    available_apps: frozenset[str] | set[str] | None = None,
    workspaces: frozenset[str] | set[str] | None = None,
) -> PlanVerdict:
    """`available_apps` and `workspaces` are what the PC's agent reported; None means "not told"
    (only the built-in apps, and no folders)."""
    can_run = EXECUTABLE_ACTIONS if executable is None else executable
    steps: list[PlanStep] = []
    held: list[HeldBack] = []
    blocked_by: int | None = None
    current_app: str | None = None

    for index, raw in enumerate(raw_steps):
        raw_action = raw.get("action") if isinstance(raw, dict) else None
        raw_dict = raw_action if isinstance(raw_action, dict) else {}

        if blocked_by is not None:
            held.append(HeldBack(index=index, raw=raw_dict, reason="blocked_by_earlier_step", detail=f"Step {blocked_by + 1} was held back"))
            continue

        reason, detail, step = _check(index, raw, raw_action, permitted_apps, can_run, current_app, len(steps), available_apps, workspaces)
        if step is None:
            blocked_by = index
            held.append(HeldBack(index=index, raw=raw_dict, reason=reason, detail=detail))
            continue
        if step.action["type"] == "open_app":
            current_app = step.action["app"]
        elif step.action["type"] == "browser_navigate":
            current_app = "browser"
        steps.append(step)

    confidence = round(sum(s.confidence for s in steps) / len(steps), 3) if steps else None
    return PlanVerdict(steps=steps, held_back=held, confidence=confidence)


def _check(
    index: int,
    raw: Any,
    raw_action: Any,
    permitted_apps: list[str],
    can_run: frozenset[str] | set[str],
    current_app: str | None,
    accepted_so_far: int,
    available_apps: frozenset[str] | set[str] | None = None,
    workspaces: frozenset[str] | set[str] | None = None,
) -> tuple[str, str, PlanStep | None]:
    if accepted_so_far >= MAX_STEPS:
        return "plan_too_long", f"Plans are limited to {MAX_STEPS} steps", None
    if not isinstance(raw, dict) or not isinstance(raw_action, dict):
        return "invalid_parameters", "Step must contain an action object", None

    confidence = raw.get("confidence", 1.0)
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        return "invalid_parameters", "confidence must be a number from 0 to 1", None

    action_type = raw_action.get("type")
    if action_type not in ACTION_TYPES:
        return "unknown_action", f"Unknown action {action_type!r}", None

    try:
        action = action_adapter.validate_python(raw_action)
    except ValidationError as exc:
        reason, detail = _first_error(exc)
        return reason, detail, None

    if action.type not in can_run:
        return "not_supported", f"{action.type} is not available on this PC", None

    if isinstance(action, OpenApp):
        label = app_label(action.app)
        if action.app not in (KNOWN_APPS if available_apps is None else available_apps):
            return "unknown_app", f"{label} is not set up on this PC", None
        if action.app not in permitted_apps:
            return "app_not_permitted", f"{label} is turned off for this PC. Turn it on in Devices.", None
        if action.app in WORKSPACE_APPS:
            if not action.workspace:
                return "invalid_parameters", f"workspace: choose which folder to open {label} in", None
            if action.workspace not in (workspaces or ()):
                return "unknown_workspace", f"No folder called {action.workspace!r} is set up on this PC", None
        elif action.workspace:
            return "invalid_parameters", f"workspace: {label} does not take a folder", None
    elif action.type == "browser_navigate":
        if "browser" not in permitted_apps:
            return "app_not_permitted", "This PC is not allowed to use the browser", None
    elif action.type in NEEDS_OPEN_APP and current_app is None:
        return "no_app_open", "Open an app before using it", None

    step = PlanStep(
        index=index,
        action=action.model_dump(mode="json", exclude_none=True),
        description=describe(action),
        confidence=float(confidence),
    )
    return "", "", step
