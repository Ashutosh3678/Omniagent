"""Task create, status, screenshot, and cancel endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.actions import InvalidActionError, parse_instruction
from app.auth import require_app
from app.models import CreateTaskRequest, Task, TaskPublic
from app.store import store
from app.ws import fail_if_timed_out, send_task

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])


@router.post("", response_model=TaskPublic, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: CreateTaskRequest,
    _: str = Depends(require_app),
) -> TaskPublic:
    try:
        action = parse_instruction(body.instruction)
    except InvalidActionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    agent = store.resolve_agent(body.agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No connected Windows PC agent")
    if not agent.online:
        raise HTTPException(status.HTTP_409_CONFLICT, "Agent is disconnected")

    task = Task(
        id=store.new_id(),
        agent_id=agent.id,
        instruction=body.instruction.strip(),
        action=action,
    )
    task.log("Task accepted")
    store.tasks[task.id] = task

    dispatched = await send_task(agent.id, task.id)
    if not dispatched:
        task.status = "failed"
        task.error = "Agent is disconnected"
        task.log("Dispatch failed")
        raise HTTPException(status.HTTP_409_CONFLICT, "Agent is disconnected")

    task.status = "running"
    task.log("Dispatched to agent")
    asyncio.create_task(fail_if_timed_out(task.id))
    return TaskPublic.from_task(task)


@router.get("", response_model=list[TaskPublic])
def list_tasks(_: str = Depends(require_app)) -> list[TaskPublic]:
    tasks = sorted(store.tasks.values(), key=lambda item: item.created_at, reverse=True)
    return [TaskPublic.from_task(task) for task in tasks]


@router.get("/{task_id}", response_model=TaskPublic)
def get_task(task_id: str, _: str = Depends(require_app)) -> TaskPublic:
    task = store.tasks.get(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return TaskPublic.from_task(task)


@router.get("/{task_id}/screenshot")
def get_screenshot(task_id: str, _: str = Depends(require_app)) -> Response:
    task = store.tasks.get(task_id)
    data = store.screenshots.get(task_id)
    if task is None or data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Screenshot not found")
    return Response(content=data, media_type="image/png")


@router.post("/{task_id}/cancel", response_model=TaskPublic)
def cancel_task(task_id: str, _: str = Depends(require_app)) -> TaskPublic:
    task = store.tasks.get(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    if task.status in {"completed", "failed"}:
        return TaskPublic.from_task(task)
    task.status = "failed"
    task.error = "Cancelled"
    task.log("Cancelled by client")
    return TaskPublic.from_task(task)
