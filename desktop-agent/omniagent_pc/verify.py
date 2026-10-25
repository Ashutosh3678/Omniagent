"""Confirm that Notepad shows the expected text and a screenshot was saved."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from omniagent_pc.actions import NotepadSession, notepad_is_visible, read_notepad_text
from omniagent_pc.models import StepResult
from omniagent_pc.screenshot import screenshot_looks_valid


def verify_task(
    session: Optional[NotepadSession],
    expected_message: str,
    screenshot_path: Optional[Path],
    observed_text: str = "",
) -> StepResult:
    failures: list[str] = []

    if session is None or not notepad_is_visible(session):
        failures.append("Notepad window is not visible")
    else:
        current_text = observed_text or read_notepad_text(session)
        if expected_message not in current_text:
            failures.append(
                f"Notepad does not contain {expected_message!r} (saw {current_text!r})"
            )

    if screenshot_path is None:
        failures.append("No screenshot path was recorded")
    elif not screenshot_looks_valid(screenshot_path):
        failures.append(f"Screenshot is missing or invalid: {screenshot_path}")

    if failures:
        return StepResult("Verify task", "Failed", "; ".join(failures))

    return StepResult(
        "Verify task",
        "Success",
        "Notepad text and screenshot were confirmed",
    )
