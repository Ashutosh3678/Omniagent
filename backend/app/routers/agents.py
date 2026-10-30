"""Agent registration and listing."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import get_current_user, hash_device_token, new_device_token
from app.models import Agent, AgentPublic, AgentRegistered, RegisterAgentRequest, User
from app.store import store

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.post("/register", response_model=AgentRegistered)
def register_agent(
    body: RegisterAgentRequest,
    user: User = Depends(get_current_user),
) -> AgentRegistered:
    """Registers a PC under the signed-in user and returns its one-time device token."""
    agent = Agent(id=store.new_id(), user_id=user.id, name=body.name, hostname=body.hostname)
    device_token = new_device_token()
    store.add_agent(agent, hash_device_token(device_token))
    return AgentRegistered(**agent.model_dump(), device_token=device_token)


@router.get("", response_model=list[AgentPublic])
def list_agents(user: User = Depends(get_current_user)) -> list[AgentPublic]:
    return [AgentPublic(**agent.model_dump()) for agent in store.list_agents(user.id)]
