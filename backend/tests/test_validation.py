from __future__ import annotations

import pytest

from app.validation import MAX_STEPS, validate_plan

APPS = ["notepad"]
LEGACY = frozenset({"open_app", "type_text", "press_key", "wait", "screenshot"})  # an older agent


def step(action: dict, confidence: float = 1.0) -> dict:
    return {"action": action, "confidence": confidence}


OPEN = {"type": "open_app", "app": "notepad"}


def test_valid_plan_is_accepted_with_mean_confidence() -> None:
    verdict = validate_plan(
        [step(OPEN, 1.0), step({"type": "type_text", "text": "hi"}, 0.8), step({"type": "press_key", "key": "enter"}, 0.6)],
        APPS,
    )
    assert [s.index for s in verdict.steps] == [0, 1, 2]
    assert verdict.held_back == []
    assert verdict.confidence == pytest.approx(0.8)
    assert verdict.steps[1].description == "Type \u201chi\u201d"


def test_empty_plan_has_no_steps_and_no_confidence() -> None:
    verdict = validate_plan([], APPS)
    assert verdict.steps == [] and verdict.confidence is None


@pytest.mark.parametrize(
    "action,reason",
    [
        ({"type": "format_disk"}, "unknown_action"),
        ({}, "unknown_action"),
        ({"type": "type_text"}, "invalid_parameters"),
        ({"type": "type_text", "text": ""}, "invalid_parameters"),
        ({"type": "type_text", "text": "x" * 2001}, "invalid_parameters"),
        ({"type": "type_text", "text": "x", "shell": "calc"}, "invalid_parameters"),
        ({"type": "wait", "seconds": 0}, "invalid_parameters"),
        ({"type": "wait", "seconds": 11}, "invalid_parameters"),
        ({"type": "press_key", "key": "f4"}, "invalid_parameters"),
        ({"type": "press_key", "key": "w", "modifiers": ["ctrl"]}, "invalid_parameters"),
        ({"type": "press_key", "key": "a"}, "invalid_parameters"),
        ({"type": "press_key", "key": "enter", "modifiers": ["alt"]}, "invalid_parameters"),
        ({"type": "browser_navigate", "url": "file:///c:/secret"}, "invalid_parameters"),
        ({"type": "browser_navigate", "url": "http://localhost:8000/admin"}, "invalid_parameters"),
        ({"type": "browser_navigate", "url": "http://192.168.1.1/"}, "invalid_parameters"),
        ({"type": "browser_navigate", "url": "http://127.0.0.1/"}, "invalid_parameters"),
        ({"type": "browser_navigate", "url": "http://169.254.169.254/latest/meta-data"}, "invalid_parameters"),
        ({"type": "browser_navigate", "url": "http://[::1]/"}, "invalid_parameters"),
        ({"type": "browser_navigate", "url": "http://printer.local/"}, "invalid_parameters"),
        ({"type": "browser_navigate", "url": "http://intranet/"}, "invalid_parameters"),
        ({"type": "browser_navigate", "url": "https://user:pass@example.com/"}, "invalid_parameters"),
        ({"type": "scroll", "direction": "sideways"}, "invalid_parameters"),
        ({"type": "scroll", "direction": "down", "amount": 99}, "invalid_parameters"),
        ({"type": "open_app", "app": "calc"}, "unknown_app"),
    ],
)
def test_bad_first_step_is_held_back_with_a_reason(action: dict, reason: str) -> None:
    verdict = validate_plan([step(action)], APPS)
    assert verdict.steps == []
    assert verdict.held_back[0].reason == reason
    assert verdict.confidence is None


def test_app_must_be_in_the_devices_scope() -> None:
    verdict = validate_plan([step(OPEN)], [])
    assert verdict.held_back[0].reason == "app_not_permitted"


def test_typing_needs_an_open_app() -> None:
    verdict = validate_plan([step({"type": "type_text", "text": "hi"})], APPS)
    assert verdict.held_back[0].reason == "no_app_open"


def test_wait_and_screenshot_need_no_app() -> None:
    verdict = validate_plan([step({"type": "wait", "seconds": 1}), step({"type": "screenshot"})], APPS)
    assert len(verdict.steps) == 2


def test_first_bad_step_blocks_everything_after_it() -> None:
    verdict = validate_plan(
        [step(OPEN), step({"type": "click", "target": "Save"}), step({"type": "type_text", "text": "later"})],
        APPS,
        LEGACY,
    )
    assert [s.index for s in verdict.steps] == [0]
    assert [(h.index, h.reason) for h in verdict.held_back] == [(1, "not_supported"), (2, "blocked_by_earlier_step")]
    assert verdict.confidence == 1.0


def test_confidence_only_counts_accepted_steps() -> None:
    verdict = validate_plan([step(OPEN, 0.5), step({"type": "click", "target": "x"}, 0.1)], APPS, LEGACY)
    assert verdict.confidence == 0.5


@pytest.mark.parametrize("confidence", [-0.1, 1.5, "high", None, True])
def test_confidence_must_be_a_number_between_0_and_1(confidence) -> None:
    verdict = validate_plan([{"action": OPEN, "confidence": confidence}], APPS)
    assert verdict.steps == []
    assert verdict.held_back[0].reason == "invalid_parameters"


@pytest.mark.parametrize("raw", ["open notepad", 7, None, {"nope": 1}, {"action": "open_app"}])
def test_malformed_steps_are_held_back_not_crashed_on(raw) -> None:
    verdict = validate_plan([raw], APPS)
    assert verdict.steps == []
    assert verdict.held_back[0].reason == "invalid_parameters"


def test_plan_length_is_capped() -> None:
    verdict = validate_plan([step(OPEN)] + [step({"type": "wait", "seconds": 1})] * MAX_STEPS, APPS)
    assert len(verdict.steps) == MAX_STEPS
    assert verdict.held_back[0].reason == "plan_too_long"


def test_modifier_combos_that_are_allowed() -> None:
    plan = [step(OPEN), step({"type": "press_key", "key": "A", "modifiers": ["ctrl"]})]
    verdict = validate_plan(plan, APPS)
    assert len(verdict.steps) == 2
    assert verdict.steps[1].action == {"type": "press_key", "key": "a", "modifiers": ["ctrl"]}
    assert verdict.steps[1].description == "Press Ctrl+A"


# per-PC capabilities and the browser
def test_what_a_pc_can_run_is_what_its_agent_reported() -> None:
    plan = [step(OPEN), step({"type": "click", "target": "File"})]
    older = validate_plan(plan, APPS, LEGACY)
    newer = validate_plan(plan, APPS, LEGACY | {"click"})
    assert [h.reason for h in older.held_back] == ["not_supported"]
    assert len(newer.steps) == 2 and newer.held_back == []


def test_click_and_scroll_need_an_open_app() -> None:
    for action in ({"type": "click", "target": "File"}, {"type": "scroll", "direction": "down"}):
        verdict = validate_plan([step(action)], APPS)
        assert verdict.held_back[0].reason == "no_app_open"


def test_scroll_defaults_and_describes_itself() -> None:
    verdict = validate_plan([step(OPEN), step({"type": "scroll", "direction": "down"})], APPS)
    assert verdict.steps[1].action["amount"] == 3
    assert verdict.steps[1].description == "Scroll down 3"


def test_browser_navigation_needs_the_browser_app_in_scope() -> None:
    nav = step({"type": "browser_navigate", "url": "https://example.com/page"})
    assert validate_plan([nav], APPS).held_back[0].reason == "app_not_permitted"
    ok = validate_plan([nav], ["browser"])
    assert len(ok.steps) == 1 and ok.steps[0].description == "Go to https://example.com/page"


def test_after_navigating_the_browser_is_the_open_app() -> None:
    plan = [step({"type": "browser_navigate", "url": "https://example.com"}), step({"type": "click", "target": "More information"})]
    assert len(validate_plan(plan, ["browser"]).steps) == 2


def test_opening_the_browser_directly_is_checked_against_scope() -> None:
    assert validate_plan([step({"type": "open_app", "app": "browser"})], APPS).held_back[0].reason == "app_not_permitted"
    assert len(validate_plan([step({"type": "open_app", "app": "browser"})], ["browser"]).steps) == 1


def test_public_addresses_are_allowed() -> None:
    for url in ("https://example.com", "http://93.184.216.34/", "https://sub.domain.example.org/a?b=c#d"):
        assert len(validate_plan([step({"type": "browser_navigate", "url": url})], ["browser"]).steps) == 1
