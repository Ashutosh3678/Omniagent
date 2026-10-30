"""Persistent agents, tasks and screenshots, plus live WebSocket connections."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from fastapi import WebSocket
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.db import Base, get_engine, session_scope
from app.models import Agent, AgentPublic, AppInfo, AuditEvent, Task, TaskPublic, User, utcnow
from app.schema import DEFAULT_PERMITTED_APPS
from app.orm import AgentRow, AuditRow, PairingCodeRow, ScreenshotRow, StepScreenshotRow, TaskRow, UserRow

logger = logging.getLogger(__name__)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _user(row: UserRow) -> User:
    return User(
        id=row.id,
        email=row.email,
        name=row.name,
        password_hash=row.password_hash,
        created_at=_aware(row.created_at),
    )


def _agent(row: AgentRow) -> Agent:
    return Agent(
        id=row.id,
        user_id=row.user_id,
        name=row.name,
        hostname=row.hostname,
        online=row.online,
        connected_at=_aware(row.connected_at),
        status=row.status,
        permitted_apps=list(row.permitted_apps or []),
        expires_at=_aware(row.expires_at),
        revoked_at=_aware(row.revoked_at),
        capabilities=list(row.capabilities) if row.capabilities is not None else None,
        apps=[AppInfo(**app) for app in row.apps] if row.apps is not None else None,
        workspaces=list(row.workspaces) if row.workspaces is not None else None,
    )


def _task(row: TaskRow) -> Task:
    return Task(
        id=row.id,
        user_id=row.user_id,
        agent_id=row.agent_id,
        instruction=row.instruction,
        plan=row.plan,
        held_back=row.held_back,
        confidence=row.confidence,
        status=row.status,
        logs=row.logs,
        steps=row.steps,
        screenshot_id=row.screenshot_id,
        screenshot_ref=row.screenshot_ref,
        summary=row.summary,
        error=row.error,
        created_at=_aware(row.created_at),
        updated_at=_aware(row.updated_at),
    )


def _task_values(task: Task) -> dict:
    return {
        "user_id": task.user_id,
        "agent_id": task.agent_id,
        "instruction": task.instruction,
        "plan": [step.model_dump(mode="json") for step in task.plan],
        "held_back": [item.model_dump(mode="json") for item in task.held_back],
        "confidence": task.confidence,
        "status": task.status,
        "logs": [entry.model_dump(mode="json") for entry in task.logs],
        "steps": [step.model_dump(mode="json") for step in task.steps],
        "screenshot_id": task.screenshot_id,
        "screenshot_ref": task.screenshot_ref,
        "summary": task.summary,
        "error": task.error,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


class Store:
    def __init__(self) -> None:
        self.sockets: dict[str, WebSocket] = {}
        self._last_audit_ts = utcnow()
        self._listeners: list[Callable[[str, str, dict], None]] = []

    def subscribe(self, listener: Callable[[str, str, dict], None]) -> None:
        """listener(kind, user_id, payload) is called after a task or PC changes. kind: "task" | "agent"."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def _emit(self, kind: str, user_id: str | None, payload: dict) -> None:
        if user_id is None:
            return
        for listener in self._listeners:
            try:
                listener(kind, user_id, payload)
            except Exception:  # noqa: BLE001 - a broken listener must never break a database write
                logger.exception("Store listener failed")

    def _emit_task(self, task: Task) -> None:
        self._emit("task", task.user_id, TaskPublic.from_task(task).model_dump(mode="json"))

    def _emit_agent(self, agent_id: str) -> None:
        agent = self.get_agent(agent_id)
        if agent is not None:
            self._emit("agent", agent.user_id, AgentPublic.from_agent(agent).model_dump(mode="json"))

    def reset(self) -> None:
        """Wipe all data. Only allowed on SQLite (tests)."""
        engine = get_engine()
        if engine.dialect.name != "sqlite":
            raise RuntimeError("reset() is only allowed on SQLite")
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        self.sockets.clear()

    def new_id(self) -> str:
        return str(uuid.uuid4())

    # users
    def add_user(self, user: User) -> bool:
        """Returns False if the email is already registered."""
        try:
            with session_scope() as db:
                db.add(UserRow(**user.model_dump()))
        except IntegrityError:
            return False
        return True

    def get_user(self, user_id: str) -> User | None:
        with session_scope() as db:
            row = db.get(UserRow, user_id)
            return _user(row) if row else None

    def get_user_by_email(self, email: str) -> User | None:
        with session_scope() as db:
            row = db.scalar(select(UserRow).where(UserRow.email == email))
            return _user(row) if row else None

    # pairing codes
    def add_pairing_code(self, user_id: str, code_hash: str, expires_at: datetime) -> None:
        with session_scope() as db:
            db.add(
                PairingCodeRow(
                    id=self.new_id(),
                    user_id=user_id,
                    code_hash=code_hash,
                    expires_at=expires_at,
                    created_at=utcnow(),
                )
            )

    def consume_pairing_code(self, code_hash: str) -> str | None:
        """Atomically marks a valid, unused, unexpired code as used. Returns its owner's id."""
        now = utcnow()
        with session_scope() as db:
            return db.scalar(
                update(PairingCodeRow)
                .where(
                    PairingCodeRow.code_hash == code_hash,
                    PairingCodeRow.used_at.is_(None),
                    PairingCodeRow.expires_at > now,
                )
                .values(used_at=now)
                .returning(PairingCodeRow.user_id)
            )

    # audit
    def add_audit(
        self,
        event: str,
        decision: str,
        reason: str = "",
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        task_id: str | None = None,
    ) -> None:
        # Windows clocks can repeat a timestamp; keep audit order strict.
        created = max(utcnow(), self._last_audit_ts + timedelta(microseconds=1))
        self._last_audit_ts = created
        with session_scope() as db:
            db.add(
                AuditRow(
                    id=self.new_id(),
                    user_id=user_id,
                    agent_id=agent_id,
                    task_id=task_id,
                    event=event,
                    decision=decision,
                    reason=reason,
                    created_at=created,
                )
            )

    def list_audit(self, user_id: str, limit: int = 100) -> list[AuditEvent]:
        with session_scope() as db:
            rows = db.scalars(
                select(AuditRow)
                .where(AuditRow.user_id == user_id)
                .order_by(AuditRow.created_at.desc())
                .limit(limit)
            ).all()
            return [
                AuditEvent(
                    id=row.id,
                    user_id=row.user_id,
                    agent_id=row.agent_id,
                    task_id=row.task_id,
                    event=row.event,
                    decision=row.decision,
                    reason=row.reason,
                    created_at=_aware(row.created_at),
                )
                for row in rows
            ]

    # agents
    def add_agent(self, agent: Agent, token_hash: str) -> None:
        with session_scope() as db:
            db.add(AgentRow(**agent.model_dump(), token_hash=token_hash, created_at=utcnow()))
        self._emit_agent(agent.id)

    def get_agent(self, agent_id: str, user_id: str | None = None) -> Agent | None:
        """With user_id, only returns the agent if that user owns it."""
        with session_scope() as db:
            row = db.get(AgentRow, agent_id)
            if row is None or (user_id is not None and row.user_id != user_id):
                return None
            return _agent(row)

    def update_agent(self, agent: Agent) -> None:
        with session_scope() as db:
            row = db.get(AgentRow, agent.id)
            if row is None:
                return
            row.name = agent.name
            row.status = agent.status
            row.permitted_apps = list(agent.permitted_apps)
            row.expires_at = agent.expires_at
            row.revoked_at = agent.revoked_at
        self._emit_agent(agent.id)

    def set_capabilities(
        self,
        agent_id: str,
        actions: list[str],
        apps: list[dict] | None = None,
        workspaces: list[str] | None = None,
    ) -> list[str]:
        """Stores what the PC says it can do. Returns the apps switched on by default the first time it
        reports its apps (same harmless set a brand-new PC gets); nothing else is ever turned on here."""
        granted: list[str] = []
        with session_scope() as db:
            row = db.get(AgentRow, agent_id)
            if row is None:
                return granted
            row.capabilities = sorted(set(actions))
            if apps is not None:
                first_report = row.apps is None
                row.apps = apps
                if first_report:
                    offered = {app["id"] for app in apps}
                    current = list(row.permitted_apps or [])
                    granted = [a for a in DEFAULT_PERMITTED_APPS if a in offered and a not in current]
                    row.permitted_apps = current + granted
            if workspaces is not None:
                row.workspaces = workspaces
        self._emit_agent(agent_id)
        return granted

    def get_agent_token_hash(self, agent_id: str) -> str | None:
        with session_scope() as db:
            row = db.get(AgentRow, agent_id)
            return row.token_hash if row else None

    def list_agents(self, user_id: str | None = None) -> list[Agent]:
        with session_scope() as db:
            query = select(AgentRow).order_by(AgentRow.created_at)
            if user_id is not None:
                query = query.where(AgentRow.user_id == user_id)
            return [_agent(row) for row in db.scalars(query).all()]

    def mark_all_offline(self) -> None:
        """Sockets do not survive a restart, so nothing can still be online."""
        with session_scope() as db:
            db.execute(update(AgentRow).values(online=False))
            db.execute(
                update(TaskRow)
                .where(TaskRow.status.in_(["pending", "running"]))
                .values(status="failed", error="Backend restarted", updated_at=utcnow())
            )

    def set_online(self, agent_id: str, socket: WebSocket) -> None:
        with session_scope() as db:
            row = db.get(AgentRow, agent_id)
            if row is None:
                return
            row.online = True
            row.connected_at = utcnow()
        self.sockets[agent_id] = socket
        self._emit_agent(agent_id)

    def fail_active_tasks(self, agent_id: str, reason: str) -> list[Task]:
        failed: list[Task] = []
        with session_scope() as db:
            rows = db.scalars(
                select(TaskRow).where(
                    TaskRow.agent_id == agent_id,
                    TaskRow.status.in_(["pending", "running"]),
                )
            ).all()
            for row in rows:
                task = _task(row)
                task.status = "failed"
                task.error = reason
                task.log(reason)
                for key, value in _task_values(task).items():
                    setattr(row, key, value)
                failed.append(task)
        for task in failed:
            self._emit_task(task)
        return failed

    def set_offline(self, agent_id: str) -> list[Task]:
        self.sockets.pop(agent_id, None)
        with session_scope() as db:
            agent = db.get(AgentRow, agent_id)
            if agent:
                agent.online = False
        self._emit_agent(agent_id)
        return self.fail_active_tasks(agent_id, "Agent disconnected")

    # tasks
    def save_task(self, task: Task) -> None:
        with session_scope() as db:
            row = db.get(TaskRow, task.id)
            if row is None:
                db.add(TaskRow(id=task.id, **_task_values(task)))
            else:
                for key, value in _task_values(task).items():
                    setattr(row, key, value)
        self._emit_task(task)

    def get_task(self, task_id: str, user_id: str | None = None) -> Task | None:
        """With user_id, only returns the task if that user owns it."""
        with session_scope() as db:
            row = db.get(TaskRow, task_id)
            if row is None or (user_id is not None and row.user_id != user_id):
                return None
            return _task(row)

    def list_tasks(self, user_id: str | None = None) -> list[Task]:
        with session_scope() as db:
            query = select(TaskRow).order_by(TaskRow.created_at.desc())
            if user_id is not None:
                query = query.where(TaskRow.user_id == user_id)
            return [_task(row) for row in db.scalars(query).all()]

    # per-step screenshots
    def save_step_screenshot(self, task_id: str, index: int, data: bytes, content_type: str) -> None:
        with session_scope() as db:
            row = db.get(StepScreenshotRow, (task_id, index))
            if row is None:
                db.add(StepScreenshotRow(task_id=task_id, step_index=index, content_type=content_type, data=data))
            else:
                row.content_type, row.data = content_type, data

    def get_step_screenshot(self, task_id: str, index: int, user_id: str | None = None) -> tuple[bytes, str] | None:
        with session_scope() as db:
            task = db.get(TaskRow, task_id)
            if task is None or (user_id is not None and task.user_id != user_id):
                return None
            row = db.get(StepScreenshotRow, (task_id, index))
            return (row.data, row.content_type) if row else None

    # screenshots
    def save_screenshot(self, task_id: str, data: bytes) -> None:
        with session_scope() as db:
            row = db.get(ScreenshotRow, task_id)
            if row is None:
                db.add(ScreenshotRow(task_id=task_id, data=data))
            else:
                row.data = data

    def get_screenshot(self, task_id: str, user_id: str | None = None) -> bytes | None:
        with session_scope() as db:
            task = db.get(TaskRow, task_id)
            if task is None or (user_id is not None and task.user_id != user_id):
                return None
            row = db.get(ScreenshotRow, task_id)
            return row.data if row else None


store = Store()
