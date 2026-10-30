"""Allowlisted task parser. Rejects anything that is not a known action."""

from __future__ import annotations

import re

from app.models import Action

_NOTEPAD = re.compile(
    r"^\s*open\s+notepad(?:\s+and\s+type\s+(.+))?\s*$",
    re.IGNORECASE,
)


# Which application each action drives. A device may only run actions whose app it is permitted.
ACTION_APP = {"open_notepad": "notepad"}
KNOWN_APPS = frozenset(ACTION_APP.values())


class InvalidActionError(ValueError):
    pass


def parse_instruction(instruction: str) -> Action:
    text = (instruction or "").strip()
    if not text:
        raise InvalidActionError("Instruction is empty")

    match = _NOTEPAD.match(text)
    if match:
        message = (match.group(1) or "Hello from OmniAgent").strip()
        if not message:
            message = "Hello from OmniAgent"
        return Action(type="open_notepad", message=message)

    raise InvalidActionError(
        "Unsupported instruction. Allowed: Open Notepad and type <message>"
    )
