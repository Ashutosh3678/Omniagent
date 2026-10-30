"""Drivers: one per kind of app the agent can operate.

A driver exposes the same few operations (`type_text`, `press_key`, `click`, `scroll`,
`observe_text`) so the executors and the verify loop do not care whether they are
talking to Notepad or a web page. Windows and browser libraries are imported only
when a driver is used, so this module loads (and is tested) anywhere.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from omniagent_pc.embeddings import VERIFY_THRESHOLD, similarity

logger = logging.getLogger(__name__)


@dataclass
class Result:
    ok: bool
    detail: str = ""
    # True only when a failure means nothing happened, so trying again cannot do it twice.
    retry: bool = False


class DriverUnavailable(Exception):
    """The libraries or programs this driver needs are not installed on this PC."""


# --------------------------------------------------------------------------- Notepad
_CLICKABLE = {"Button", "MenuItem", "TabItem", "CheckBox", "RadioButton", "Hyperlink", "ListItem", "TreeItem", "SplitButton"}


def click_best_match(window: Any, target: str, where: str) -> Result:
    """Clicks the control in `window` whose label best matches `target` (local embeddings, no model)."""
    try:
        window.set_focus()
        best_score, best = 0.0, None
        for control in window.descendants():
            label = (control.window_text() or "").strip()
            if not label or len(label) > 80:
                continue
            try:
                kind = control.element_info.control_type
            except Exception:  # noqa: BLE001 - the win32 backend has no control types
                kind = None
            if kind is not None and kind not in _CLICKABLE:
                continue
            score = similarity(target, label)
            if score > best_score:
                best_score, best = score, (control, label)
        if best is None or best_score < VERIFY_THRESHOLD:
            return Result(False, f"Could not find {target!r} in {where}", retry=True)
        best[0].click_input()
        return Result(True, f"Clicked {best[1]!r}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Click failed")
        return Result(False, str(exc))


def scroll_window(window: Any, direction: str, amount: int) -> Result:
    try:
        import pyautogui

        window.set_focus()
        rect = window.rectangle()
        pyautogui.moveTo((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
        pyautogui.scroll(amount if direction == "up" else -amount)
        return Result(True, f"Scrolled {direction} {amount}")
    except Exception as exc:  # noqa: BLE001 - includes pyautogui's corner failsafe
        logger.exception("Scroll failed")
        return Result(False, str(exc))


class NotepadDriver:
    name = "notepad"

    def __init__(self, session: Any) -> None:
        self.session = session

    @classmethod
    def open(cls) -> tuple[NotepadDriver | None, Result]:
        from omniagent_pc import actions

        session, result = actions.launch_notepad()
        if session is None:
            return None, Result(False, result.detail)
        driver = cls(session)
        blank = driver._ensure_blank_page()
        if not blank.ok:
            return None, blank
        return driver, Result(True, result.detail)

    def _ensure_blank_page(self) -> Result:
        """Windows 11 Notepad brings back the last session's unsaved text. Never type into or over
        someone's old text: start a new tab instead, and give up if that page is not blank."""
        from omniagent_pc import actions

        if not actions.read_notepad_text(self.session).strip():
            return Result(True)
        edit = actions._find_document_control(self.session.spec(), self.session.backend)
        if edit is None:
            return Result(False, "Notepad opened with older text and its text area could not be found")
        edit.type_keys("^n", pause=0.05)
        time.sleep(0.8)
        if actions.read_notepad_text(self.session).strip():
            return Result(False, "Notepad opened with older unsaved text and a blank page could not be started")
        return Result(True)

    def observe_text(self) -> str:
        from omniagent_pc import actions

        title = ""
        try:
            title = self.session.spec().window_text()
        except Exception:  # noqa: BLE001
            logger.debug("Could not read the Notepad title", exc_info=True)
        return f"{title}\n{actions.read_notepad_text(self.session)}"

    def type_text(self, text: str) -> Result:
        from omniagent_pc import actions

        _, result = actions.append_text(self.session, text)
        # Only "no text area" means nothing was typed; any other failure may have typed some.
        return Result(result.status == "Success", result.detail, retry="text area" in result.detail)

    def press_key(self, key: str, modifiers: list[str]) -> Result:
        from omniagent_pc import actions

        result = actions.press_key(self.session, key, modifiers)
        return Result(result.status == "Success", result.detail, retry="text area" in result.detail)

    def click(self, target: str) -> Result:
        """Clicks the control in the Notepad window whose label best matches `target`."""
        return click_best_match(self.session.spec(), target, "Notepad")

    def scroll(self, direction: str, amount: int) -> Result:
        return scroll_window(self.session.spec(), direction, amount)

    def close(self) -> None:  # the user keeps the window they asked for
        return None


# --------------------------------------------------------------------------- any other window
# Windows' key names for the keys the backend allows (same table the Notepad driver uses).
_SENDKEYS = {
    "enter": "{ENTER}", "tab": "{TAB}", "escape": "{ESC}", "backspace": "{BACKSPACE}", "delete": "{DELETE}",
    "up": "{UP}", "down": "{DOWN}", "left": "{LEFT}", "right": "{RIGHT}", "home": "{HOME}", "end": "{END}",
    "pageup": "{PGUP}", "pagedown": "{PGDN}",
}  # fmt: skip
_CONSOLE_CLASSES = frozenset({"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS"})


def escape_send_keys(text: str) -> str:
    """Escapes the characters pywinauto treats as keyboard modifiers."""
    return "".join("{" + char + "}" if char in "+^%~{}()" else char for char in text)


def visible_windows() -> dict[int, tuple[str, str]]:
    """Every visible top-level window: handle -> (title, class name)."""
    from pywinauto import Desktop

    found: dict[int, tuple[str, str]] = {}
    try:
        for window in Desktop(backend="uia").windows():
            try:
                if window.is_visible():
                    found[int(window.handle)] = (window.window_text() or "", window.class_name() or "")
            except Exception:  # noqa: BLE001 - windows come and go while we look
                continue
    except Exception:  # noqa: BLE001
        logger.debug("Could not list windows", exc_info=True)
    return found


def choose_window(
    candidates: dict[int, tuple[str, str]],
    hint: str | None = None,
    classes: frozenset[str] | None = None,
) -> int | None:
    """Picks the window that is most likely the app we just started. Pure, so it can be tested."""
    usable = {
        handle: (title, cls)
        for handle, (title, cls) in candidates.items()
        if (title.strip() or (classes and cls in classes)) and (classes is None or cls in classes)
    }
    if hint:
        wanted = hint.lower()
        for handle, (title, _cls) in usable.items():
            if wanted in title.lower():
                return handle
        return None
    return next(iter(usable), None)


def wait_for_window(
    before: dict[int, tuple[str, str]],
    hint: str | None,
    classes: frozenset[str] | None,
    timeout: float,
    snapshot: Any = None,
    sleep: Any = time.sleep,
    clock: Any = time.monotonic,
) -> int | None:
    """Waits for a new window to appear after starting a program.

    Single-instance apps (Calculator) may just bring their existing window forward, so near the end
    an already-open window that matches the title hint is accepted too."""
    snapshot = snapshot or visible_windows
    start = clock()
    while True:
        elapsed = clock() - start
        current = snapshot()
        fresh = {h: v for h, v in current.items() if h not in before}
        found = choose_window(fresh, hint, classes)
        if found is None and hint and elapsed >= timeout * 0.5:
            found = choose_window(current, hint, classes)
        if found is not None:
            return found
        if elapsed >= timeout:
            return None
        sleep(0.4)


class WindowDriver:
    """Drives any ordinary desktop window (Paint, Calculator, programs the owner added)."""

    name = "window"
    # Typed text may not show up as text on screen (a calculator, a drawing program), so typing is not
    # checked against the screen the way it is for Notepad.
    verifies_typing = False

    def __init__(self, handle: int, label: str) -> None:
        self.handle = handle
        self.label = label

    @classmethod
    def open(
        cls,
        command: list[str],
        label: str,
        *,
        title_hint: str | None = None,
        classes: frozenset[str] | None = None,
        cwd: str | None = None,
        new_console: bool = False,
        timeout: float = 20.0,
    ) -> tuple[WindowDriver | None, Result]:
        import subprocess

        before = visible_windows()
        try:
            if new_console:
                subprocess.Popen(command, cwd=cwd, creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            return None, Result(False, f"Could not start {label}: {exc}")

        handle = wait_for_window(before, title_hint, classes, timeout)
        if handle is None:
            return None, Result(False, f"{label} was started but its window did not appear")
        driver = cls(handle, label)
        try:
            driver._spec().set_focus()
        except Exception:  # noqa: BLE001 - it is open; focus will be set again before every action
            logger.debug("Could not focus %s", label, exc_info=True)
        return driver, Result(True, f"Opened {label}")

    def _spec(self) -> Any:
        from pywinauto import Desktop

        return Desktop(backend="uia").window(handle=self.handle)

    def _focused(self) -> Any:
        spec = self._spec()
        spec.set_focus()
        time.sleep(0.3)
        return spec

    def observe_text(self) -> str:
        parts: list[str] = []
        try:
            spec = self._spec()
            parts.append(spec.window_text() or "")
            for control in spec.descendants()[:300]:
                text = (control.window_text() or "").strip()
                if text and len(text) < 200:
                    parts.append(text)
        except Exception:  # noqa: BLE001
            logger.debug("Could not read %s", self.label, exc_info=True)
        return "\n".join(parts)

    def _typed(self, text: str) -> str:
        return text

    def type_text(self, text: str) -> Result:
        try:
            self._focused().type_keys(escape_send_keys(self._typed(text)), with_spaces=True, with_newlines=True, pause=0.02)
            return Result(True, f"Typed {text!r}")
        except Exception as exc:  # noqa: BLE001 - some keys may already have gone in, so never repeat this
            logger.exception("Typing failed")
            return Result(False, str(exc).splitlines()[0] if str(exc) else "Typing failed")

    def press_key(self, key: str, modifiers: list[str]) -> Result:
        name = _SENDKEYS.get(key, key if len(key) == 1 else None)
        if name is None:
            return Result(False, f"Key {key!r} is not supported")
        prefix = ("^" if "ctrl" in modifiers else "") + ("+" if "shift" in modifiers else "")
        try:
            self._focused().type_keys(prefix + name, pause=0.02)
            return Result(True, f"Pressed {prefix}{name}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Key press failed")
            return Result(False, str(exc).splitlines()[0] if str(exc) else "Key press failed")

    def click(self, target: str) -> Result:
        return click_best_match(self._spec(), target, self.label)

    def scroll(self, direction: str, amount: int) -> Result:
        return scroll_window(self._spec(), direction, amount)

    def close(self) -> None:  # the user keeps the window they asked for
        return None


class ClaudeCodeDriver(WindowDriver):
    """Claude Code in a terminal window, started inside a folder the owner chose on this PC.

    Claude Code is started exactly as `claude` would be, so its own permission questions still appear;
    nothing here switches those off. What is typed goes to Claude Code's prompt, not to a shell."""

    name = "claude_code"

    @classmethod
    def start(cls, folder: Path) -> tuple[ClaudeCodeDriver | None, Result]:
        import shutil

        if shutil.which("claude") is None:
            return None, Result(False, "Claude Code is not installed on this PC (the 'claude' command was not found)")
        if not folder.is_dir():
            return None, Result(False, f"The folder {folder} no longer exists")
        driver, result = cls.open(
            ["cmd.exe", "/k", "claude"],
            "Claude Code",
            classes=_CONSOLE_CLASSES,
            cwd=str(folder),
            new_console=True,
            timeout=25.0,
        )
        if driver is not None:
            result = Result(True, f"Opened Claude Code in {folder.name}")
        return driver, result

    def _typed(self, text: str) -> str:
        # Enter sends the prompt in Claude Code, so a pasted line break must not become an Enter.
        return " ".join(text.split())


# --------------------------------------------------------------------------- Browser
_KEYS = {
    "enter": "Enter", "tab": "Tab", "escape": "Escape", "backspace": "Backspace", "delete": "Delete",
    "up": "ArrowUp", "down": "ArrowDown", "left": "ArrowLeft", "right": "ArrowRight",
    "home": "Home", "end": "End", "pageup": "PageUp", "pagedown": "PageDown",
}  # fmt: skip
_LOCAL_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".corp")


def is_private_address(url: str) -> bool:
    """True for anything that is not an ordinary public web address. Checked again here so a
    redirect or a link on a page cannot lead the browser onto the local network."""
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return True
    try:
        return not ipaddress.ip_address(host).is_global
    except ValueError:
        return host == "localhost" or "." not in host or host.endswith(_LOCAL_SUFFIXES)


def page_host(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


# Playwright shuts the window if these objects are collected or stopped after the task
# thread returns. Keep them for the life of this process so the page stays on screen,
# the same way Notepad is left open.
_open_browsers: list[BrowserDriver] = []


class BrowserDriver:
    name = "browser"

    def __init__(self, playwright: Any, browser: Any, page: Any) -> None:
        self._playwright, self._browser, self.page = playwright, browser, page
        _open_browsers.append(self)

    @classmethod
    def open(cls) -> BrowserDriver:
        """A fresh, empty browser window (installed Edge or Chrome; no profile, no downloads)."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise DriverUnavailable("The browser needs: pip install playwright") from exc

        playwright = sync_playwright().start()
        browser, last = None, None
        for channel in ("msedge", "chrome"):
            try:
                browser = playwright.chromium.launch(channel=channel, headless=False)
                break
            except Exception as exc:  # noqa: BLE001
                last = exc
        if browser is None:
            playwright.stop()
            raise DriverUnavailable(f"Neither Edge nor Chrome could be started ({last})")

        context = browser.new_context(accept_downloads=False)
        page = context.new_page()

        def guard(route: Any) -> None:
            if route.request.url.startswith(("http://", "https://")) and is_private_address(route.request.url):
                route.abort()
            else:
                route.continue_()

        context.route("**/*", guard)
        return cls(playwright, browser, page)

    def navigate(self, url: str) -> Result:
        if is_private_address(url):
            return Result(False, "Local and private network addresses are not allowed")
        try:
            self.page.goto(url, timeout=20_000, wait_until="domcontentloaded")
            return Result(True, f"Opened {page_host(self.page.url) or url}")
        except Exception as exc:  # noqa: BLE001
            return Result(False, f"Could not open {url}: {str(exc).splitlines()[0]}", retry=True)

    def observe_text(self) -> str:
        try:
            body = self.page.inner_text("body", timeout=3000)
        except Exception:  # noqa: BLE001
            body = ""
        return f"{self.page.url}\n{self.page.title()}\n{body[:4000]}"

    def type_text(self, text: str) -> Result:
        try:
            self.page.keyboard.type(text, delay=10)
            return Result(True, f"Typed {text!r}")
        except Exception as exc:  # noqa: BLE001
            return Result(False, str(exc).splitlines()[0])

    def press_key(self, key: str, modifiers: list[str]) -> Result:
        combo = "+".join([m.capitalize() if m != "ctrl" else "Control" for m in modifiers] + [_KEYS.get(key, key)])
        try:
            self.page.keyboard.press(combo)
            return Result(True, f"Pressed {combo}")
        except Exception as exc:  # noqa: BLE001
            return Result(False, str(exc).splitlines()[0])

    def click(self, target: str) -> Result:
        pattern = re.compile(re.escape(target), re.IGNORECASE)
        candidates = (
            self.page.get_by_role("link", name=pattern),
            self.page.get_by_role("button", name=pattern),
            self.page.get_by_text(pattern),
        )
        for locator in candidates:
            try:
                if locator.count():
                    locator.first.click(timeout=4000)
                    return Result(True, f"Clicked {target!r}")
            except Exception as exc:  # noqa: BLE001
                logger.debug("Click candidate failed: %s", exc)
        return Result(False, f"Could not find {target!r} on the page", retry=True)

    def scroll(self, direction: str, amount: int) -> Result:
        try:
            self.page.mouse.wheel(0, (amount if direction == "down" else -amount) * 120)
            return Result(True, f"Scrolled {direction} {amount}")
        except Exception as exc:  # noqa: BLE001
            return Result(False, str(exc).splitlines()[0])

    def close(self) -> None:
        """Leave the window on screen after the task. Playwright is kept alive so it
        does not tear the process down when this task's RunContext is discarded."""
        if self not in _open_browsers:
            _open_browsers.append(self)
