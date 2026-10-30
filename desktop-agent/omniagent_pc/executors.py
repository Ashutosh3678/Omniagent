"""The executors behind each plan action. Each returns what should now be on screen, if anything,
and the plan runner confirms it (see plan_runner)."""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from typing import Any

from omniagent_pc import apps
from omniagent_pc.drivers import (
    BrowserDriver,
    ClaudeCodeDriver,
    DriverUnavailable,
    NotepadDriver,
    Result,
    WindowDriver,
    page_host,
)
from omniagent_pc.plan_runner import Executor, RunContext, StepOutcome


def _outcome(result: Result, expected: str | None = None) -> StepOutcome:
    return StepOutcome(result.ok, result.detail, expected if result.ok else None, retry=result.retry)


def _need_app(ctx: RunContext) -> StepOutcome | None:
    return None if ctx.driver is not None else StepOutcome(False, "No app is open")


def _open_browser(ctx: RunContext) -> BrowserDriver:
    driver = BrowserDriver.open()
    # close() keeps the window; it is still registered so cleanup always retains Playwright.
    ctx.cleanups.append(driver.close)
    ctx.driver = driver
    return driver


def open_app(action: dict[str, Any], ctx: RunContext) -> StepOutcome:
    """Opens an app the owner has set up on this PC. The app list and folders are re-read from the
    PC's own settings now, so what was true when the agent connected is not simply trusted."""
    app = action.get("app")
    config = apps.load_config()
    spec = apps.app_specs(config).get(str(app))
    if spec is None:
        return StepOutcome(False, f"{app!r} is not set up on this PC")

    if spec.kind == "notepad":
        driver, result = NotepadDriver.open()
        if driver is not None:
            ctx.driver = driver
        return _outcome(result, expected="notepad")  # the window title says so
    if spec.kind == "browser":
        try:
            _open_browser(ctx)
        except DriverUnavailable as exc:
            return StepOutcome(False, str(exc))
        return StepOutcome(True, "Opened the browser")
    if spec.kind == "claude_code":
        name = str(action.get("workspace") or "")
        folder = apps.folder_paths(config).get(name)
        if folder is None:
            return StepOutcome(False, f"No folder called {name!r} is set up on this PC")
        driver, result = ClaudeCodeDriver.start(folder)
        if driver is not None:
            ctx.driver = driver
        return _outcome(result)  # a terminal's text cannot be read back, so there is nothing to compare
    driver, result = WindowDriver.open([spec.exe], spec.label, title_hint=spec.title_hint)
    if driver is not None:
        ctx.driver = driver
    return _outcome(result)


def type_text(action: dict[str, Any], ctx: RunContext) -> StepOutcome:
    if (missing := _need_app(ctx)) is not None:
        return missing
    text = str(action.get("text", ""))
    # Only drivers that can read their window back (Notepad, the browser) have typing checked on screen.
    expected = text if getattr(ctx.driver, "verifies_typing", True) else None
    return _outcome(ctx.driver.type_text(text), expected=expected)


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
