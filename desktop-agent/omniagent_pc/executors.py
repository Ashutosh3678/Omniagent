"""The executors behind each plan action. Each returns what should now be on screen, if anything,
and the plan runner confirms it (see plan_runner)."""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from typing import Any

from omniagent_pc.drivers import BrowserDriver, DriverUnavailable, NotepadDriver, Result, page_host
from omniagent_pc.plan_runner import Executor, RunContext, StepOutcome


def _outcome(result: Result, expected: str | None = None) -> StepOutcome:
    return StepOutcome(result.ok, result.detail, expected if result.ok else None, retry=result.retry)


def _need_app(ctx: RunContext) -> StepOutcome | None:
    return None if ctx.driver is not None else StepOutcome(False, "No app is open")


def _open_browser(ctx: RunContext) -> BrowserDriver:
    driver = BrowserDriver.open()
    ctx.cleanups.append(driver.close)
    ctx.driver = driver
    return driver


def open_app(action: dict[str, Any], ctx: RunContext) -> StepOutcome:
    app = action.get("app")
    if app == "notepad":
        driver, result = NotepadDriver.open()
        if driver is not None:
            ctx.driver = driver
        return _outcome(result, expected="notepad")  # the window title says so
    if app == "browser":
        try:
            _open_browser(ctx)
        except DriverUnavailable as exc:
            return StepOutcome(False, str(exc))
        return StepOutcome(True, "Opened the browser")
    return StepOutcome(False, f"Cannot open {app!r}")


def type_text(action: dict[str, Any], ctx: RunContext) -> StepOutcome:
    if (missing := _need_app(ctx)) is not None:
        return missing
    text = str(action.get("text", ""))
    return _outcome(ctx.driver.type_text(text), expected=text)


def press_key(action: dict[str, Any], ctx: RunContext) -> StepOutcome:
    if (missing := _need_app(ctx)) is not None:
        return missing
    return _outcome(ctx.driver.press_key(str(action.get("key", "")), list(action.get("modifiers") or [])))


def click(action: dict[str, Any], ctx: RunContext) -> StepOutcome:
    if (missing := _need_app(ctx)) is not None:
        return missing
    return _outcome(ctx.driver.click(str(action.get("target", ""))))


def scroll(action: dict[str, Any], ctx: RunContext) -> StepOutcome:
    if (missing := _need_app(ctx)) is not None:
        return missing
    return _outcome(ctx.driver.scroll(str(action.get("direction", "down")), int(action.get("amount", 3))))


def browser_navigate(action: dict[str, Any], ctx: RunContext) -> StepOutcome:
    url = str(action.get("url", ""))
    try:
        driver = ctx.driver if isinstance(ctx.driver, BrowserDriver) else _open_browser(ctx)
    except DriverUnavailable as exc:
        return StepOutcome(False, str(exc))
    return _outcome(driver.navigate(url), expected=page_host(url))


def wait(action: dict[str, Any], ctx: RunContext) -> StepOutcome:
    seconds = min(float(action.get("seconds", 0)), 10.0)
    time.sleep(seconds)
    return StepOutcome(True, f"Waited {seconds:g}s")


def screenshot(action: dict[str, Any], ctx: RunContext) -> StepOutcome:
    from omniagent_pc.screenshot import capture_screen

    path, result = capture_screen()
    if path is not None:
        ctx.screenshot_path = str(Path(path))
    return StepOutcome(result.status == "Success", result.detail)


def _installed(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def build_executors() -> dict[str, Executor]:
    """Exactly the actions this PC can run right now. The agent reports these keys to the backend,
    which only plans (and only dispatches) what is listed, so nothing is promised that cannot be done."""
    executors: dict[str, Executor] = {
        "open_app": open_app,
        "type_text": type_text,
        "press_key": press_key,
        "click": click,
        "wait": wait,
        "screenshot": screenshot,
    }
    if _installed("pyautogui"):
        executors["scroll"] = scroll
    if _installed("playwright"):
        executors["browser_navigate"] = browser_navigate
    return executors
