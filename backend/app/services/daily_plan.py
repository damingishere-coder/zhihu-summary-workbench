from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select, case
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings
from backend.app.models.core import DailyPlan, Question
from backend.app.schemas.publish import DailyPlanRunResult
from backend.app.services.queue import QueueBroker
from backend.app.services.settings import get_setting
from backend.app.services.tasks import create_task


async def get_or_create_daily_plan(
    session: AsyncSession, settings: Settings, value: date | None = None
) -> DailyPlan:
    target = value or datetime.now().astimezone().date()
    item = await session.scalar(
        select(DailyPlan).where(DailyPlan.plan_date == target)
    )
    if item:
        return item
    item = DailyPlan(
        plan_date=target,
        question_limit=int(
            await get_setting(
                session, "daily_question_limit", settings.daily_question_limit
            )
        ),
        hot_quota=int(
            await get_setting(
                session, "hot_question_quota", settings.hot_question_quota
            )
        ),
        manual_quota=int(
            await get_setting(
                session, "manual_question_quota", settings.manual_question_quota
            )
        ),
        execute_time=str(
            await get_setting(session, "daily_plan_time", settings.daily_plan_time)
        ),
        max_concurrency=int(
            await get_setting(
                session, "max_ai_concurrency", settings.max_ai_concurrency
            )
        ),
        max_answers=int(
            await get_setting(
                session,
                "max_answers_per_question",
                settings.max_answers_per_question,
            )
        ),
        daily_publish_limit=int(
            await get_setting(
                session, "daily_publish_limit", settings.daily_publish_limit
            )
        ),
        publish_interval_minutes=int(
            await get_setting(
                session,
                "publish_interval_minutes",
                settings.publish_interval_minutes,
            )
        ),
        auto_production=bool(
            await get_setting(
                session,
                "auto_production_enabled",
                settings.auto_production_enabled,
            )
        ),
        auto_publish=bool(
            await get_setting(
                session,
                "auto_publish_enabled",
                settings.auto_publish_enabled,
            )
        ),
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def update_daily_plan(
    session: AsyncSession, item: DailyPlan, values: dict[str, object]
) -> DailyPlan:
    if values.get("auto_production") or values.get("auto_publish"):
        raise ValueError("当前采用手动执行计划、人工发布，不支持开启自动开关")
    target = {
        "question_limit": int(values.get("question_limit", item.question_limit)),
        "hot_quota": int(values.get("hot_quota", item.hot_quota)),
        "manual_quota": int(values.get("manual_quota", item.manual_quota)),
    }
    if target["hot_quota"] + target["manual_quota"] > target["question_limit"]:
        raise ValueError("热门配额与手动配额之和不能超过每日问题数")
    for key, value in values.items():
        setattr(item, key, value)
    item.auto_production = False
    item.auto_publish = False
    await session.commit()
    await session.refresh(item)
    return item


_plan_lock = __import__("asyncio").Lock()


async def execute_daily_plan(session, broker, item, settings, *, trigger):
    from backend.app.models.core import TaskJob
    from backend.app.services.checkpoints import resume_task
    from backend.app.services.hot_questions import sync_hot_questions
    if trigger != "manual":
        return DailyPlanRunResult(plan=item, message="请在工作台手动执行今日计划")
    async with _plan_lock:
        await session.refresh(item)
        item.result = {**item.result, "pause_requested": False}
        await session.commit()
        previous = list(item.result.get("queued_task_ids", []))
        queued = []
        skipped = []
        if not previous:
            hot_result = await sync_hot_questions(session, limit=30)
            await session.refresh(item)
            item.result = {**item.result, "hot_sync": hot_result}
        if item.result.get("pause_requested"):
            await session.commit()
            return DailyPlanRunResult(plan=item, message="计划已暂停，未继续入队")
        for task_id in previous:
            task = await session.get(TaskJob, task_id)
            if task and task.status in {"paused", "failed", "cancelled", "waiting_browser", "waiting_login", "waiting_verification"}:
                try:
                    await resume_task(session, broker, task)
                    queued.append(task.id)
                except ValueError:
                    skipped.append(task.question_id)
        questions = list((await session.scalars(
            select(Question).where(Question.status == "candidate").order_by(
                case((Question.priority == "high", 0), (Question.priority == "medium", 1), else_=2), Question.hot_rank.asc().nulls_last(), Question.created_at.asc()
            )
        )).all())
        used = set()
        if previous:
            used = set((await session.scalars(select(TaskJob.question_id).where(TaskJob.id.in_(previous)))).all())
        questions = [q for q in questions if q.id not in used and (q.source != 'hot' or q.hot_rank is not None)]
        remaining = max(0, item.question_limit - len(previous))
        hot = [q for q in questions if q.source == "hot"][:item.hot_quota]
        manual = [q for q in questions if q.source != "hot"][:item.manual_quota]
        chosen = (hot + manual)[:remaining]
        selected_ids = {q.id for q in chosen}
        chosen += [q for q in questions if q.id not in selected_ids][:max(0, remaining - len(chosen))]
        runtime = settings.model_copy(update={"max_answers_per_question": item.max_answers, "max_ai_concurrency": min(2, item.max_concurrency)})
        for question in chosen:
            await session.refresh(item)
            if item.result.get("pause_requested"):
                break
            try:
                task = await create_task(session, broker, question, runtime)
                previous.append(task.id)
                queued.append(task.id)
                # Persist each allocation before continuing, even if a later question fails.
                item.result = {**item.result, "queued_task_ids": previous}
                await session.commit()
            except (ValueError, RuntimeError):
                skipped.append(question.id)
        item.status = "paused" if item.result.get("pause_requested") else ("running" if previous else "insufficient_candidates")
        item.auto_production = False
        item.auto_publish = False
        if queued:
            item.last_executed_at = datetime.now(timezone.utc)
        item.result = {**item.result, "trigger": "manual", "queued_task_ids": previous,
                       "skipped_question_ids": skipped, "shortfall": max(0, item.question_limit - len(previous))}
        await refresh_plan_summary(session, item)
        await session.commit()
        return DailyPlanRunResult(plan=item, queued_task_ids=queued, skipped_question_ids=skipped,
                                  message=f"本次入队或继续 {len(queued)} 题；今日已安排 {len(previous)}/{item.question_limit} 题")


async def refresh_plan_summary(session, item):
    from backend.app.models.core import TaskJob
    tasks = list((await session.scalars(select(TaskJob).where(TaskJob.id.in_(item.result.get("queued_task_ids", []))))).all())
    completed = sum(t.status in {"waiting_review", "review_approved"} and bool(t.result.get("images_complete")) for t in tasks)
    item.result = {**item.result, "completed": completed,
        "article_completed": sum(bool(t.result.get("checkpoints", {}).get("article") or t.result.get("draft_id")) for t in tasks),
        "failed": sum(t.status in {"failed", "image_result_unknown"} for t in tasks),
        "waiting": sum(t.status in {"paused", "waiting_browser", "waiting_login", "waiting_verification"} for t in tasks),
        "items": [{"task_id": t.id, "question_id": t.question_id, "status": t.status, "stage": t.stage,
                   "progress": t.progress, "error": t.error_message} for t in tasks]}
    if completed >= item.question_limit:
        item.status = "completed"


async def run_due_daily_plan(session, broker, settings):
    # Manual RunDock ownership: neither startup nor a timer starts model work.
    return None
