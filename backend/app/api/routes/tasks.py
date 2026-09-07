from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.api.dependencies import get_broker
from backend.app.db.session import get_db_session
from backend.app.models.core import TaskJob
from backend.app.schemas.browser_bridge import RetryCollectionResponse
from backend.app.schemas.task import QueueStatus, TaskListResponse, TaskRead, WorkerRead
from backend.app.services.queue import QueueBroker
from backend.app.services.serializers import task_to_read
from backend.app.services.tasks import (
    cancel_task,
    resume_task_after_login,
    resume_task_after_verification,
    retry_collection_task,
    retry_task,
)


router = APIRouter(tags=["tasks"])


async def load_task(
    session: AsyncSession, task_id: str, *, logs: bool = False
) -> TaskJob | None:
    options = [selectinload(TaskJob.question)]
    if logs:
        options.append(selectinload(TaskJob.logs))
    return await session.scalar(
        select(TaskJob).options(*options).where(TaskJob.id == task_id)
    )


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    status_filter: str | None = Query(default=None, alias="status"),
    question_id: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
) -> TaskListResponse:
    conditions = []
    if status_filter:
        conditions.append(TaskJob.status == status_filter)
    if question_id:
        conditions.append(TaskJob.question_id == question_id)
    statement = (
        select(TaskJob)
        .options(selectinload(TaskJob.question))
        .where(*conditions)
        .order_by(TaskJob.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    count_statement = select(func.count(TaskJob.id)).where(*conditions)
    items = (await session.scalars(statement)).all()
    total = int((await session.scalar(count_statement)) or 0)
    return TaskListResponse(
        items=[task_to_read(item) for item in items],
        total=total,
    )


@router.get("/tasks/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> TaskRead:
    task = await load_task(session, task_id, logs=True)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task_to_read(task, include_logs=True)


@router.post("/tasks/{task_id}/retry", response_model=TaskRead)
async def retry_failed_task(
    task_id: str,
    session: AsyncSession = Depends(get_db_session),
    broker: QueueBroker = Depends(get_broker),
) -> TaskRead:
    task = await load_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        await retry_task(session, broker, task)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    task = await load_task(session, task_id)
    return task_to_read(task)


@router.post(
    "/tasks/{task_id}/retry-collection",
    response_model=RetryCollectionResponse,
)
async def retry_task_collection(
    task_id: str,
    session: AsyncSession = Depends(get_db_session),
    broker: QueueBroker = Depends(get_broker),
) -> RetryCollectionResponse:
    task = await load_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        job, dispatched = await retry_collection_task(session, broker, task)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RetryCollectionResponse(
        task_id=task.id,
        collection_job_id=job.id,
        status=task.status,
        dispatched=dispatched,
        message=(
            "已使用安全保存的采集结果恢复任务"
            if job.status == "completed"
            else
            "采集任务已发送到 Chrome 扩展"
            if dispatched
            else "采集任务已保存；请连接 Chrome 扩展后继续"
        ),
    )


@router.post("/tasks/{task_id}/cancel", response_model=TaskRead)
async def cancel_running_task(
    task_id: str,
    session: AsyncSession = Depends(get_db_session),
    broker: QueueBroker = Depends(get_broker),
) -> TaskRead:
    task = await load_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        await cancel_task(session, broker, task)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    task = await load_task(session, task_id)
    return task_to_read(task)


@router.post("/tasks/{task_id}/resume-after-login", response_model=TaskRead)
async def resume_waiting_task_after_login(
    task_id: str,
    session: AsyncSession = Depends(get_db_session),
    broker: QueueBroker = Depends(get_broker),
) -> TaskRead:
    task = await load_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        await resume_task_after_login(session, broker, task)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    task = await load_task(session, task_id)
    return task_to_read(task)


@router.post(
    "/tasks/{task_id}/resume-after-verification",
    response_model=TaskRead,
)
async def resume_waiting_task_after_verification(
    task_id: str,
    session: AsyncSession = Depends(get_db_session),
    broker: QueueBroker = Depends(get_broker),
) -> TaskRead:
    task = await load_task(session, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        await resume_task_after_verification(session, broker, task)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    task = await load_task(session, task_id)
    return task_to_read(task)


@router.get("/queues/status", response_model=QueueStatus)
async def get_queue_status(
    broker: QueueBroker = Depends(get_broker),
) -> QueueStatus:
    return await broker.status()


@router.get("/workers", response_model=list[WorkerRead])
async def get_workers(
    broker: QueueBroker = Depends(get_broker),
) -> list[WorkerRead]:
    try:
        return await broker.workers()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"无法读取 Worker 状态：{exc}") from exc


@router.get("/queues/status/stream")
async def stream_queue_status(
    request: Request,
    broker: QueueBroker = Depends(get_broker),
) -> StreamingResponse:
    async def event_stream():
        initial = await broker.status()
        yield f"event: snapshot\ndata: {initial.model_dump_json()}\n\n"
        try:
            async for event in broker.events():
                if await request.is_disconnected():
                    break
                event_type = event.get("type", "message")
                payload = json.dumps(event, ensure_ascii=False)
                yield f"event: {event_type}\ndata: {payload}\n\n"
        except Exception as exc:
            payload = json.dumps(
                {"type": "stream_error", "message": str(exc)}, ensure_ascii=False
            )
            yield f"event: stream_error\ndata: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/tasks/{task_id}/continue", response_model=TaskRead)
async def continue_task(task_id: str, allow_partial: bool = False, session: AsyncSession = Depends(get_db_session), broker: QueueBroker = Depends(get_broker)):
    from backend.app.services.checkpoints import resume_task
    task = await load_task(session, task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    try:
        await resume_task(session, broker, task, allow_partial=allow_partial)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return task_to_read(await load_task(session, task_id))
