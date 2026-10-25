"""In-memory agents, tasks, screenshots, and live WebSocket connections."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import WebSocket

from app.models import Agent, Task, utcnow


class Store:
    def __init__(self) -> None:
        self.agents: dict[str, Agent] = {}
        self.tasks: dict[str, Task] = {}
        self.screenshots: dict[str, bytes] = {}
        self.sockets: dict[str, WebSocket] = {}
        self.lock = asyncio.Lock()

    def reset(self) -> None:
        self.agents.clear()
        self.tasks.clear()
        self.screenshots.clear()
        self.sockets.clear()

    def new_id(self) -> str:
        return str(uuid.uuid4())

    def connected_agents(self) -> list[Agent]:
        return [agent for agent in self.agents.values() if agent.online]

    def resolve_agent(self, agent_id: str | None) -> Agent | None:
        if agent_id:
            return self.agents.get(agent_id)
        online = self.connected_agents()
        if len(online) == 1:
            return online[0]
        return None

    def set_online(self, agent_id: str, socket: WebSocket) -> None:
        agent = self.agents.get(agent_id)
        if agent is None:
            return
        agent.online = True
        agent.connected_at = utcnow()
        self.sockets[agent_id] = socket

    def set_offline(self, agent_id: str) -> list[Task]:
        agent = self.agents.get(agent_id)
        if agent:
            agent.online = False
        self.sockets.pop(agent_id, None)
        failed: list[Task] = []
        for task in self.tasks.values():
            if task.agent_id == agent_id and task.status in {"pending", "running"}:
                task.status = "failed"
                task.error = "Agent disconnected"
                task.log("Agent disconnected")
                task.updated_at = datetime.now(timezone.utc)
                failed.append(task)
        return failed


store = Store()
