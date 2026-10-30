"""Device pairing, listing, scope changes and revocation."""

from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.actions import KNOWN_APPS
from app.auth import get_current_user, hash_device_token, new_device_token
from app.config import PAIRING_CODE_TTL_SECONDS
from app.models import (
    Agent,
    AgentPublic,
    AgentRegistered,
    PairAgentRequest,
    PairingCodeResponse,
    UpdateAgentRequest,
    User,
    utcnow,
)
from app.ratelimit import pairing_limiter
from app.store import store

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

# No 0/O/1/I so a code read off a phone screen is hard to mistype.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 8


def _normalize_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def _code_hash(code: str) -> str:
    return hash_device_token(_normalize_code(code))


def _owned_agent(agent_id: str, user: User) -> Agent:
    agent = store.get_agent(agent_id, user.id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PC not found")
    return agent


@router.post("/pairing-code", response_model=PairingCodeResponse, status_code=status.HTTP_201_CREATED)
def create_pairing_code(user: User = Depends(get_current_user)) -> PairingCodeResponse:
    """A one-time code the user types into the PC agent. Valid for a few minutes."""
    raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
    expires_at = utcnow() + timedelta(seconds=PAIRING_CODE_TTL_SECONDS)
    store.add_pairing_code(user.id, _code_hash(raw), expires_at)
    store.add_audit("pairing_code_created", "info", user_id=user.id)
    return PairingCodeResponse(code=f"{raw[:4]}-{raw[4:]}", expires_at=expires_at)


@router.post("/pair", response_model=AgentRegistered)
def pair_agent(body: PairAgentRequest, request: Request) -> AgentRegistered:
    """Called by the PC agent (no login) with the code shown in the phone app."""
    client = request.client.host if request.client else "unknown"
    if pairing_limiter.blocked(client):
        store.add_audit("pairing_failed", "deny", "rate_limited")
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again later.")

    user_id = store.consume_pairing_code(_code_hash(body.code))
    if user_id is None:
        pairing_limiter.record_failure(client)
        store.add_audit("pairing_failed", "deny", "invalid_or_expired_code")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired pairing code")

    agent = Agent(id=store.new_id(), user_id=user_id, name=body.name.strip(), hostname=body.hostname.strip())
    device_token = new_device_token()
    store.add_agent(agent, hash_device_token(device_token))
    store.add_audit("pairing_succeeded", "permit", user_id=user_id, agent_id=agent.id)
    return AgentRegistered(**AgentPublic.from_agent(agent).model_dump(), device_token=device_token)


@router.get("", response_model=list[AgentPublic])
def list_agents(user: User = Depends(get_current_user)) -> list[AgentPublic]:
    return [AgentPublic.from_agent(agent) for agent in store.list_agents(user.id)]


@router.patch("/{agent_id}", response_model=AgentPublic)
def update_agent(
    agent_id: str,
    body: UpdateAgentRequest,
    user: User = Depends(get_current_user),
) -> AgentPublic:
    agent = _owned_agent(agent_id, user)
    if agent.status != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "This PC has been removed")

    changes: list[str] = []
    if body.name is not None:
        agent.name = body.name.strip()
        changes.append("name")
    if body.permitted_apps is not None:
        unknown = set(body.permitted_apps) - (KNOWN_APPS | agent.available_app_ids)
        if unknown:
            raise HTTPException(422, f"Unknown apps: {sorted(unknown)}")
        agent.permitted_apps = sorted(set(body.permitted_apps))
        changes.append("permitted_apps")
    if body.clear_expiry:
        agent.expires_at = None
        changes.append("expires_at")
    elif body.expires_at is not None:
        if body.expires_at <= utcnow():
            raise HTTPException(422, "Expiry must be in the future")
        agent.expires_at = body.expires_at
        changes.append("expires_at")

    store.update_agent(agent)
    store.add_audit("device_updated", "info", ",".join(changes), user_id=user.id, agent_id=agent.id)
    return AgentPublic.from_agent(agent)


@router.post("/{agent_id}/revoke", response_model=AgentPublic)
async def revoke_agent(agent_id: str, user: User = Depends(get_current_user)) -> AgentPublic:
    """Permanently removes a PC: its token stops working and any live connection is dropped."""
    agent = _owned_agent(agent_id, user)
    if agent.status != "revoked":
        agent.status = "revoked"
        agent.revoked_at = utcnow()
        store.update_agent(agent)
        store.fail_active_tasks(agent.id, "PC was removed")
        store.add_audit("device_revoked", "info", user_id=user.id, agent_id=agent.id)
    socket = store.sockets.get(agent.id)
    if socket is not None:
        try:
            await socket.close(code=4403)
        except Exception:
            pass
    return AgentPublic.from_agent(agent)
