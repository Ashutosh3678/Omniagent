"""Agent registration and listing."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import require_agent, require_app
from app.models import Agent, AgentPublic, RegisterAgentRequest
from app.store import store

router = APIRouter(prefix="/v1/agents", tags=["agents"])


@router.post("/register", response_model=AgentPublic)
def register_agent(
    body: RegisterAgentRequest,
    _: str = Depends(require_agent),
) -> AgentPublic:
    agent = Agent(id=store.new_id(), name=body.name, hostname=body.hostname)
    store.agents[agent.id] = agent
    return AgentPublic(**agent.model_dump())


@router.get("", response_model=list[AgentPublic])
def list_agents(_: str = Depends(require_app)) -> list[AgentPublic]:
    return [AgentPublic(**agent.model_dump()) for agent in store.agents.values()]
