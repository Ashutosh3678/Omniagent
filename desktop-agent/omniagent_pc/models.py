"""Shared result types for the Phase 1 Windows agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

Status = Literal["Success", "Failed"]


@dataclass(frozen=True)
class StepResult:
    name: str
    status: Status
    detail: str = ""


@dataclass
class TaskResult:
    status: Status
    message: str
    steps: list[StepResult] = field(default_factory=list)
    screenshot_path: Optional[str] = None
    observed_text: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.status == "Success"
