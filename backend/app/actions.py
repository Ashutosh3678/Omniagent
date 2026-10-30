"""Rule-based instruction parser. Used until (and as a fallback for) the LLM planner."""

from __future__ import annotations

import re
from typing import Any

from app.schema import KNOWN_APPS  # noqa: F401  (re-exported for callers)

_NOTEPAD = re.compile(
    r"^\s*open\s+notepad(?:\s+and\s+type\s+(.+))?\s*$",
    re.IGNORECASE,
)


_SIMPLE_APP = re.compile(r"^\s*open\s+(?:ms\s*)?(paint|calculator|calc)\s*$", re.IGNORECASE)


class InvalidActionError(ValueError):
    pass


def plan_from_instruction(instruction: str) -> list[dict[str, Any]]:
    """Turns a plain instruction into raw plan steps, or raises InvalidActionError.

    The result is untrusted until it goes through validation.validate_plan.
    """
    text = (instruction or "").strip()
    if not text:
        raise InvalidActionError("Instruction is empty")

    simple = _SIMPLE_APP.match(text)
    if simple:
        app = "calculator" if simple.group(1).lower() in ("calc", "calculator") else "paint"
        return [{"action": {"type": "open_app", "app": app}, "confidence": 1.0}]

    match = _NOTEPAD.match(text)
    if match:
        steps: list[dict[str, Any]] = [{"action": {"type": "open_app", "app": "notepad"}, "confidence": 1.0}]
        message = (match.group(1) or "").strip()
        if message:
            steps.append({"action": {"type": "type_text", "text": message}, "confidence": 1.0})
        return steps

    raise InvalidActionError("Unsupported instruction. Allowed: Open Notepad and type <message>, Open Paint, Open Calculator")
