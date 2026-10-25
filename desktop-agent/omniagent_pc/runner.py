"""Orchestrate the Phase 1 Notepad demo and report Success or Failed."""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from omniagent_pc.actions import launch_notepad, require_windows, type_message
from omniagent_pc.models import StepResult, TaskResult
from omniagent_pc.screenshot import capture_screen
from omniagent_pc.verify import verify_task

DEFAULT_MESSAGE = "Hello from OmniAgent"


def _enable_dpi_awareness() -> None:
    """Reduce blurry screenshots and mismatched window coordinates on scaled displays."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def run_phase1_task(
    message: str = DEFAULT_MESSAGE,
    output_dir: Path | None = None,
) -> TaskResult:
    """Open Notepad, type a message, screenshot the screen, and verify."""
    steps: list[StepResult] = []
    screenshot_path: Path | None = None
    observed_text = ""

    try:
        require_windows()
    except RuntimeError as exc:
        failed = StepResult("Open Notepad", "Failed", str(exc))
        return TaskResult(status="Failed", message=str(exc), steps=[failed])

    _enable_dpi_awareness()

    try:
        session, launch_result = launch_notepad()
        steps.append(launch_result)
        if launch_result.status == "Failed" or session is None:
            return _failed("Could not open Notepad", steps, screenshot_path, observed_text)

        observed_text, type_result = type_message(session, message)
        steps.append(type_result)

        screenshot_path, shot_result = capture_screen(output_dir)
        steps.append(shot_result)

        verify_result = verify_task(session, message, screenshot_path, observed_text)
        steps.append(verify_result)
    except Exception as exc:  # noqa: BLE001
        steps.append(StepResult("Verify task", "Failed", f"Unexpected error: {exc}"))
        return _failed(str(exc), steps, screenshot_path, observed_text)

    if any(step.status == "Failed" for step in steps):
        return _failed(
            "One or more Phase 1 steps failed",
            steps,
            screenshot_path,
            observed_text,
        )

    return TaskResult(
        status="Success",
        message="Opened Notepad, typed the message, captured a screenshot, and verified the result",
        steps=steps,
        screenshot_path=str(screenshot_path) if screenshot_path else None,
        observed_text=observed_text,
    )


def format_task_result(result: TaskResult) -> str:
    width = 62
    lines = [
        "=" * width,
        "OmniAgent Phase 1 — Windows PC Agent",
        "=" * width,
    ]
    for index, step in enumerate(result.steps, start=1):
        lines.append(f"[{index}] {step.name:<22} {step.status}")
        if step.detail:
            lines.append(f"    {step.detail}")
    lines.append("-" * width)
    lines.append(f"Task status: {result.status}")
    if result.screenshot_path:
        lines.append(f"Screenshot:  {result.screenshot_path}")
    if result.observed_text:
        lines.append(f"Notepad text: {result.observed_text!r}")
    lines.append("=" * width)
    return "\n".join(lines)


def print_task_result(result: TaskResult) -> None:
    print(format_task_result(result))


def _failed(
    message: str,
    steps: list[StepResult],
    screenshot_path: Path | None,
    observed_text: str,
) -> TaskResult:
    return TaskResult(
        status="Failed",
        message=message,
        steps=steps,
        screenshot_path=str(screenshot_path) if screenshot_path else None,
        observed_text=observed_text or None,
    )


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    message = " ".join(args).strip() or DEFAULT_MESSAGE
    result = run_phase1_task(message=message)
    print_task_result(result)
    return 0 if result.succeeded else 1
