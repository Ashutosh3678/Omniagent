"""The typed action vocabulary. Every plan step is exactly one of these."""

from __future__ import annotations

import ipaddress
from typing import Annotated, Literal, Union
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

# Keys that can be pressed on their own, and letters that may only be pressed with Ctrl.
SPECIAL_KEYS = frozenset(
    {"enter", "tab", "escape", "backspace", "delete", "up", "down", "left", "right", "home", "end", "pageup", "pagedown"}
)
CTRL_LETTERS = frozenset("acvxzy")


class _Action(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OpenApp(_Action):
    type: Literal["open_app"]
    app: str = Field(min_length=1, max_length=32)


class TypeText(_Action):
    type: Literal["type_text"]
    text: str = Field(min_length=1, max_length=2000)


class PressKey(_Action):
    type: Literal["press_key"]
    key: str = Field(min_length=1, max_length=16)
    modifiers: list[Literal["ctrl", "shift"]] = Field(default_factory=list, max_length=2)

    @field_validator("key")
    @classmethod
    def _known_key(cls, key: str) -> str:
        return key.lower()

    @model_validator(mode="after")
    def _allowed_combo(self) -> PressKey:
        if self.key in SPECIAL_KEYS or (self.key in CTRL_LETTERS and "ctrl" in self.modifiers):
            return self
        raise ValueError(f"Key {self.key!r} is not allowed")


class Wait(_Action):
    type: Literal["wait"]
    seconds: float = Field(gt=0, le=10)


class Screenshot(_Action):
    type: Literal["screenshot"]


class Click(_Action):
    type: Literal["click"]
    target: str = Field(min_length=1, max_length=200)


class Scroll(_Action):
    type: Literal["scroll"]
    direction: Literal["up", "down"]
    amount: int = Field(default=3, ge=1, le=20)


class BrowserNavigate(_Action):
    type: Literal["browser_navigate"]
    url: str = Field(pattern=r"^https?://", max_length=2000)

    @field_validator("url")
    @classmethod
    def _public_web_address(cls, url: str) -> str:
        """Only ordinary public web pages: no logins in the URL, no local or private network hosts."""
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if not host or parts.username or parts.password:
            raise ValueError("Use a plain web address without a username or password")
        if _is_ip(host):
            private = not ipaddress.ip_address(host.strip("[]")).is_global
        else:
            private = host == "localhost" or "." not in host or host.endswith(_LOCAL_SUFFIXES)
        if private:
            raise ValueError("Local and private network addresses are not allowed")
        return url


_LOCAL_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".corp")


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


Action = Annotated[
    Union[OpenApp, TypeText, PressKey, Wait, Screenshot, Click, Scroll, BrowserNavigate],
    Field(discriminator="type"),
]
action_adapter: TypeAdapter[Action] = TypeAdapter(Action)

ACTION_TYPES = frozenset(
    {"open_app", "type_text", "press_key", "wait", "screenshot", "click", "scroll", "browser_navigate"}
)
# Everything this system can plan. What a given PC can run is what its agent reports (Agent.executable_actions).
EXECUTABLE_ACTIONS = ACTION_TYPES
# What agents from before capability reporting could run.
LEGACY_ACTIONS = frozenset({"open_app", "type_text", "press_key", "wait", "screenshot"})
# Actions that act inside an app, so an app must have been opened earlier in the plan.
NEEDS_OPEN_APP = frozenset({"type_text", "press_key", "click", "scroll"})
KNOWN_APPS = frozenset({"notepad", "browser"})


def describe(action: _Action) -> str:
    """A short plain-language label for the step, shown in the app."""
    match action:
        case OpenApp(app=app):
            return f"Open {app.capitalize()}"
        case TypeText(text=text):
            shown = text if len(text) <= 40 else text[:37] + "..."
            return f"Type “{shown}”"
        case PressKey(key=key, modifiers=mods):
            return "Press " + "+".join([m.capitalize() for m in mods] + [key.upper() if len(key) == 1 else key.capitalize()])
        case Wait(seconds=seconds):
            return f"Wait {seconds:g}s"
        case Screenshot():
            return "Take a screenshot"
        case Click(target=target):
            return f"Click {target}"
        case Scroll(direction=direction, amount=amount):
            return f"Scroll {direction} {amount}"
        case BrowserNavigate(url=url):
            return f"Go to {url}"
    return action.type  # pragma: no cover
