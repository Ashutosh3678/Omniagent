"""Live updates for the phone: one WebSocket that pushes task and PC changes as they happen."""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth import decode_claims
from app.hub import hub
from app.store import store

logger = logging.getLogger(__name__)
router = APIRouter()

AUTH_TIMEOUT_SECONDS = 5.0

# Close codes the app understands.
CLOSE_UNAUTHORIZED = 4401
CLOSE_TOO_MANY = 4429

store.subscribe(hub.on_store_event)


@router.websocket("/api/v1/events")
async def events(websocket: WebSocket) -> None:
    """Send `{"type": "auth", "token": "<access token>"}` first. The token is not accepted in the URL,
    where it would end up in logs. Events are snapshots: `task`, `agent`, or `resync` (reload everything)."""
    await websocket.accept()

    try:
        first = await asyncio.wait_for(websocket.receive_json(), AUTH_TIMEOUT_SECONDS)
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError, KeyError, RuntimeError):
        await _close(websocket, CLOSE_UNAUTHORIZED)
        return

    token = first.get("token") if isinstance(first, dict) and first.get("type") == "auth" else None
    claims = decode_claims(token) if isinstance(token, str) else None
    user = store.get_user(str(claims["sub"])) if claims else None
    if user is None:
        await _close(websocket, CLOSE_UNAUTHORIZED)
        return

    subscription = hub.subscribe(user.id, asyncio.get_running_loop())
    if subscription is None:
        await _close(websocket, CLOSE_TOO_MANY)
        return

    expires_at = float(claims["exp"])
    try:
        await websocket.send_json({"type": "hello"})
        receiver = asyncio.create_task(websocket.receive_text())  # only to notice the phone leaving
        getter = asyncio.create_task(subscription.queue.get())
        try:
            while True:
                done, _ = await asyncio.wait(
                    {receiver, getter},
                    timeout=max(0.0, min(expires_at - time.time(), 60.0)),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if time.time() >= expires_at:
                    await _close(websocket, CLOSE_UNAUTHORIZED)  # the login ran out: sign in again
                    return
                if receiver in done:
                    receiver.result()  # raises WebSocketDisconnect when the phone goes away
                    receiver = asyncio.create_task(websocket.receive_text())  # ignore anything it sends
                if getter in done:
                    await websocket.send_json(getter.result())
                    getter = asyncio.create_task(subscription.queue.get())
        finally:
            receiver.cancel()
            getter.cancel()
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception:
        logger.exception("Event stream for user %s failed", user.id)
    finally:
        hub.unsubscribe(subscription)


async def _close(websocket: WebSocket, code: int) -> None:
    try:
        await websocket.close(code=code)
    except RuntimeError:
        pass
