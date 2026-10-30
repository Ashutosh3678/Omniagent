"""The list of apps and folders this PC's owner allows, and the drivers for them."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omniagent_pc import apps, executors
from omniagent_pc import drivers as drv
from omniagent_pc.plan_runner import RunContext, StepOutcome


@pytest.fixture
def config() -> dict:
    return {"programs": {}, "folders": {}}


@pytest.fixture
def fake_pc(monkeypatch):
    """A PC with Paint, Calculator and Claude Code installed, but no Playwright."""
    monkeypatch.setattr(apps, "_on_path", lambda program: program in {"mspaint.exe", "calc.exe", "claude"})
    monkeypatch.setattr(apps.importlib.util, "find_spec", lambda name: None)


# --- the owner's file
def test_a_missing_or_damaged_file_is_an_empty_list(tmp_path: Path) -> None:
    assert apps.load_config(tmp_path / "nope.json") == {"programs": {}, "folders": {}}
    broken = tmp_path / "apps.json"
    broken.write_text("{not json", encoding="utf-8")
    assert apps.load_config(broken) == {"programs": {}, "folders": {}}
    broken.write_text(json.dumps({"programs": "x", "folders": [1]}), encoding="utf-8")
    assert apps.load_config(broken) == {"programs": {}, "folders": {}}


def test_the_list_survives_a_save_and_load(tmp_path: Path, config: dict) -> None:
    exe = tmp_path / "Tool.exe"
    exe.write_bytes(b"MZ")
    apps.add_program(config, str(exe), "My Tool")
    apps.add_folder(config, str(tmp_path), "work")
    path = tmp_path / "home" / "apps.json"
    apps.save_config(config, path)
    assert apps.load_config(path) == config


# --- adding programs
def test_a_program_must_be_an_existing_exe_with_a_full_path(tmp_path: Path, config: dict) -> None:
    (tmp_path / "notes.txt").write_text("x")
    for bad in ("calc.exe", str(tmp_path / "missing.exe"), str(tmp_path / "notes.txt"), str(tmp_path)):
        with pytest.raises(ValueError):
            apps.add_program(config, bad)
    assert config["programs"] == {}


def test_program_ids_are_safe_and_never_collide_with_built_in_apps(tmp_path: Path, config: dict) -> None:
    exe = tmp_path / "Paint.exe"
    exe.write_bytes(b"MZ")
    first = apps.add_program(config, str(exe), "Paint")
    second = apps.add_program(config, str(exe), "Paint")
    assert first not in apps.BUILTIN and second not in apps.BUILTIN and first != second
    assert first == "paint_2" and second == "paint_3"  # ids may not contain a hyphen
    odd = apps.add_program(config, str(exe), "7-Zip File Manager!!")
    assert odd.replace("_", "").isalnum() and odd == odd.lower() and not odd[0].isdigit() and len(odd) <= 32


# --- adding folders
def test_a_folder_must_exist_and_be_a_full_path(tmp_path: Path, config: dict) -> None:
    for bad in ("relative/dir", str(tmp_path / "missing")):
        with pytest.raises(ValueError):
            apps.add_folder(config, bad)


def test_folders_get_short_safe_unique_names(tmp_path: Path, config: dict) -> None:
    a, b = tmp_path / "one" / "site", tmp_path / "two" / "site"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    assert apps.add_folder(config, str(a)) == "site"
    assert apps.add_folder(config, str(b)) == "site-2"
    assert apps.add_folder(config, str(a)) == "site"  # the same folder again is not added twice
    weird = tmp_path / "my project (v2) $HOME"
    weird.mkdir()
    name = apps.add_folder(config, str(weird))
    assert all(ch.isalnum() or ch in " _.-" for ch in name) and 0 < len(name) <= 80


# --- what the agent reports
def test_the_report_has_names_and_labels_but_never_paths(tmp_path: Path, config: dict, fake_pc) -> None:
    exe = tmp_path / "Spotify.exe"
    exe.write_bytes(b"MZ")
    work = tmp_path / "secret-client-work"
    work.mkdir()
    apps.add_program(config, str(exe), "Spotify")
    apps.add_folder(config, str(work), "client")
    report = apps.catalog(config)
    assert {a["id"] for a in report["apps"]} == {"notepad", "paint", "calculator", "claude_code", "spotify"}
    assert next(a for a in report["apps"] if a["id"] == "claude_code")["needs_workspace"] is True
    assert report["workspaces"] == ["client"]
    text = json.dumps(report)
    assert str(tmp_path) not in text and "secret-client-work" not in text and "Spotify.exe" not in text


def test_apps_that_are_not_installed_are_not_offered(config: dict, monkeypatch) -> None:
    monkeypatch.setattr(apps, "_on_path", lambda program: False)
    monkeypatch.setattr(apps.importlib.util, "find_spec", lambda name: None)
    assert set(apps.app_specs(config)) == {"notepad"}


def test_the_browser_is_offered_only_with_playwright(config: dict, monkeypatch) -> None:
    monkeypatch.setattr(apps, "_on_path", lambda program: False)
    monkeypatch.setattr(apps.importlib.util, "find_spec", lambda name: object() if name == "playwright" else None)
    assert "browser" in apps.app_specs(config)


def test_a_program_or_folder_that_has_gone_is_no_longer_offered(tmp_path: Path, config: dict, fake_pc) -> None:
    exe = tmp_path / "Gone.exe"
    exe.write_bytes(b"MZ")
    folder = tmp_path / "gone"
    folder.mkdir()
    apps.add_program(config, str(exe), "Gone")
    apps.add_folder(config, str(folder), "gone")
    exe.unlink()
    folder.rmdir()
    report = apps.catalog(config)
    assert "gone" not in {a["id"] for a in report["apps"]} and report["workspaces"] == []


# --- finding a window after starting a program
WINDOWS = {10: ("Untitled - Notepad", "Notepad"), 20: ("Untitled - Paint", "ApplicationFrameWindow"), 30: ("", "Shell_TrayWnd")}


def test_choose_window_prefers_the_title_hint() -> None:
    assert drv.choose_window(WINDOWS, "paint") == 20
    assert drv.choose_window(WINDOWS, "calculator") is None


def test_choose_window_without_a_hint_takes_a_window_that_has_a_title() -> None:
    assert drv.choose_window({30: ("", "Shell_TrayWnd"), 20: ("Paint", "x")}) == 20


def test_choose_window_for_a_terminal_takes_a_console_even_with_an_empty_title() -> None:
    windows = {5: ("Browser", "Chrome_WidgetWin_1"), 6: ("", "CASCADIA_HOSTING_WINDOW_CLASS")}
    assert drv.choose_window(windows, None, drv._CONSOLE_CLASSES) == 6


def test_wait_for_window_returns_the_new_window() -> None:
    before = {10: ("Untitled - Notepad", "Notepad")}
    shots = iter([dict(before), dict(before), {**before, 20: ("Untitled - Paint", "x")}])
    ticks = iter(range(100))
    found = drv.wait_for_window(before, "paint", None, 20, snapshot=lambda: next(shots), sleep=lambda s: None, clock=lambda: next(ticks))
    assert found == 20


def test_wait_for_window_reuses_a_single_instance_app_that_was_already_open() -> None:
    existing = {40: ("Calculator", "ApplicationFrameWindow")}
    clock = iter([0, 1, 2, 11, 12, 13])  # past half the timeout, the already-open window is accepted
    found = drv.wait_for_window(existing, "calculator", None, 20, snapshot=lambda: dict(existing), sleep=lambda s: None, clock=lambda: next(clock))
    assert found == 40


def test_wait_for_window_gives_up() -> None:
    clock = iter([0, 5, 10, 15, 21, 22])
    assert drv.wait_for_window({}, "paint", None, 20, snapshot=lambda: {}, sleep=lambda s: None, clock=lambda: next(clock)) is None


# --- typing and keys that need no window
def test_special_characters_are_escaped_for_sendkeys() -> None:
    assert drv.escape_send_keys("a+b^c%d~e(f){g}") == "a{+}b{^}c{%}d{~}e{(}f{)}{{}g{}}"


def test_unsupported_keys_are_refused_without_touching_any_window() -> None:
    result = drv.WindowDriver(1, "Paint").press_key("f4", [])
    assert not result.ok and "not supported" in result.detail


def test_claude_code_gets_one_line_because_enter_sends_it() -> None:
    assert drv.ClaudeCodeDriver(1, "Claude Code")._typed("fix the test\n\nthen   run it\r\nagain") == "fix the test then run it again"


def test_only_notepad_and_the_browser_have_their_typing_checked_on_screen() -> None:
    assert drv.WindowDriver.verifies_typing is False and drv.ClaudeCodeDriver.verifies_typing is False


# --- starting Claude Code
def test_claude_code_refuses_when_it_is_not_installed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: None)
    driver, result = drv.ClaudeCodeDriver.start(tmp_path)
    assert driver is None and "not installed" in result.detail


def test_claude_code_refuses_a_folder_that_vanished(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: "claude")
    driver, result = drv.ClaudeCodeDriver.start(tmp_path / "gone")
    assert driver is None and "no longer exists" in result.detail


def test_claude_code_starts_the_plain_claude_command_in_the_folder(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: "claude")
    seen: dict = {}

    def fake_open(cls, command, label, **kwargs):
        seen.update(command=command, label=label, **kwargs)
        return cls(7, label), drv.Result(True, "Opened Claude Code")

    monkeypatch.setattr(drv.ClaudeCodeDriver, "open", classmethod(fake_open))
    driver, result = drv.ClaudeCodeDriver.start(tmp_path)
    assert driver is not None and result.detail == f"Opened Claude Code in {tmp_path.name}"
    assert seen["command"] == ["cmd.exe", "/k", "claude"]  # nothing from the phone is ever put in this command
    assert "--dangerously-skip-permissions" not in " ".join(seen["command"])
    assert seen["cwd"] == str(tmp_path) and seen["new_console"] is True


# --- the executor
class Recorder:
    verifies_typing = True

    def __init__(self) -> None:
        self.typed: list[str] = []

    def observe_text(self) -> str:
        return ""

    def type_text(self, text: str):
        self.typed.append(text)
        return drv.Result(True, "typed")


def test_open_claude_code_uses_a_folder_from_this_pcs_list(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "omniagent"
    folder.mkdir()
    monkeypatch.setattr(executors.apps, "load_config", lambda: {"programs": {}, "folders": {"omniagent": str(folder)}})
    monkeypatch.setattr(executors.apps, "app_specs", lambda config: {"claude_code": apps.BUILTIN["claude_code"]})
    started: list[Path] = []
    driver = Recorder()

    def start(cls, path):
        started.append(path)
        return driver, drv.Result(True, "Opened Claude Code in omniagent")

    monkeypatch.setattr(executors.ClaudeCodeDriver, "start", classmethod(start))
    ctx = RunContext()
    outcome = executors.open_app({"type": "open_app", "app": "claude_code", "workspace": "omniagent"}, ctx)
    assert outcome.ok and outcome.expected is None and ctx.driver is driver
    assert started == [folder]


@pytest.mark.parametrize("workspace", [None, "", "secrets", "C:\\Windows", "../x"])
def test_open_claude_code_refuses_any_folder_not_on_this_pcs_list(tmp_path: Path, monkeypatch, workspace) -> None:
    monkeypatch.setattr(executors.apps, "load_config", lambda: {"programs": {}, "folders": {"omniagent": str(tmp_path)}})
    monkeypatch.setattr(executors.apps, "app_specs", lambda config: {"claude_code": apps.BUILTIN["claude_code"]})
    called: list = []
    monkeypatch.setattr(executors.ClaudeCodeDriver, "start", classmethod(lambda cls, path: called.append(path)))
    action = {"type": "open_app", "app": "claude_code"} | ({"workspace": workspace} if workspace is not None else {})
    outcome = executors.open_app(action, RunContext())
    assert not outcome.ok and "No folder called" in outcome.detail and called == []


def test_open_paint_starts_its_program_and_finds_the_window_by_title(monkeypatch) -> None:
    monkeypatch.setattr(executors.apps, "load_config", lambda: {"programs": {}, "folders": {}})
    monkeypatch.setattr(executors.apps, "app_specs", lambda config: {"paint": apps.BUILTIN["paint"]})
    seen: dict = {}

    def fake_open(cls, command, label, **kwargs):
        seen.update(command=command, label=label, **kwargs)
        return cls(9, label), drv.Result(True, "Opened Paint")

    monkeypatch.setattr(executors.WindowDriver, "open", classmethod(fake_open))
    ctx = RunContext()
    outcome = executors.open_app({"type": "open_app", "app": "paint"}, ctx)
    assert outcome.ok and isinstance(ctx.driver, drv.WindowDriver)
    assert seen["command"] == ["mspaint.exe"] and seen["title_hint"] == "Paint"


def test_an_app_the_owner_did_not_set_up_is_refused_even_if_the_backend_allowed_it(monkeypatch) -> None:
    monkeypatch.setattr(executors.apps, "load_config", lambda: {"programs": {}, "folders": {}})
    monkeypatch.setattr(executors.apps, "app_specs", lambda config: {"notepad": apps.BUILTIN["notepad"]})
    outcome = executors.open_app({"type": "open_app", "app": "regedit"}, RunContext())
    assert not outcome.ok and "not set up on this PC" in outcome.detail


def test_typing_is_checked_on_screen_only_for_drivers_that_can_be_read_back() -> None:
    reads = Recorder()
    assert executors.type_text({"text": "hello"}, RunContext(driver=reads)) == StepOutcome(True, "typed", "hello", retry=False)
    blind = Recorder()
    blind.verifies_typing = False
    assert executors.type_text({"text": "hello"}, RunContext(driver=blind)).expected is None
