"""Authenticated WebSocket between the backend and a Windows PC agent."""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth import device_token_matches, token_from_header
from app.config import STEP_TIMEOUT_SECONDS, TASK_TIMEOUT_SECONDS
from app.models import Task, utcnow
from app.schema import ACTION_TYPES
from app.store import store

logger = logging.getLogger(__name__)
router = APIRouter()

_STEP_STATUSES = {"running", "success", "failed", "unverified", "skipped"}
MAX_STEP_SCREENSHOT_BYTES = 1_500_000
_SCREENSHOT_TYPES = {"image/jpeg", "image/png"}


async def send_task(agent_id: str, task: Task) -> bool:
    socket = store.sockets.get(agent_id)
    if socket is None:
        return False
    try:
        await socket.send_json(
            {
                "type": "task",
                "task_id": task.id,
                "plan": [{"index": s.index, "action": s.action} for s in task.plan],
            }
        )
        return True
    except Exception:
        logger.exception("Failed to dispatch task %s to agent %s", task.id, agent_id)
        return False


async def send_cancel(agent_id: str, task_id: str) -> bool:
    """Tells the agent to stop a task after its current step. False if the PC is not connected."""
    socket = store.sockets.get(agent_id)
    if socket is None:
        return False
    try:
        await socket.send_json({"type": "cancel", "task_id": task_id})
        return True
    except Exception:
        logger.exception("Failed to send cancel for task %s to agent %s", task_id, agent_id)
        return False


async def fail_if_timed_out(task_id: str, step_count: int = 1) -> None:
    await asyncio.sleep(max(TASK_TIMEOUT_SECONDS, STEP_TIMEOUT_SECONDS * step_count))
    task = store.get_task(task_id)
    if task and task.status in {"pending", "running"}:
        task.status = "failed"
        task.error = "Task timed out"
        task.log("Task timed out")
        store.save_task(task)


@router.websocket("/api/v1/agents/{agent_id}/ws")
async def agent_socket(websocket: WebSocket, agent_id: str) -> None:
    agent = store.get_agent(agent_id)
    if agent is None:
        await websocket.close(code=4404)
        return
    presented = token_from_header(websocket.headers.get("authorization"))
    if not device_token_matches(presented, store.get_agent_token_hash(agent_id)):
        store.add_audit("connection_denied", "deny", "bad_device_token", user_id=agent.user_id, agent_id=agent_id)
        await websocket.close(code=4401)
        return
    if agent.status != "active" or agent.expired:
        reason = "device_revoked" if agent.status != "active" else "device_expired"
        store.add_audit("connection_denied", "deny", reason, user_id=agent.user_id, agent_id=agent_id)
        await websocket.close(code=4403)
        return

    await websocket.accept()
    store.set_online(agent_id, websocket)
    await websocket.send_json({"type": "hello_ok", "agent_id": agent_id})

    try:
        while True:
            message = await websocket.receive_json()
            await _handle_agent_message(agent_id, message)
    except WebSocketDisconnect:
        store.set_offline(agent_id)
    except Exception:
        logger.exception("Agent websocket error for %s", agent_id)
        store.set_offline(agent_id)
        await websocket.close()


def _decode_step_screenshot(message: dict[str, Any]) -> tuple[bytes, str] | None:
    encoded = message.get("screenshot_b64")
    if not isinstance(encoded, str) or not encoded:
        return None
    content_type = message.get("content_type") or "image/jpeg"
    if content_type not in _SCREENSHOT_TYPES or len(encoded) > MAX_STEP_SCREENSHOT_BYTES * 4 // 3 + 8:
        return None
    try:
        data = base64.b64decode(encoded, validate=True)
    except ValueError:
        return None
    return (data, content_type) if 0 < len(data) <= MAX_STEP_SCREENSHOT_BYTES else None


async def _handle_agent_message(agent_id: str, message: dict[str, Any]) -> None:
    kind = message.get("type")
    task_id = message.get("task_id")
    task = store.get_task(task_id) if task_id else None

    if kind == "pong":
        return

    if kind == "capabilities":
        actions = message.get("actions")
        if isinstance(actions, list):
            store.set_capabilities(agent_id, [a for a in actions if a in ACTION_TYPES])
        return

    if kind == "ack" and task and task.agent_id == agent_id:
        task.status = "running"
        task.log("Agent acknowledged task")
        store.save_task(task)
        return

    if kind == "log" and task and task.agent_id == agent_id:
        task.log(str(message.get("log") or ""))
        store.save_task(task)
        return

    if kind == "step" and task and task.agent_id == agent_id and task.status in {"pending", "running"}:
        index = message.get("index")
        new_status = message.get("status")
        if isinstance(index, int) and 0 <= index < len(task.plan) and new_status in _STEP_STATUSES:
            task.steps[index].status = new_status
            task.steps[index].detail = str(message.get("detail") or "")[:500]
            shot = _decode_step_screenshot(message)
            if shot is not None:
                store.save_step_screenshot(task.id, index, shot[0], shot[1])
                task.steps[index].has_screenshot = True
            task.updated_at = utcnow()
            store.save_task(task)
        return

    if kind == "result" and task and task.agent_id == agent_id:
        if task.status in {"completed", "partial", "failed"}:
            return  # already finished (cancelled, timed out, removed): do not overwrite
        reported = message.get("status")
        if reported == "completed":
            # The agent ran everything it was sent; held-back steps mean the plan is incomplete.
            task.status = "partial" if task.held_back else "completed"
        elif reported == "partial":
            task.status = "partial"
        else:
            task.status = "failed"
        for step in task.steps:
            if step.status in {"pending", "running"}:
                step.status = "skipped"
        task.summary = str(message.get("summary") or "")
        task.error = str(message.get("error") or "")
        screenshot_b64 = message.get("screenshot_b64")
        if screenshot_b64:
            try:
                store.save_screenshot(task.id, base64.b64decode(screenshot_b64))
                task.screenshot_id = task.id
            except Exception:
                task.log("Screenshot payload was invalid")
        task.log("Agent reported " + task.status)
        store.save_task(task)
        return

    logger.warning("Ignored agent message type=%s from %s", kind, agent_id)
