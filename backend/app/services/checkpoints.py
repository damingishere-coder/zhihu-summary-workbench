"""Durable stage results and explicit, manual recovery of interrupted work."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.core import TaskJob, Question, TaskLog
from backend.app.models.browser_bridge import CollectionJob


TERMINAL = {"waiting_review", "review_approved", "failed", "cancelled", "paused", "image_result_unknown"}


class PipelinePaused(RuntimeError):
    pass


async def checkpoint(
    session: AsyncSession, task: TaskJob, key: str,
    execute: Callable[[], Awaitable[Any]],
    encode: Callable[[Any], Any] = lambda value: value,
    decode: Callable[[Any], Any] = lambda value: value,
) -> Any:
    saved = (task.result or {}).get("checkpoints", {})
    if key in saved:
        return decode(saved[key])
    result = await execute()
    task.result = {**(task.result or {}), "checkpoints": {**saved, key: encode(result)}}
    await session.commit()
    return result


async def recover_interrupted_tasks(session: AsyncSession) -> int:
    """Called once by the API before dispatchers/workers start. Never enqueues."""
    tasks = list((await session.scalars(select(TaskJob).where(TaskJob.status.not_in(TERMINAL)))).all())
    for task in tasks:
        interrupted = task.stage
        task.status = "paused"
        task.worker_id = None
        task.payload = {**(task.payload or {}), "pause_requested": True}
        task.error_message = f"服务已重启；已保留 {interrupted} 阶段进度，请点击继续"
        await session.execute(update(Question).where(Question.id == task.question_id).values(status="paused"))
        session.add(TaskLog(task_id=task.id, stage=interrupted, level="warning", message=task.error_message))
    await session.execute(update(CollectionJob).where(CollectionJob.status.in_(["pending", "dispatched"])).values(status="paused"))
    await session.commit()
    return len(tasks)


async def pause_tasks(session: AsyncSession, task_ids: list[str]) -> int:
    tasks = list((await session.scalars(select(TaskJob).where(TaskJob.id.in_(task_ids), TaskJob.status.not_in(TERMINAL)))).all())
    for task in tasks:
        task.payload = {**(task.payload or {}), "pause_requested": True}
        if task.status in {"queued", "waiting_browser", "waiting_login", "waiting_verification"}:
            task.status = "paused"
            await session.execute(update(Question).where(Question.id == task.question_id).values(status="paused"))
        await session.execute(update(CollectionJob).where(CollectionJob.task_id == task.id, CollectionJob.status.in_(["pending", "dispatched"])).values(status="paused"))
    await session.commit()
    return len(tasks)


async def resume_task(session: AsyncSession, broker, task: TaskJob, *, allow_partial: bool = False) -> None:
    if task.status == "image_result_unknown":
        from backend.app.ai.providers.codex_image import collect_artifact
        from backend.app.core.config import REPOSITORY_ROOT, get_settings
        from backend.app.services.settings import configured_settings_copy
        try:
            await __import__("asyncio").to_thread(collect_artifact, REPOSITORY_ROOT / "data" / "generated" / task.id,
                                                await configured_settings_copy(session, get_settings()))
        except ValueError as exc:
            raise ValueError("尚未找到本次请求的有效图片，继续保持暂停，不会重新生图") from exc
        task.status = "paused"
    if task.status not in {"paused", "failed", "cancelled", "waiting_browser", "waiting_login", "waiting_verification"}:
        return
    if (task.error_message or "").startswith("资料不足") and not allow_partial:
        raise ValueError("采集尚未确认完整；可查看已保存回答，选择‘按现有资料继续’，文章将明确标注采集范围")
    if allow_partial:
        task.payload = {**task.payload, "accept_partial": True}
    # Retain accumulated batches. The new dispatch receives a new nonce only for a new job.
    import secrets
    jobs = list((await session.scalars(select(CollectionJob).where(CollectionJob.task_id == task.id, CollectionJob.status.in_(["paused", "blocked", "failed", "cancelled"])))).all())
    for job in jobs:
        job.status = "pending"
        job.error_message = None
        job.nonce = secrets.token_urlsafe(24)
        job.client_id = None
    task.status = "queued"
    task.payload = {**(task.payload or {}), "pause_requested": False}
    task.cancel_requested = False
    task.error_message = None
    task.completed_at = None
    await session.execute(update(Question).where(Question.id == task.question_id).values(status="queued"))
    await session.commit()
    try:
        await broker.enqueue(task.id)
    except Exception:
        task.status = "paused"
        task.payload = {**task.payload, "pause_requested": True}
        await session.execute(update(Question).where(Question.id == task.question_id).values(status="paused"))
        await session.execute(update(CollectionJob).where(CollectionJob.task_id == task.id, CollectionJob.status.in_(["pending", "dispatched"])).values(status="paused"))
        task.error_message = "恢复入队失败，已有结果保留，请稍后继续"
        await session.commit()
        raise
