from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_broker
from backend.app.core.config import Settings, get_settings
from backend.app.db.session import get_db_session
from backend.app.models.core import ArticleDraft, DailyPlan, OpenSourceReference
from backend.app.models.media import PublishRecord, PublishSchedule
from backend.app.schemas.publish import (
    BrowserSafetyState,
    DailyPlanRead,
    DailyPlanRunResult,
    DailyPlanUpdate,
    ModelUsageOverview,
    OpenSourceReferenceRead,
    PublishExecuteRequest,
    PublishReadiness,
    PublishRecordRead,
    PublishScheduleCreate,
    PublishScheduleRead,
    PublishScheduleUpdate,
)
from backend.app.services.daily_plan import (
    execute_daily_plan,
    get_or_create_daily_plan,
    update_daily_plan,
)
from backend.app.services.publishing import (
    BrowserSessionManager,
    cancel_publish_schedule,
    create_publish_schedule,
    execute_publish_schedule,
    publish_readiness,
    record_to_read,
    resolve_publish_screenshot,
    schedule_to_read,
    update_publish_schedule,
)
from backend.app.services.queue import QueueBroker
from backend.app.services.settings import get_setting
from backend.app.services.usage import model_usage_overview


router = APIRouter(tags=["publishing"])


@router.get(
    "/drafts/{draft_id}/publish-readiness",
    response_model=PublishReadiness,
)
async def get_publish_readiness(
    draft_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> PublishReadiness:
    draft = await session.get(ArticleDraft, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")
    return await publish_readiness(session, draft)


@router.get("/publish-schedules", response_model=list[PublishScheduleRead])
async def list_publish_schedules(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> list[PublishScheduleRead]:
    statement = select(PublishSchedule).order_by(
        PublishSchedule.scheduled_for, PublishSchedule.sort_order
    )
    if start:
        statement = statement.where(PublishSchedule.scheduled_for >= start)
    if end:
        statement = statement.where(PublishSchedule.scheduled_for < end)
    items = list((await session.scalars(statement)).all())
    return [await schedule_to_read(session, item) for item in items]


@router.post("/publish-schedules", response_model=PublishScheduleRead)
async def post_publish_schedule(
    payload: PublishScheduleCreate,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> PublishScheduleRead:
    draft = await session.get(ArticleDraft, payload.article_draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")
    try:
        item = await create_publish_schedule(
            session,
            draft,
            scheduled_for=payload.scheduled_for,
            mode=payload.mode,
            settings=settings,
        )
        return await schedule_to_read(session, item)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch(
    "/publish-schedules/{schedule_id}", response_model=PublishScheduleRead
)
async def patch_publish_schedule(
    schedule_id: str,
    payload: PublishScheduleUpdate,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> PublishScheduleRead:
    item = await session.get(PublishSchedule, schedule_id)
    if not item:
        raise HTTPException(status_code=404, detail="发布排期不存在")
    try:
        item = await update_publish_schedule(
            session,
            item,
            scheduled_for=payload.scheduled_for,
            mode=payload.mode,
            sort_order=payload.sort_order,
            settings=settings,
        )
        return await schedule_to_read(session, item)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete(
    "/publish-schedules/{schedule_id}", response_model=PublishScheduleRead
)
async def delete_publish_schedule(
    schedule_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> PublishScheduleRead:
    item = await session.get(PublishSchedule, schedule_id)
    if not item:
        raise HTTPException(status_code=404, detail="发布排期不存在")
    try:
        item = await cancel_publish_schedule(session, item)
        return await schedule_to_read(session, item)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/publish-schedules/{schedule_id}/execute",
    response_model=PublishRecordRead,
)
async def post_publish_execute(
    schedule_id: str,
    payload: PublishExecuteRequest,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> PublishRecordRead:
    item = await session.get(PublishSchedule, schedule_id)
    if not item:
        raise HTTPException(status_code=404, detail="发布排期不存在")
    try:
        record = await execute_publish_schedule(
            session,
            item,
            confirmation=payload.confirmation,
            settings=settings,
        )
        return record_to_read(record)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/publish-records", response_model=list[PublishRecordRead])
async def list_publish_records(
    session: AsyncSession = Depends(get_db_session),
) -> list[PublishRecordRead]:
    items = list(
        (
            await session.scalars(
                select(PublishRecord)
                .order_by(PublishRecord.created_at.desc())
                .limit(200)
            )
        ).all()
    )
    return [record_to_read(item) for item in items]


@router.get("/publish-records/{record_id}/screenshot")
async def get_publish_screenshot(
    record_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> FileResponse:
    item = await session.get(PublishRecord, record_id)
    if not item:
        raise HTTPException(status_code=404, detail="发布记录不存在")
    try:
        path = resolve_publish_screenshot(item)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="image/png")


@router.get("/settings/browser/test", response_model=BrowserSafetyState)
async def test_browser_settings(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> BrowserSafetyState:
    profile = str(
        await get_setting(
            session,
            "browser_user_data_dir",
            settings.zhihu_browser_user_data_dir,
        )
    )
    return await BrowserSessionManager(profile).inspect(session)


@router.get("/plans/today", response_model=DailyPlanRead)
async def get_today_plan(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DailyPlan:
    return await get_or_create_daily_plan(session, settings)


@router.patch("/plans/today", response_model=DailyPlanRead)
async def patch_today_plan(
    payload: DailyPlanUpdate,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DailyPlan:
    item = await get_or_create_daily_plan(session, settings)
    try:
        return await update_daily_plan(
            session, item, payload.model_dump(exclude_none=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/plans/today/run", response_model=DailyPlanRunResult)
async def run_today_plan(
    session: AsyncSession = Depends(get_db_session),
    broker: QueueBroker = Depends(get_broker),
    settings: Settings = Depends(get_settings),
) -> DailyPlanRunResult:
    item = await get_or_create_daily_plan(session, settings)
    return await execute_daily_plan(
        session, broker, item, settings, trigger="manual"
    )


@router.get("/model-usage", response_model=ModelUsageOverview)
async def get_model_usage(
    target: date = Query(default_factory=lambda: datetime.now().astimezone().date()),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ModelUsageOverview:
    return await model_usage_overview(session, settings, target)


@router.get(
    "/open-source-references",
    response_model=list[OpenSourceReferenceRead],
)
async def list_open_source_references(
    session: AsyncSession = Depends(get_db_session),
) -> list[OpenSourceReference]:
    return list(
        (
            await session.scalars(
                select(OpenSourceReference).order_by(OpenSourceReference.name)
            )
        ).all()
    )
