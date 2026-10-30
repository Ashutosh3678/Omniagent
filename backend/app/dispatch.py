"""Fail-closed dispatch checks. Every decision, permit or deny, is audited."""

from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException, status

from app.actions import ACTION_APP
from app.models import Action, Agent, User
from app.store import store


def deny(
    http_status: int,
    reason: str,
    detail: str,
    *,
    user: User,
    agent: Agent | None = None,
    event: str = "dispatch_denied",
) -> NoReturn:
    store.add_audit(event, "deny", reason, user_id=user.id, agent_id=agent.id if agent else None)
    raise HTTPException(http_status, detail)


def authorize_dispatch(user: User, agent_id: str | None, action: Action) -> Agent:
    """Returns the agent only if every check passes; otherwise audits and raises.

    Checks run in order and the first failure wins: ownership, revoked, expired,
    online, then the app scope. There is no path that returns an agent on error.
    """
    if agent_id:
        agent = store.get_agent(agent_id, user.id)
        if agent is None:
            deny(status.HTTP_404_NOT_FOUND, "unknown_device", "PC not found", user=user)
    else:
        usable = [a for a in store.list_agents(user.id) if a.online and a.status == "active"]
        if not usable:
            deny(status.HTTP_503_SERVICE_UNAVAILABLE, "no_online_device", "No connected PC", user=user)
        if len(usable) > 1:
            deny(status.HTTP_409_CONFLICT, "ambiguous_device", "Choose which PC to use", user=user)
        agent = usable[0]

    if agent.status != "active":
        deny(status.HTTP_403_FORBIDDEN, "device_revoked", "This PC has been removed", user=user, agent=agent)
    if agent.expired:
        deny(status.HTTP_403_FORBIDDEN, "device_expired", "This PC's access has expired", user=user, agent=agent)
    if not agent.online or agent.id not in store.sockets:
        deny(status.HTTP_503_SERVICE_UNAVAILABLE, "device_offline", "This PC is offline", user=user, agent=agent)

    app_name = ACTION_APP.get(action.type)
    if app_name is None or app_name not in agent.permitted_apps:
        deny(
            status.HTTP_403_FORBIDDEN,
            "app_not_permitted",
            f"This PC is not allowed to use {app_name or action.type}",
            user=user,
            agent=agent,
        )
    return agent
