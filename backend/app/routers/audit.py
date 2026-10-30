"""Read-only view of the user's dispatch and device audit trail."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.auth import get_current_user
from app.models import AuditEvent, User
from app.store import store

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("", response_model=list[AuditEvent])
def list_audit(
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(get_current_user),
) -> list[AuditEvent]:
    return store.list_audit(user.id, limit)
