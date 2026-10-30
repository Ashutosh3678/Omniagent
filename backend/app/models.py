"""Structured task and agent objects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schema import EXECUTABLE_ACTIONS, LEGACY_ACTIONS

TaskStatus = Literal["pending", "running", "completed", "partial", "failed"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LogEntry(BaseModel):
    ts: datetime = Field(default_factory=utcnow)
    message: str


class Step(BaseModel):
    """What the app shows for one plan step."""

    name: str
    status: Literal["pending", "running", "success", "failed", "unverified", "skipped", "held_back"] = "pending"
    detail: str = ""
    has_screenshot: bool = False
    # Where the thumbnail is stored on the CDN (kept with the task), and the address the app should load
    # (filled in only when the task is sent out, so a signed link is never saved).
    screenshot_ref: str | None = None
    screenshot_url: str | None = None


class PlanStep(BaseModel):
    """One validated action to run on the PC."""

    index: int
    action: dict[str, Any]
    description: str
    confidence: float = 1.0


class HeldBack(BaseModel):
    """A step the validator refused to dispatch, and why."""

    index: int
    raw: dict[str, Any] = Field(default_factory=dict)
    reason: str
    detail: str = ""


class PlanVerdict(BaseModel):
    steps: list[PlanStep]
    held_back: list[HeldBack]
    confidence: float | None = None


class User(BaseModel):
    id: str
    email: str
    name: str = ""
    password_hash: str
    created_at: datetime = Field(default_factory=utcnow)


class UserPublic(BaseModel):
    id: str
    email: str
    name: str

    @classmethod
    def from_user(cls, user: User) -> UserPublic:
        return cls(id=user.id, email=user.email, name=user.name)


class RegisterUserRequest(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=120)


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


AgentStatus = Literal["active", "revoked"]


class Agent(BaseModel):
    id: str
    user_id: str | None = None
    name: str
    hostname: str
    online: bool = False
    connected_at: datetime | None = None
    status: AgentStatus = "active"
    permitted_apps: list[str] = Field(default_factory=lambda: ["notepad"])
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    # Actions the PC's agent says it can run; None until it reports (older agents).
    capabilities: list[str] | None = None

    @property
    def executable_actions(self) -> frozenset[str]:
        if self.capabilities is None:
            return LEGACY_ACTIONS
        return frozenset(self.capabilities) & EXECUTABLE_ACTIONS

    @property
    def expired(self) -> bool:
        if self.expires_at is None:
            return False
        expires = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=timezone.utc)
        return expires <= utcnow()


class Task(BaseModel):
    id: str
    user_id: str | None = None
    agent_id: str
    instruction: str
    plan: list[PlanStep] = Field(default_factory=list)
    held_back: list[HeldBack] = Field(default_factory=list)
    confidence: float | None = None
    status: TaskStatus = "pending"
    logs: list[LogEntry] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    screenshot_id: str | None = None
    screenshot_ref: str | None = None
    summary: str = ""
    error: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def log(self, message: str) -> None:
        self.logs.append(LogEntry(message=message))
        self.updated_at = utcnow()


class PairAgentRequest(BaseModel):
    code: str = Field(min_length=4, max_length=32)
    name: str = Field(default="Office PC", max_length=120)
    hostname: str = Field(default="WINDOWS-PC", max_length=255)


class PairingCodeResponse(BaseModel):
    code: str
    expires_at: datetime


class UpdateAgentRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    permitted_apps: list[str] | None = None
    expires_at: datetime | None = None
    clear_expiry: bool = False


class AuditEvent(BaseModel):
    id: str
    user_id: str | None = None
    agent_id: str | None = None
    task_id: str | None = None
    event: str
    decision: Literal["permit", "deny", "info"]
    reason: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class CreateTaskRequest(BaseModel):
    instruction: str = Field(max_length=2000)
    agent_id: str | None = None
    # A plan the app already previewed. It is validated again; it is never trusted.
    plan: list[dict[str, Any]] | None = Field(default=None, max_length=50)


class PlanPreviewRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)
    agent_id: str | None = None


class PlanPreview(BaseModel):
    planner: str
    steps: list[PlanStep]
    held_back: list[HeldBack]
    confidence: float | None = None
    runnable: bool
    low_confidence: bool = False
    note: str = ""
    # The full plan as planned (including held-back steps), to send back to create the task.
    plan: list[dict[str, Any]]


class TaskPublic(BaseModel):
    id: str
    agent_id: str
    instruction: str
    status: TaskStatus
    logs: list[LogEntry]
    steps: list[Step]
    held_back: list[HeldBack] = Field(default_factory=list)
    confidence: float | None = None
    screenshot_url: str | None = None
    summary: str
    error: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_task(cls, task: Task) -> TaskPublic:
        from app.cdn import get_cdn  # imported here: the CDN module reads settings that models must not depend on

        cdn = get_cdn()

        def step_url(index: int, step: Step) -> str | None:
            if step.screenshot_ref and cdn is not None:
                return cdn.url(step.screenshot_ref)
            if step.has_screenshot and not step.screenshot_ref:
                return f"/api/v1/tasks/{task.id}/steps/{index}/screenshot"
            return None

        final_url = None
        if task.screenshot_ref and cdn is not None:
            final_url = cdn.url(task.screenshot_ref, max_width=1080)
        elif task.screenshot_id:
            final_url = f"/api/v1/tasks/{task.id}/screenshot"

        return cls(
            id=task.id,
            agent_id=task.agent_id,
            instruction=task.instruction,
            status=task.status,
            logs=task.logs,
            steps=[step.model_copy(update={"screenshot_url": step_url(i, step)}) for i, step in enumerate(task.steps)],
            held_back=task.held_back,
            confidence=task.confidence,
            screenshot_url=final_url,
            summary=task.summary,
            error=task.error,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )


class AgentPublic(BaseModel):
    id: str
    name: str
    hostname: str
    online: bool
    status: AgentStatus = "active"
    permitted_apps: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None
    actions: list[str] = Field(default_factory=list)

    @classmethod
    def from_agent(cls, agent: Agent) -> AgentPublic:
        return cls(
            id=agent.id,
            name=agent.name,
            hostname=agent.hostname,
            online=agent.online,
            status="revoked" if agent.status == "revoked" else "active",
            permitted_apps=agent.permitted_apps,
            expires_at=agent.expires_at,
            actions=sorted(agent.executable_actions),
        )


class AgentRegistered(AgentPublic):
    """Returned once at registration; the device token is never shown again."""

    device_token: str


class WsMessage(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
