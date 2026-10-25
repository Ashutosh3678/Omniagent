"""Bearer-token checks for the mobile app and Windows agent."""

from __future__ import annotations

from fastapi import Header, HTTPException, Query, status

from app.config import AGENT_TOKEN, APP_TOKEN


def _token_from_header(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return ""
    return value.strip()


def require_app(authorization: str | None = Header(default=None)) -> str:
    token = _token_from_header(authorization)
    if token != APP_TOKEN:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid app token")
    return token


def require_agent(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> str:
    value = token or _token_from_header(authorization)
    if value != AGENT_TOKEN:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid agent token")
    return value
