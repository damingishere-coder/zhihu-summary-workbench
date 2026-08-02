from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.api.dependencies import get_broker
from backend.app.core.config import Settings, get_settings
from backend.app.db.session import get_db_session
from backend.app.models.core import ArticleDraft, Question, TaskJob, TaskLog
from backend.app.models.media import PublishRecord
from backend.app.schemas.dashboard import (
    DashboardMetrics,
    DashboardSummary,
    ServiceHealth,
)
from backend.app.services.queue import QueueBroker
from backend.app.services.serializers import task_to_read
from backend.app.services.settings import provider_mode


router = APIRouter(prefix="/dashboard", tags=["dashboard"])
PROCESSING_STATUSES = [
    "queued",
    "fetching_question",
    "fetching_answers",
    "cleaning_answers",
    "evaluating_answers",
    "extracting_claims",
    "generating_embeddings",
    "clustering_claims",
    "refining_clusters",
    "generating_opinion_map",
    "generating_article",
    "reviewing_article",
]


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(
    session: AsyncSession = Depends(get_db_session),
    broker: QueueBroker = Depends(get_broker),
    settings: Settings = Depends(get_settings),
) -> DashboardSummary:
    processing = int(
        (
            await session.scalar(
                select(func.count(TaskJob.id)).where(
                    TaskJob.status.in_(PROCESSING_STATUSES)
                )
            )
        )
        or 0
    )
    waiting_review = int(
        (
            await session.scalar(
                select(func.count(ArticleDraft.id)).where(
                    ArticleDraft.status == "waiting_review"
                )
            )
        )
        or 0
    )
    failed = int(
        (
            await session.scalar(
                select(func.count(TaskJob.id)).where(TaskJob.status == "failed")
            )
        )
        or 0
    )
    ready_to_publish = int(
        (
            await session.scalar(
                select(func.count(ArticleDraft.id)).where(
                    ArticleDraft.status == "review_approved"
                )
            )
        )
        or 0
    )
    published = int(
        (
            await session.scalar(
                select(func.count(PublishRecord.id)).where(
                    PublishRecord.status == "published"
                )
            )
        )
        or 0
    )
    recent_tasks = (
        await session.scalars(
            select(TaskJob)
            .options(selectinload(TaskJob.question))
            .order_by(TaskJob.created_at.desc())
            .limit(10)
        )
    ).all()
    recent_logs = (
        await session.scalars(
            select(TaskLog).order_by(TaskLog.created_at.desc()).limit(12)
        )
    ).all()
    queue = await broker.status()
    try:
        workers = await broker.workers()
    except Exception:
        workers = []
    try:
        await session.execute(text("SELECT 1"))
        database_state = "正常"
    except Exception:
        database_state = "异常"
    mode = await provider_mode(session, settings)
    return DashboardSummary(
        metrics=DashboardMetrics(
            today_plan=settings.daily_question_limit,
            processing=processing,
            waiting_review=waiting_review,
            ready_to_publish=ready_to_publish,
            published=published,
            failed=failed,
        ),
        health=ServiceHealth(
            database=database_state,
            redis="正常" if queue.connected else "异常",
            workers="正常" if any(not item.stale for item in workers) else "未在线",
            model="可用"
            if mode == "mock" or settings.deepseek_key_value
            else "未配置",
            provider_mode=mode,
        ),
        queue=queue,
        workers=workers,
        recent_tasks=[task_to_read(item) for item in recent_tasks],
        recent_logs=recent_logs,
    )
