"""Fail-closed dispatch checks. Every decision, permit or deny, is audited."""

from __future__ import annotations

from typing import Any, NoReturn

from fastapi import HTTPException, status

from app.models import Agent, PlanVerdict, User
from app.store import store
from app.validation import validate_plan

# HTTP status for a plan the validator refused entirely, keyed by the first held-back reason.
_DENIED_STATUS = {
    "app_not_permitted": status.HTTP_403_FORBIDDEN,
    "unknown_app": status.HTTP_403_FORBIDDEN,
}


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


def authorize_device(user: User, agent_id: str | None) -> Agent:
    """Returns the PC only if it is yours, active, unexpired and online.

    Checks run in order and the first failure wins; there is no path that returns
    an agent on error.
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
    return agent


def resolve_device_for_preview(user: User, agent_id: str | None) -> Agent:
    """The PC a plan is made for. It need not be online: previewing sends nothing."""
    if agent_id:
        agent = store.get_agent(agent_id, user.id)
        if agent is None:
            deny(status.HTTP_404_NOT_FOUND, "unknown_device", "PC not found", user=user)
    else:
        active = [a for a in store.list_agents(user.id) if a.status == "active" and not a.expired]
        if not active:
            deny(status.HTTP_503_SERVICE_UNAVAILABLE, "no_device", "Pair a PC first", user=user)
        if len(active) > 1:
            deny(status.HTTP_409_CONFLICT, "ambiguous_device", "Choose which PC to use", user=user)
        agent = active[0]
    if agent.status != "active":
        deny(status.HTTP_403_FORBIDDEN, "device_revoked", "This PC has been removed", user=user, agent=agent)
    if agent.expired:
        deny(status.HTTP_403_FORBIDDEN, "device_expired", "This PC's access has expired", user=user, agent=agent)
    return agent


def authorize_plan(user: User, agent: Agent, raw_steps: list[Any]) -> PlanVerdict:
    """Validates the plan against this PC's app scope.

    Held-back steps are audited. If nothing at all can run, the request is refused.
    """
    verdict = validate_plan(raw_steps, agent.permitted_apps)
    for held in verdict.held_back:
        store.add_audit(
            "plan_step_held_back",
            "deny",
            f"step {held.index + 1}: {held.reason}",
            user_id=user.id,
            agent_id=agent.id,
        )
    if not verdict.steps:
        first = verdict.held_back[0] if verdict.held_back else None
        reason = first.reason if first else "empty_plan"
        detail = first.detail if first else "The plan has no steps"
        deny(
            _DENIED_STATUS.get(reason, status.HTTP_422_UNPROCESSABLE_CONTENT),
            reason,
            detail,
            user=user,
            agent=agent,
        )
    return verdict
