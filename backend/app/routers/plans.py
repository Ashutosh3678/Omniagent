"""Plan preview: show what would run, without running anything."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.auth import get_current_user
from app.config import LOW_CONFIDENCE
from app.dispatch import deny, resolve_device_for_preview
from app.models import PlanPreview, PlanPreviewRequest, User
from app.planning import llm_available, llm_plan, record_planned, rules_plan, unsupported_message
from app.validation import validate_plan

router = APIRouter(prefix="/api/v1/plans", tags=["plans"])


@router.post("/preview", response_model=PlanPreview)
async def preview_plan(body: PlanPreviewRequest, user: User = Depends(get_current_user)) -> PlanPreview:
    """Plans and validates the instruction for one of your PCs. Nothing is sent to the PC."""
    result = rules_plan(body.instruction)
    if result is None and not llm_available():
        deny(status.HTTP_400_BAD_REQUEST, "invalid_instruction", unsupported_message(), user=user)

    agent = resolve_device_for_preview(user, body.agent_id)
    if result is None:
        result = await llm_plan(user, agent, body.instruction)
    record_planned(user, agent, result, "plan_previewed")

    verdict = validate_plan(result.steps, agent.permitted_apps, agent.executable_actions)
    return PlanPreview(
        planner=result.planner,
        steps=verdict.steps,
        held_back=verdict.held_back,
        confidence=verdict.confidence,
        runnable=bool(verdict.steps),
        low_confidence=verdict.confidence is not None and verdict.confidence < LOW_CONFIDENCE,
        note=result.note,
        plan=result.steps,
    )
