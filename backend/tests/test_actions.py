from app.actions import InvalidActionError, parse_instruction


def test_parse_default_notepad_instruction() -> None:
    action = parse_instruction("Open Notepad and type Hello from OmniAgent")
    assert action.type == "open_notepad"
    assert action.message == "Hello from OmniAgent"


def test_parse_open_notepad_only() -> None:
    action = parse_instruction("open notepad")
    assert action.message == "Hello from OmniAgent"


def test_reject_arbitrary_commands() -> None:
    for instruction in (
        "run powershell Get-Process",
        "cmd.exe /c del /f C:\\Windows\\System32",
        "python -c print(1)",
        "",
    ):
        try:
            parse_instruction(instruction)
        except InvalidActionError:
            continue
        raise AssertionError(f"Should reject {instruction!r}")
