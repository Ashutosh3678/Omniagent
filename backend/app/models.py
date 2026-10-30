"""Structured task and agent objects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

TaskStatus = Literal["pending", "running", "completed", "failed"]
ALLOWED_ACTION_TYPES = frozenset({"open_notepad"})


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Action(BaseModel):
    type: Literal["open_notepad"]
    message: str = "Hello from OmniAgent"


class LogEntry(BaseModel):
    ts: datetime = Field(default_factory=utcnow)
    message: str


class Step(BaseModel):
    name: str
    status: Literal["pending", "running", "success", "failed"] = "pending"
    detail: str = ""


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
    action: Action
    status: TaskStatus = "pending"
    logs: list[LogEntry] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    screenshot_id: str | None = None
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
    instruction: str
    agent_id: str | None = None


class TaskPublic(BaseModel):
    id: str
    agent_id: str
    instruction: str
    status: TaskStatus
    logs: list[LogEntry]
    steps: list[Step]
    screenshot_url: str | None = None
    summary: str
    error: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_task(cls, task: Task) -> TaskPublic:
        return cls(
            id=task.id,
            agent_id=task.agent_id,
            instruction=task.instruction,
            status=task.status,
            logs=task.logs,
            steps=task.steps,
            screenshot_url=f"/api/v1/tasks/{task.id}/screenshot" if task.screenshot_id else None,
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
        )


class AgentRegistered(AgentPublic):
    """Returned once at registration; the device token is never shown again."""

    device_token: str


class WsMessage(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
