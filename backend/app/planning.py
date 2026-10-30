"""Chooses how an instruction becomes a plan: client-supplied, built-in rules, or Gemini."""

from __future__ import annotations

from typing import Any

from fastapi import status

from app import planner as planner_module
from app.actions import InvalidActionError, plan_from_instruction
from app.dispatch import deny
from app.models import Agent, User
from app.planner import PlannerError, PlannerResult
from app.ratelimit import planner_limiter
from app.store import store

NOTE_LIMIT = 300


def supplied_plan(steps: list[dict[str, Any]]) -> PlannerResult:
    return PlannerResult(steps=steps, planner="client")


def rules_plan(instruction: str) -> PlannerResult | None:
    """The built-in rules, or None when the instruction is not one of their phrases."""
    try:
        return PlannerResult(steps=plan_from_instruction(instruction), planner="rules")
    except InvalidActionError:
        return None


def llm_available() -> bool:
    return planner_module.get_planner() is not None


def unsupported_message() -> str:
    if llm_available():
        return "Could not understand that instruction"
    return "Unsupported instruction. Allowed: Open Notepad and type <message>"


async def llm_plan(user: User, agent: Agent, instruction: str) -> PlannerResult:
    """Asks Gemini for a plan. Refuses when rate limited or the planner fails; may return no steps."""
    llm = planner_module.get_planner()
    if llm is None:
        deny(status.HTTP_400_BAD_REQUEST, "invalid_instruction", unsupported_message(), user=user, agent=agent)
    if not planner_limiter.allow(user.id):
        deny(status.HTTP_429_TOO_MANY_REQUESTS, "planner_rate_limited", "Too many requests. Wait a moment.", user=user, agent=agent)
    try:
        result = await llm.plan(instruction, agent.permitted_apps)
    except PlannerError:
        deny(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "planner_failed",
            "The planner is unavailable right now. Try again in a moment.",
            user=user,
            agent=agent,
        )
    result.note = result.note.strip()[:NOTE_LIMIT]
    return result


def record_planned(user: User, agent: Agent, result: PlannerResult, event: str) -> None:
    store.add_audit(event, "info", f"{result.planner}: {len(result.steps)} step(s)", user_id=user.id, agent_id=agent.id)
