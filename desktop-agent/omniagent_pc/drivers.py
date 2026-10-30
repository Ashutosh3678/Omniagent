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
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from omniagent_pc.embeddings import VERIFY_THRESHOLD, similarity

logger = logging.getLogger(__name__)


@dataclass
class Result:
    ok: bool
    detail: str = ""


class DriverUnavailable(Exception):
    """The libraries or programs this driver needs are not installed on this PC."""


# --------------------------------------------------------------------------- Notepad
_CLICKABLE = {"Button", "MenuItem", "TabItem", "CheckBox", "RadioButton", "Hyperlink", "ListItem", "TreeItem", "SplitButton"}


class NotepadDriver:
    name = "notepad"

    def __init__(self, session: Any) -> None:
        self.session = session

    @classmethod
    def open(cls) -> tuple[NotepadDriver | None, Result]:
        from omniagent_pc import actions

        session, result = actions.launch_notepad()
        driver = cls(session) if session is not None else None
        return driver, Result(result.status == "Success", result.detail)

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
        return Result(result.status == "Success", result.detail)

    def press_key(self, key: str, modifiers: list[str]) -> Result:
        from omniagent_pc import actions

        result = actions.press_key(self.session, key, modifiers)
        return Result(result.status == "Success", result.detail)

    def click(self, target: str) -> Result:
        """Clicks the control in the Notepad window whose label best matches `target`."""
        try:
            window = self.session.spec()
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
                return Result(False, f"Could not find {target!r} in Notepad")
            best[0].click_input()
            return Result(True, f"Clicked {best[1]!r}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Click failed")
            return Result(False, str(exc))

    def scroll(self, direction: str, amount: int) -> Result:
        try:
            import pyautogui

            window = self.session.spec()
            window.set_focus()
            rect = window.rectangle()
            pyautogui.moveTo((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
            pyautogui.scroll(amount if direction == "up" else -amount)
            return Result(True, f"Scrolled {direction} {amount}")
        except Exception as exc:  # noqa: BLE001 - includes pyautogui's corner failsafe
            logger.exception("Scroll failed")
            return Result(False, str(exc))

    def close(self) -> None:  # the user keeps the window they asked for
        return None


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


class BrowserDriver:
    name = "browser"

    def __init__(self, playwright: Any, browser: Any, page: Any) -> None:
        self._playwright, self._browser, self.page = playwright, browser, page

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
            return Result(False, f"Could not open {url}: {str(exc).splitlines()[0]}")

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
        return Result(False, f"Could not find {target!r} on the page")

    def scroll(self, direction: str, amount: int) -> Result:
        try:
            self.page.mouse.wheel(0, (amount if direction == "down" else -amount) * 120)
            return Result(True, f"Scrolled {direction} {amount}")
        except Exception as exc:  # noqa: BLE001
            return Result(False, str(exc).splitlines()[0])

    def close(self) -> None:
        for closer in (self._browser.close, self._playwright.stop):
            try:
                closer()
            except Exception:  # noqa: BLE001
                logger.debug("Browser cleanup failed", exc_info=True)
