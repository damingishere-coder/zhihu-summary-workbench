from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
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
    target = {
        "question_limit": int(values.get("question_limit", item.question_limit)),
        "hot_quota": int(values.get("hot_quota", item.hot_quota)),
        "manual_quota": int(values.get("manual_quota", item.manual_quota)),
    }
    if target["hot_quota"] + target["manual_quota"] > target["question_limit"]:
        raise ValueError("热门配额与手动配额之和不能超过每日问题数")
    for key, value in values.items():
        setattr(item, key, value)
    # 自动发布具有更高风险，服务端始终要求先开启自动生产。
    if item.auto_publish and not item.auto_production:
        raise ValueError("开启自动发布前必须先开启自动生产")
    await session.commit()
    await session.refresh(item)
    return item


async def execute_daily_plan(
    session: AsyncSession,
    broker: QueueBroker,
    item: DailyPlan,
    settings: Settings,
    *,
    trigger: str,
) -> DailyPlanRunResult:
    now = datetime.now(timezone.utc)
    local_today = datetime.now().astimezone().date()
    last_executed = item.last_executed_at
    if last_executed and last_executed.tzinfo is None:
        last_executed = last_executed.replace(tzinfo=timezone.utc)
    if last_executed and last_executed.astimezone().date() == local_today:
        return DailyPlanRunResult(
            plan=item,
            queued_task_ids=list(item.result.get("queued_task_ids", [])),
            skipped_question_ids=[],
            message="今日计划已经执行过，本次没有重复入队",
        )
    if not item.auto_production and trigger == "timer":
        item.status = "disabled"
        item.result = {"trigger": trigger, "reason": "auto_production_disabled"}
        await session.commit()
        return DailyPlanRunResult(
            plan=item,
            message="自动生产未开启，定时器已安全跳过",
        )
    questions = list(
        (
            await session.scalars(
                select(Question)
                .where(Question.status == "candidate")
                .order_by(
                    Question.priority.asc(),
                    Question.hot_rank.asc().nulls_last(),
                    Question.created_at.asc(),
                )
                .limit(item.question_limit * 3)
            )
        ).all()
    )
    hot = [question for question in questions if question.source == "hot"][
        : item.hot_quota
    ]
    manual = [question for question in questions if question.source != "hot"][
        : item.manual_quota
    ]
    selected = (hot + manual)[: item.question_limit]
    queued: list[str] = []
    skipped: list[str] = []
    runtime = settings.model_copy(
        update={
            "max_answers_per_question": item.max_answers,
            "max_ai_concurrency": item.max_concurrency,
        }
    )
    for question in selected:
        try:
            task = await create_task(session, broker, question, runtime)
            queued.append(task.id)
        except (ValueError, RuntimeError):
            skipped.append(question.id)
    item.status = "executed"
    item.last_executed_at = now
    item.result = {
        "trigger": trigger,
        "queued_task_ids": queued,
        "skipped_question_ids": skipped,
        "selected_question_ids": [question.id for question in selected],
        "auto_publish": item.auto_publish,
    }
    await session.commit()
    await session.refresh(item)
    return DailyPlanRunResult(
        plan=item,
        queued_task_ids=queued,
        skipped_question_ids=skipped,
        message=f"今日计划已执行，{len(queued)} 个问题进入队列",
    )


async def run_due_daily_plan(
    session: AsyncSession,
    broker: QueueBroker,
    settings: Settings,
) -> DailyPlanRunResult | None:
    item = await get_or_create_daily_plan(session, settings)
    now = datetime.now().astimezone()
    current_hm = now.strftime("%H:%M")
    if current_hm < item.execute_time:
        return None
    last_executed = item.last_executed_at
    if last_executed and last_executed.tzinfo is None:
        last_executed = last_executed.replace(tzinfo=timezone.utc)
    if last_executed and last_executed.astimezone().date() == now.date():
        return None
    return await execute_daily_plan(
        session, broker, item, settings, trigger="timer"
    )
