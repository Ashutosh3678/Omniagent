"""Authenticated WebSocket between the backend and a Windows PC agent."""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import AGENT_TOKEN, TASK_TIMEOUT_SECONDS
from app.models import Step
from app.store import store

logger = logging.getLogger(__name__)
router = APIRouter()


async def send_task(agent_id: str, task_id: str) -> bool:
    task = store.tasks.get(task_id)
    socket = store.sockets.get(agent_id)
    if task is None or socket is None:
        return False
    try:
        await socket.send_json(
            {
                "type": "task",
                "task_id": task.id,
                "action": task.action.model_dump(),
            }
        )
        return True
    except Exception:
        logger.exception("Failed to dispatch task %s to agent %s", task_id, agent_id)
        return False


async def fail_if_timed_out(task_id: str) -> None:
    await asyncio.sleep(TASK_TIMEOUT_SECONDS)
    task = store.tasks.get(task_id)
    if task and task.status in {"pending", "running"}:
        task.status = "failed"
        task.error = "Task timed out"
        task.log("Task timed out")


@router.websocket("/v1/agents/{agent_id}/ws")
async def agent_socket(websocket: WebSocket, agent_id: str, token: str = "") -> None:
    if token != AGENT_TOKEN:
        await websocket.close(code=4401)
        return
    agent = store.agents.get(agent_id)
    if agent is None:
        await websocket.close(code=4404)
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


async def _handle_agent_message(agent_id: str, message: dict[str, Any]) -> None:
    kind = message.get("type")
    task_id = message.get("task_id")
    task = store.tasks.get(task_id) if task_id else None

    if kind == "pong":
        return

    if kind == "ack" and task and task.agent_id == agent_id:
        task.status = "running"
        task.log("Agent acknowledged task")
        return

    if kind == "progress" and task and task.agent_id == agent_id:
        if message.get("log"):
            task.log(str(message["log"]))
        if message.get("steps"):
            task.steps = [Step.model_validate(step) for step in message["steps"]]
        if task.status == "pending":
            task.status = "running"
        return

    if kind == "result" and task and task.agent_id == agent_id:
        status = message.get("status")
        task.status = "completed" if status == "completed" else "failed"
        task.summary = str(message.get("summary") or "")
        task.error = str(message.get("error") or "")
        if message.get("steps"):
            task.steps = [Step.model_validate(step) for step in message["steps"]]
        screenshot_b64 = message.get("screenshot_b64")
        if screenshot_b64:
            try:
                store.screenshots[task.id] = base64.b64decode(screenshot_b64)
                task.screenshot_id = task.id
            except Exception:
                task.log("Screenshot payload was invalid")
        task.log("Agent reported " + task.status)
        return

    logger.warning("Ignored agent message type=%s from %s", kind, agent_id)
