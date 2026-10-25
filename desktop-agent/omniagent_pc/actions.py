"""Windows UI actions: open Notepad and type a message."""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from typing import Optional

from pywinauto import Desktop
from pywinauto.application import WindowSpecification

from omniagent_pc.models import StepResult

logger = logging.getLogger(__name__)

LAUNCH_TIMEOUT_SECONDS = 20.0
WINDOW_POLL_INTERVAL_SECONDS = 0.25
UIA_EDIT_CONTROL_TYPES = {"Edit", "Document"}


class NotepadSession:
    """A live Notepad window the agent can type into and inspect."""

    def __init__(self, handle: int, backend: str) -> None:
        self._handle = handle
        self.backend = backend

    def handle(self) -> int:
        return self._handle

    def spec(self) -> WindowSpecification:
        return Desktop(backend=self.backend).window(handle=self._handle)

    def process_id(self) -> int:
        return int(self.spec().process_id())


def require_windows() -> None:
    if sys.platform != "win32":
        raise RuntimeError("This agent only runs on Windows.")


def launch_notepad(
    timeout: float = LAUNCH_TIMEOUT_SECONDS,
) -> tuple[Optional[NotepadSession], StepResult]:
    """Start a new Notepad window and wait until it is visible."""
    require_windows()
    existing = _notepad_handles()
    logger.info("Launching notepad.exe (%s existing window(s))", len(existing))

    try:
        subprocess.Popen(
            ["notepad.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        return _failed_session(f"Could not start notepad.exe: {exc}")

    deadline = time.time() + timeout
    last_error = "Notepad window did not appear"

    while time.time() < deadline:
        session = _find_new_notepad_window(existing)
        if session is None:
            time.sleep(WINDOW_POLL_INTERVAL_SECONDS)
            continue

        try:
            window = session.spec()
            window.wait("visible", timeout=3)
            window.set_focus()
        except Exception as exc:  # noqa: BLE001 - UI timing is unpredictable
            last_error = f"Notepad opened but could not be focused: {exc}"
            time.sleep(WINDOW_POLL_INTERVAL_SECONDS)
            continue

        if _find_document_control(session.spec(), session.backend) is None:
            last_error = "Notepad opened but the text area is not ready"
            time.sleep(WINDOW_POLL_INTERVAL_SECONDS)
            continue

        detail = (
            f"backend={session.backend}, "
            f"pid={session.process_id()}, "
            f"hwnd={session.handle()}"
        )
        return session, StepResult("Open Notepad", "Success", detail)

    return _failed_session(last_error)


def type_message(session: NotepadSession, message: str) -> tuple[str, StepResult]:
    """Type `message` into the Notepad document and return the observed text."""
    try:
        window = session.spec()
        window.set_focus()
        time.sleep(0.35)
        edit = _find_document_control(window, session.backend)
        if edit is None:
            return "", StepResult(
                "Type message",
                "Failed",
                "Could not find Notepad's text area",
            )

        edit.set_focus()
        _clear_document(edit)
        edit.type_keys(_escape_type_keys(message), with_spaces=True, pause=0.02)
        time.sleep(0.25)

        observed = _read_control_text(edit)
        if not observed:
            time.sleep(0.4)
            observed = _read_control_text(edit)
        if not observed:
            observed = _read_via_clipboard(window)

        if message not in observed:
            return observed, StepResult(
                "Type message",
                "Failed",
                f"Typed text was not confirmed in Notepad (saw {observed!r})",
            )

        return observed, StepResult("Type message", "Success", f"Typed {message!r}")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Typing into Notepad failed")
        return "", StepResult("Type message", "Failed", str(exc))


def read_notepad_text(session: NotepadSession) -> str:
    edit = _find_document_control(session.spec(), session.backend)
    if edit is None:
        return ""
    return _read_control_text(edit) or _read_via_clipboard(session.spec())


def notepad_is_visible(session: NotepadSession) -> bool:
    try:
        window = session.spec()
        return bool(window.exists(timeout=1)) and bool(window.is_visible())
    except Exception:  # noqa: BLE001
        return False


def _failed_session(detail: str) -> tuple[Optional[NotepadSession], StepResult]:
    return None, StepResult("Open Notepad", "Failed", detail)


def _notepad_handles() -> set[int]:
    handles: set[int] = set()
    for backend in ("uia", "win32"):
        try:
            desktop = Desktop(backend=backend)
            for window in desktop.windows():
                title = window.window_text() or ""
                if "notepad" in title.lower():
                    handles.add(int(window.handle))
        except Exception:  # noqa: BLE001
            continue
    return handles


def _find_new_notepad_window(existing: set[int]) -> Optional[NotepadSession]:
    for backend in ("uia", "win32"):
        try:
            desktop = Desktop(backend=backend)
            for window in desktop.windows():
                title = window.window_text() or ""
                if "notepad" not in title.lower():
                    continue
                handle = int(window.handle)
                if handle in existing or not window.is_visible():
                    continue
                return NotepadSession(handle, backend)
        except Exception:  # noqa: BLE001
            continue
    return None


def _find_document_control(window: WindowSpecification, backend: str):
    if backend == "uia":
        search_specs = (
            {"control_type": "Document"},
            {"control_type": "Edit"},
            {"title": "Text editor", "control_type": "Edit"},
            {"class_name": "RichEditD2DPT"},
            {"auto_id": "RichEditD2DPT"},
        )
    else:
        search_specs = (
            {"class_name": "Edit"},
            {"class_name": "RichEditD2DPT"},
        )

    for spec in search_specs:
        try:
            control = window.child_window(**spec)
            if control.exists(timeout=1):
                return control
        except Exception:  # noqa: BLE001
            continue

    try:
        wrapper = window.wrapper_object()
        for descendant in wrapper.descendants():
            info = descendant.element_info
            control_type = getattr(info, "control_type", "") or ""
            class_name = getattr(info, "class_name", "") or ""
            if control_type in UIA_EDIT_CONTROL_TYPES or class_name in {
                "Edit",
                "RichEditD2DPT",
            }:
                return descendant
    except Exception:  # noqa: BLE001
        logger.debug("Could not walk Notepad descendants", exc_info=True)

    return None


def _clear_document(edit) -> None:
    try:
        edit.type_keys("^a{BACKSPACE}", pause=0.03)
        time.sleep(0.1)
    except Exception:  # noqa: BLE001
        logger.debug("Could not clear Notepad before typing", exc_info=True)


def _read_control_text(control) -> str:
    readers = (
        lambda: control.get_value(),
        lambda: control.legacy_properties().get("Value"),
        lambda: control.window_text(),
        lambda: control.texts()[0] if control.texts() else "",
    )
    for reader in readers:
        try:
            value = reader()
            if value:
                return str(value)
        except Exception:  # noqa: BLE001
            continue
    return ""


def _read_via_clipboard(window: WindowSpecification) -> str:
    """Last-resort read for Win11 Notepad when UIA value is empty."""
    try:
        import win32clipboard
        import win32con
    except ImportError:
        return ""

    previous: Optional[str] = None
    try:
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                previous = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()
    except Exception:  # noqa: BLE001
        previous = None

    try:
        window.set_focus()
        window.type_keys("^a^c", pause=0.05)
        time.sleep(0.2)
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                return str(win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT))
        finally:
            win32clipboard.CloseClipboard()
    except Exception:  # noqa: BLE001
        logger.debug("Clipboard readback from Notepad failed", exc_info=True)
        return ""
    finally:
        if previous is not None:
            try:
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(previous, win32con.CF_UNICODETEXT)
                win32clipboard.CloseClipboard()
            except Exception:  # noqa: BLE001
                logger.debug("Could not restore clipboard", exc_info=True)

    return ""


def _escape_type_keys(text: str) -> str:
    """Escape characters that pywinauto treats as keyboard modifiers."""
    special = set("+^%~{}()")
    return "".join("{" + char + "}" if char in special else char for char in text)


__all__ = [
    "NotepadSession",
    "launch_notepad",
    "notepad_is_visible",
    "read_notepad_text",
    "require_windows",
    "type_message",
]
