import pytest

from app.actions import InvalidActionError, plan_from_instruction


def test_open_and_type_becomes_two_steps() -> None:
    plan = plan_from_instruction("Open Notepad and type Hello from OmniAgent")
    assert [s["action"]["type"] for s in plan] == ["open_app", "type_text"]
    assert plan[0]["action"]["app"] == "notepad"
    assert plan[1]["action"]["text"] == "Hello from OmniAgent"


def test_open_only_is_one_step() -> None:
    plan = plan_from_instruction("open notepad")
    assert plan == [{"action": {"type": "open_app", "app": "notepad"}, "confidence": 1.0}]


@pytest.mark.parametrize("text", ["", "   ", "run calc.exe", "open notepad && del *", "format c:"])
def test_other_instructions_are_rejected(text: str) -> None:
    with pytest.raises(InvalidActionError):
        plan_from_instruction(text)
