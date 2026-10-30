from __future__ import annotations

from types import SimpleNamespace

import pytest

from omniagent_pc import executors
from omniagent_pc.drivers import BrowserDriver, NotepadDriver, Result, is_private_address, page_host
from omniagent_pc.plan_runner import RunContext, StepOutcome, run_plan


# --- address safety
@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/", "http://127.0.0.1:8000/", "http://192.168.0.1/", "http://10.0.0.5/",
        "http://169.254.169.254/latest/meta-data", "http://[::1]/", "http://printer.local/", "http://intranet/",
        "http://nas.lan/", "https:///nohost",
    ],
)  # fmt: skip
def test_local_and_private_addresses_are_blocked(url: str) -> None:
    assert is_private_address(url) is True


@pytest.mark.parametrize("url", ["https://example.com", "http://93.184.216.34/", "https://a.b.example.org/x?y=1"])
def test_public_addresses_are_allowed(url: str) -> None:
    assert is_private_address(url) is False


def test_page_host_drops_www() -> None:
    assert page_host("https://www.example.com/a") == "example.com"


# --- Notepad control matching
class FakeControl:
    def __init__(self, label: str, kind: str = "Button") -> None:
        self._label = label
        self.element_info = SimpleNamespace(control_type=kind)
        self.clicked = False

    def window_text(self) -> str:
        return self._label

    def click_input(self) -> None:
        self.clicked = True


class FakeSession:
    def __init__(self, *controls: FakeControl) -> None:
        self.controls = controls

    def spec(self):
        controls = self.controls
        return SimpleNamespace(set_focus=lambda: None, descendants=lambda: list(controls))


def test_click_picks_the_control_whose_label_best_matches() -> None:
    save, close, edit = FakeControl("Save As"), FakeControl("Close"), FakeControl("Save the file", "Edit")
    result = NotepadDriver(FakeSession(close, edit, save)).click("save as")
    assert result.ok and save.clicked and not close.clicked and not edit.clicked


def test_click_refuses_when_nothing_matches() -> None:
    only = FakeControl("Zoom In")
    result = NotepadDriver(FakeSession(only)).click("Delete everything")
    assert not result.ok and not only.clicked
    assert "Could not find" in result.detail


def test_click_ignores_text_areas_even_if_their_text_matches() -> None:
    document = FakeControl("Save", "Edit")
    assert not NotepadDriver(FakeSession(document)).click("Save").ok and not document.clicked


# --- executors with a fake driver
class FakeDriver:
    def __init__(self, text: str = "") -> None:
        self.calls: list[tuple] = []
        self.text = text

    def observe_text(self) -> str:
        return self.text

    def type_text(self, text):
        self.calls.append(("type", text))
        self.text += " " + text
        return Result(True, "typed")

    def press_key(self, key, modifiers):
        self.calls.append(("key", key, tuple(modifiers)))
        return Result(True, "pressed")

    def click(self, target):
        self.calls.append(("click", target))
        return Result(target != "missing", "clicked" if target != "missing" else "not found", retry=True)

    def scroll(self, direction, amount):
        self.calls.append(("scroll", direction, amount))
        return Result(True, "scrolled")


def step(index: int, **action) -> dict:
    return {"index": index, "action": action}


def test_a_plan_runs_through_the_real_executors_and_is_verified(monkeypatch) -> None:
    monkeypatch.setattr(executors, "_installed", lambda module: True)
    driver = FakeDriver("Untitled - Notepad")
    ctx = RunContext(driver=driver)
    plan = [
        step(0, type="type_text", text="Dear team"),
        step(1, type="press_key", key="enter", modifiers=[]),
        step(2, type="click", target="Save"),
        step(3, type="scroll", direction="down", amount=2),
    ]
    events: list[tuple] = []
    outcome = run_plan(plan, executors.build_executors(), ctx, lambda i, s, d, shot=None: events.append((i, s)), sleep=lambda s: None)
    assert outcome.status == "completed"
    assert driver.calls == [("type", "Dear team"), ("key", "enter", ()), ("click", "Save"), ("scroll", "down", 2)]
    assert (0, "success") in events


def test_typing_that_never_appears_is_unverified_and_not_repeated() -> None:
    class Deaf(FakeDriver):
        def type_text(self, text):
            self.calls.append(("type", text))
            return Result(True, "typed")  # claims success, screen never changes

    driver = Deaf("Untitled - Notepad")
    outcome = run_plan(
        [step(0, type="type_text", text="Quarterly numbers")],
        executors.build_executors(), RunContext(driver=driver), lambda *a, **k: None, sleep=lambda s: None,
    )  # fmt: skip
    assert outcome.status == "partial"
    assert len([c for c in driver.calls if c[0] == "type"]) == 1


def test_a_failing_click_is_retried_then_stops_the_plan() -> None:
    driver = FakeDriver()
    outcome = run_plan(
        [step(0, type="click", target="missing"), step(1, type="press_key", key="tab", modifiers=[])],
        executors.build_executors(), RunContext(driver=driver), lambda *a, **k: None, sleep=lambda s: None,
    )  # fmt: skip
    assert outcome.status == "failed"
    assert [c for c in driver.calls if c[0] == "click"] == [("click", "missing")] * 3
    assert not any(c[0] == "key" for c in driver.calls)


@pytest.mark.parametrize("kind", ["type_text", "press_key", "click", "scroll"])
def test_acting_without_an_open_app_fails_cleanly(kind: str) -> None:
    action = {"type_text": {"text": "x"}, "press_key": {"key": "tab"}, "click": {"target": "x"}, "scroll": {"direction": "up"}}[kind]
    outcome = getattr(executors, kind)(action, RunContext())
    assert outcome == StepOutcome(False, "No app is open")


def test_open_notepad_expects_to_see_notepad_in_the_title(monkeypatch) -> None:
    driver = FakeDriver("Untitled - Notepad")
    monkeypatch.setattr(executors.NotepadDriver, "open", classmethod(lambda cls: (driver, Result(True, "hwnd=1"))))
    ctx = RunContext()
    outcome = executors.open_app({"type": "open_app", "app": "notepad"}, ctx)
    assert ctx.driver is driver and outcome.expected == "notepad" and outcome.ok


def test_a_notepad_that_will_not_open_leaves_no_driver(monkeypatch) -> None:
    monkeypatch.setattr(executors.NotepadDriver, "open", classmethod(lambda cls: (None, Result(False, "no window"))))
    ctx = RunContext()
    outcome = executors.open_app({"type": "open_app", "app": "notepad"}, ctx)
    assert ctx.driver is None and not outcome.ok and outcome.expected is None


def test_open_unknown_app_is_refused() -> None:
    assert not executors.open_app({"type": "open_app", "app": "cmd"}, RunContext()).ok


def test_browser_driver_close_leaves_the_window_open() -> None:
    class Probe:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def close(self) -> None:
            self.calls.append("close")

        def stop(self) -> None:
            self.calls.append("stop")

    playwright, browser = Probe(), Probe()
    BrowserDriver(playwright, browser, object()).close()
    assert playwright.calls == [] and browser.calls == []


def test_browser_navigation_expects_the_site_name_and_registers_cleanup(monkeypatch) -> None:
    closed: list[bool] = []

    class FakeBrowser(BrowserDriver):
        def __init__(self) -> None:
            self.urls: list[str] = []

        @classmethod
        def open(cls):
            return cls()

        def navigate(self, url):
            self.urls.append(url)
            return Result(True, "Opened example.com")

        def close(self):
            closed.append(True)

    monkeypatch.setattr(executors, "BrowserDriver", FakeBrowser)
    ctx = RunContext()
    outcome = executors.browser_navigate({"type": "browser_navigate", "url": "https://www.example.com/x"}, ctx)
    assert outcome.ok and outcome.expected == "example.com"
    assert ctx.driver is not None
    ctx.cleanup()
    assert closed == [True]


def test_browser_that_cannot_start_is_a_failed_step_not_a_crash(monkeypatch) -> None:
    from omniagent_pc.drivers import DriverUnavailable

    class Missing:
        @classmethod
        def open(cls):
            raise DriverUnavailable("Neither Edge nor Chrome could be started")

    monkeypatch.setattr(executors, "BrowserDriver", Missing)
    monkeypatch.setattr(executors.apps, "app_specs", lambda config: {"browser": executors.apps.BUILTIN["browser"]})
    outcome = executors.open_app({"type": "open_app", "app": "browser"}, RunContext())
    assert not outcome.ok and "Edge" in outcome.detail


def test_capabilities_only_list_what_is_installed(monkeypatch) -> None:
    monkeypatch.setattr(executors, "_installed", lambda module: module == "pyautogui")
    assert set(executors.build_executors()) == {"open_app", "type_text", "press_key", "click", "wait", "screenshot", "scroll"}
    monkeypatch.setattr(executors, "_installed", lambda module: module == "playwright")
    assert set(executors.build_executors()) == {"open_app", "type_text", "press_key", "click", "wait", "screenshot", "browser_navigate"}
    monkeypatch.setattr(executors, "_installed", lambda module: False)
    assert "scroll" not in executors.build_executors() and "browser_navigate" not in executors.build_executors()


def test_a_typing_failure_that_may_have_typed_something_is_never_repeated() -> None:
    class Flaky(FakeDriver):
        def type_text(self, text):
            self.calls.append(("type", text))
            return Result(False, "UIA error after some keys")  # retry defaults to False

    driver = Flaky()
    outcome = run_plan(
        [step(0, type="type_text", text="Hello")],
        executors.build_executors(), RunContext(driver=driver), lambda *a, **k: None, sleep=lambda s: None,
    )  # fmt: skip
    assert outcome.status == "failed"
    assert driver.calls == [("type", "Hello")]  # exactly once


def test_a_failure_that_did_nothing_can_be_retried() -> None:
    class NotReady(FakeDriver):
        def type_text(self, text):
            self.calls.append(("type", text))
            return Result(False, "Could not find Notepad's text area", retry=True)

    driver = NotReady()
    run_plan(
        [step(0, type="type_text", text="Hello")],
        executors.build_executors(), RunContext(driver=driver), lambda *a, **k: None, sleep=lambda s: None,
    )  # fmt: skip
    assert len(driver.calls) == 3


# --- Notepad opens on a blank page (needs the Windows libraries)
class TestBlankPage:
    @pytest.fixture
    def fake_actions(self, monkeypatch):
        pytest.importorskip("pywinauto")
        from omniagent_pc import actions

        state = {"text": "", "keys": []}

        class Edit:
            def type_keys(self, keys, pause=0.0):
                state["keys"].append(keys)
                if keys == "^n":
                    state["text"] = state.get("after_new", "")

        monkeypatch.setattr(actions, "read_notepad_text", lambda session: state["text"])
        monkeypatch.setattr(actions, "_find_document_control", lambda window, backend: state.get("edit", Edit()))
        monkeypatch.setattr("omniagent_pc.drivers.time.sleep", lambda s: None)
        session = SimpleNamespace(spec=lambda: None, backend="uia")
        return state, session, Edit

    def test_an_empty_notepad_is_used_as_it_is(self, fake_actions) -> None:
        state, session, _ = fake_actions
        assert NotepadDriver(session)._ensure_blank_page().ok and state["keys"] == []

    def test_restored_text_is_left_alone_and_a_new_tab_is_used(self, fake_actions) -> None:
        state, session, _ = fake_actions
        state["text"], state["after_new"] = "someone's old unsaved notes", ""
        assert NotepadDriver(session)._ensure_blank_page().ok
        assert state["keys"] == ["^n"]  # opened a new page; never selected or deleted anything

    def test_it_refuses_to_write_if_a_blank_page_cannot_be_had(self, fake_actions) -> None:
        state, session, _ = fake_actions
        state["text"], state["after_new"] = "old notes", "old notes"
        result = NotepadDriver(session)._ensure_blank_page()
        assert not result.ok and "blank page" in result.detail

    def test_it_refuses_if_it_cannot_find_the_text_area(self, fake_actions, monkeypatch) -> None:
        from omniagent_pc import actions

        state, session, _ = fake_actions
        state["text"] = "old notes"
        monkeypatch.setattr(actions, "_find_document_control", lambda window, backend: None)
        assert not NotepadDriver(session)._ensure_blank_page().ok
