from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import REPOSITORY_ROOT, Settings
from backend.app.models.content import QuestionScore
from backend.app.models.core import ArticleDraft, ArticleVersion, AuditLog
from backend.app.models.media import (
    BrowserSession,
    ImageDraft,
    ImageVersion,
    PublishRecord,
    PublishSchedule,
)
from backend.app.schemas.publish import (
    BrowserSafetyState,
    PublishReadiness,
    PublishRecordRead,
    PublishScheduleRead,
)
from backend.app.services.settings import get_setting


CONFIRMATION_TEXT = "确认发布"
TERMINAL_SCHEDULE_STATUSES = {"completed", "cancelled", "failed"}


def _day_bounds(value: date) -> tuple[datetime, datetime]:
    local_timezone = datetime.now().astimezone().tzinfo or timezone.utc
    start_local = datetime.combine(value, time.min).replace(
        tzinfo=local_timezone
    )
    return (
        start_local.astimezone(timezone.utc),
        (start_local + timedelta(days=1)).astimezone(timezone.utc),
    )


async def publish_readiness(
    session: AsyncSession, draft: ArticleDraft
) -> PublishReadiness:
    article = await session.scalar(
        select(ArticleVersion).where(
            ArticleVersion.draft_id == draft.id,
            ArticleVersion.version == draft.current_version,
        )
    )
    image_draft = await session.scalar(
        select(ImageDraft)
        .where(ImageDraft.article_draft_id == draft.id)
        .order_by(ImageDraft.created_at.desc())
        .limit(1)
    )
    image = None
    if image_draft:
        image = await session.scalar(
            select(ImageVersion).where(
                ImageVersion.image_draft_id == image_draft.id,
                ImageVersion.version == image_draft.current_version,
            )
        )
    score = await session.scalar(
        select(QuestionScore)
        .where(QuestionScore.question_id == draft.question_id)
        .order_by(QuestionScore.created_at.desc())
        .limit(1)
    )
    blockers: list[str] = []
    warnings: list[str] = []
    approved = draft.status == "review_approved"
    rendered = bool(
        image
        and image.render_status == "rendered"
        and image.rendered_path
        and Path(image.rendered_path).is_file()
    )
    if not approved:
        blockers.append("文章尚未通过草稿审核")
    if not article:
        blockers.append("文章当前版本不存在")
    if not rendered:
        blockers.append("信息图尚未成功渲染")
    risk_level = score.risk_level if score else "unknown"
    if risk_level in {"high", "blocked"}:
        blockers.append("内容风险等级较高，需要先处理风险项")
    elif risk_level not in {"normal", "low"}:
        warnings.append("当前没有明确的低风险评估，请在发布前人工核验")
    return PublishReadiness(
        draft_id=draft.id,
        ready=not blockers,
        article_approved=approved,
        article_version_id=article.id if article else None,
        article_version=article.version if article else None,
        image_rendered=rendered,
        image_version_id=image.id if image else None,
        image_version=image.version if image else None,
        risk_level=risk_level,
        blockers=blockers,
        warnings=warnings,
    )


async def _conflicts(
    session: AsyncSession,
    *,
    scheduled_for: datetime,
    settings: Settings,
    exclude_id: str | None = None,
) -> dict[str, Any]:
    current = scheduled_for
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local_current = current.astimezone()
    start, end = _day_bounds(local_current.date())
    daily_limit = int(
        await get_setting(
            session, "daily_publish_limit", settings.daily_publish_limit
        )
    )
    interval_minutes = int(
        await get_setting(
            session, "publish_interval_minutes", settings.publish_interval_minutes
        )
    )
    statement = select(PublishSchedule).where(
        PublishSchedule.scheduled_for >= start,
        PublishSchedule.scheduled_for < end,
        PublishSchedule.status.not_in(TERMINAL_SCHEDULE_STATUSES),
    )
    if exclude_id:
        statement = statement.where(PublishSchedule.id != exclude_id)
    items = list((await session.scalars(statement)).all())
    messages: list[str] = []
    if len(items) >= daily_limit:
        messages.append(f"当天排期已达到 {daily_limit} 条上限")
    for item in items:
        existing = item.scheduled_for
        if existing.tzinfo is None:
            existing = existing.replace(tzinfo=timezone.utc)
        if abs((existing - current).total_seconds()) < interval_minutes * 60:
            messages.append(
                f"与 {existing.isoformat()} 的排期小于 {interval_minutes} 分钟"
            )
            break
    return {
        "has_conflict": bool(messages),
        "messages": messages,
        "daily_count": len(items),
        "daily_limit": daily_limit,
        "interval_minutes": interval_minutes,
    }


async def create_publish_schedule(
    session: AsyncSession,
    draft: ArticleDraft,
    *,
    scheduled_for: datetime,
    mode: str,
    settings: Settings,
) -> PublishSchedule:
    readiness = await publish_readiness(session, draft)
    if not readiness.ready:
        raise ValueError("；".join(readiness.blockers))
    duplicate = await session.scalar(
        select(PublishSchedule).where(
            PublishSchedule.article_draft_id == draft.id,
            PublishSchedule.status.not_in(TERMINAL_SCHEDULE_STATUSES),
        )
    )
    if duplicate:
        raise ValueError("该草稿已经有未结束的发布排期")
    conflict = await _conflicts(
        session, scheduled_for=scheduled_for, settings=settings
    )
    if conflict["has_conflict"]:
        raise ValueError("；".join(conflict["messages"]))
    item = PublishSchedule(
        article_draft_id=draft.id,
        article_version_id=readiness.article_version_id,
        image_version_id=readiness.image_version_id,
        scheduled_for=scheduled_for,
        mode=mode,
        status="scheduled",
        requires_confirmation=True,
        sort_order=conflict["daily_count"],
        interval_minutes=conflict["interval_minutes"],
        conflict_state=conflict,
    )
    session.add(item)
    await session.flush()
    session.add(
        AuditLog(
            actor="operator",
            action="publish.schedule_created",
            entity_type="publish_schedule",
            entity_id=item.id,
            after_data={
                "draft_id": draft.id,
                "article_version_id": readiness.article_version_id,
                "image_version_id": readiness.image_version_id,
                "scheduled_for": scheduled_for.isoformat(),
                "mode": mode,
            },
        )
    )
    await session.commit()
    await session.refresh(item)
    return item


async def update_publish_schedule(
    session: AsyncSession,
    item: PublishSchedule,
    *,
    scheduled_for: datetime | None,
    mode: str | None,
    sort_order: int | None,
    settings: Settings,
) -> PublishSchedule:
    if item.status != "scheduled":
        raise ValueError("只有待发布排期可以调整")
    before = {
        "scheduled_for": item.scheduled_for.isoformat(),
        "mode": item.mode,
        "sort_order": item.sort_order,
    }
    target_time = scheduled_for or item.scheduled_for
    conflict = await _conflicts(
        session,
        scheduled_for=target_time,
        settings=settings,
        exclude_id=item.id,
    )
    if conflict["has_conflict"]:
        raise ValueError("；".join(conflict["messages"]))
    item.scheduled_for = target_time
    if mode is not None:
        item.mode = mode
    if sort_order is not None:
        item.sort_order = sort_order
    item.interval_minutes = conflict["interval_minutes"]
    item.conflict_state = conflict
    session.add(
        AuditLog(
            actor="operator",
            action="publish.schedule_updated",
            entity_type="publish_schedule",
            entity_id=item.id,
            before_data=before,
            after_data={
                "scheduled_for": item.scheduled_for.isoformat(),
                "mode": item.mode,
                "sort_order": item.sort_order,
            },
        )
    )
    await session.commit()
    await session.refresh(item)
    return item


async def cancel_publish_schedule(
    session: AsyncSession, item: PublishSchedule
) -> PublishSchedule:
    if item.status in TERMINAL_SCHEDULE_STATUSES:
        raise ValueError("该排期已经结束")
    item.status = "cancelled"
    session.add(
        AuditLog(
            actor="operator",
            action="publish.schedule_cancelled",
            entity_type="publish_schedule",
            entity_id=item.id,
            after_data={"status": "cancelled"},
        )
    )
    await session.commit()
    await session.refresh(item)
    return item


class ZhihuBrowserClient:
    """只做安全状态判断；不会在未确认、未登录或有验证码时继续。"""

    def __init__(self, profile_reference: str) -> None:
        self.profile_reference = profile_reference.strip()

    async def inspect(self) -> BrowserSafetyState:
        if not self.profile_reference:
            return BrowserSafetyState(
                state="profile_missing",
                safe_to_continue=False,
                message="尚未配置本机 Chrome 用户数据目录，已保持人工发布模式",
                profile_configured=False,
            )
        if not Path(self.profile_reference).exists():
            return BrowserSafetyState(
                state="browser_unavailable",
                safe_to_continue=False,
                message="配置的浏览器用户数据目录不存在，请在设置页重新选择",
                profile_configured=True,
            )
        return BrowserSafetyState(
            state="ready",
            safe_to_continue=True,
            message="浏览器资料目录可用；实际发布前仍会再次检查登录和验证码",
            profile_configured=True,
        )


class BrowserSessionManager:
    def __init__(self, profile_reference: str) -> None:
        self.client = ZhihuBrowserClient(profile_reference)

    async def inspect(self, session: AsyncSession) -> BrowserSafetyState:
        state = await self.client.inspect()
        row = await session.scalar(
            select(BrowserSession)
            .where(BrowserSession.adapter == "zhihu")
            .order_by(BrowserSession.updated_at.desc())
            .limit(1)
        )
        if not row:
            row = BrowserSession(adapter="zhihu")
            session.add(row)
        row.status = state.state
        row.profile_reference = (
            self.client.profile_reference if state.profile_configured else ""
        )
        row.last_error = None if state.safe_to_continue else state.message
        await session.commit()
        return state


class DraftPublisher:
    def __init__(self, manager: BrowserSessionManager) -> None:
        self.manager = manager

    async def prepare(self, session: AsyncSession) -> BrowserSafetyState:
        return await self.manager.inspect(session)


async def execute_publish_schedule(
    session: AsyncSession,
    item: PublishSchedule,
    *,
    confirmation: str,
    settings: Settings,
) -> PublishRecord:
    if confirmation != CONFIRMATION_TEXT:
        raise ValueError(f"请输入“{CONFIRMATION_TEXT}”后再继续")
    if item.status != "scheduled":
        raise ValueError("该排期当前不能执行")
    draft = await session.get(ArticleDraft, item.article_draft_id)
    if not draft:
        raise ValueError("关联草稿不存在")
    executed_at = datetime.now(timezone.utc)
    item.confirmed_at = executed_at
    item.confirmed_by = "operator"
    item.executed_at = executed_at
    details: dict[str, Any] = {
        "mode": item.mode,
        "article_version_id": item.article_version_id,
        "image_version_id": item.image_version_id,
        "confirmation": CONFIRMATION_TEXT,
    }
    status = "manual_package_ready"
    error_message = None
    if item.mode == "assisted":
        profile = str(
            await get_setting(
                session,
                "browser_user_data_dir",
                settings.zhihu_browser_user_data_dir,
            )
        )
        safety = await DraftPublisher(
            BrowserSessionManager(profile)
        ).prepare(session)
        details["browser_safety"] = safety.model_dump(mode="json")
        if not safety.safe_to_continue:
            status = "paused"
            item.status = "paused"
            error_message = safety.message
        else:
            # 第三阶段坚持安全边界：准备好浏览器资料后仍停在人工复核点，
            # 不绕过登录、验证码或平台风控，也不在后台静默提交。
            status = "awaiting_manual_browser_review"
            item.status = "awaiting_manual_review"
    else:
        item.status = "manual_package_ready"
    record = PublishRecord(
        schedule_id=item.id,
        article_version_id=item.article_version_id,
        image_version_id=item.image_version_id,
        status=status,
        error_message=error_message,
        details=details,
        attempt_count=1,
    )
    session.add(record)
    await session.flush()
    session.add(
        AuditLog(
            actor="operator",
            action="publish.execution_confirmed",
            entity_type="publish_schedule",
            entity_id=item.id,
            after_data={"record_id": record.id, "status": status, **details},
        )
    )
    await session.commit()
    await session.refresh(record)
    return record


async def schedule_to_read(
    session: AsyncSession, item: PublishSchedule
) -> PublishScheduleRead:
    draft = await session.get(ArticleDraft, item.article_draft_id)
    article = (
        await session.get(ArticleVersion, item.article_version_id)
        if item.article_version_id
        else None
    )
    image = (
        await session.get(ImageVersion, item.image_version_id)
        if item.image_version_id
        else None
    )
    return PublishScheduleRead(
        id=item.id,
        article_draft_id=item.article_draft_id,
        article_title=draft.title if draft else "",
        article_version_id=item.article_version_id,
        article_version=article.version if article else None,
        image_version_id=item.image_version_id,
        image_version=image.version if image else None,
        scheduled_for=item.scheduled_for,
        mode=item.mode,
        status=item.status,
        requires_confirmation=item.requires_confirmation,
        sort_order=item.sort_order,
        interval_minutes=item.interval_minutes,
        conflict_state=item.conflict_state or {},
        confirmed_at=item.confirmed_at,
        confirmed_by=item.confirmed_by,
        executed_at=item.executed_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def record_to_read(item: PublishRecord) -> PublishRecordRead:
    screenshot_url = (
        f"/api/publish-records/{item.id}/screenshot"
        if item.screenshot_path
        else None
    )
    return PublishRecordRead(
        id=item.id,
        schedule_id=item.schedule_id,
        article_version_id=item.article_version_id,
        image_version_id=item.image_version_id,
        status=item.status,
        final_url=item.final_url,
        error_message=item.error_message,
        screenshot_url=screenshot_url,
        attempt_count=item.attempt_count,
        details=item.details or {},
        created_at=item.created_at,
    )


def resolve_publish_screenshot(item: PublishRecord) -> Path:
    if not item.screenshot_path:
        raise FileNotFoundError("该发布记录没有浏览器截图")
    path = Path(item.screenshot_path).resolve()
    allowed = (REPOSITORY_ROOT / "data" / "publish").resolve()
    if allowed not in path.parents or not path.is_file():
        raise FileNotFoundError("发布截图不存在或路径不安全")
    return path
