from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings
from backend.app.models.core import ModelUsageLog, Question
from backend.app.models.media import ImageVersion
from backend.app.schemas.publish import ModelUsageOverview, UsageBreakdown
from backend.app.services.settings import get_setting


async def model_usage_overview(
    session: AsyncSession, settings: Settings, target: date
) -> ModelUsageOverview:
    local_timezone = datetime.now().astimezone().tzinfo or timezone.utc
    start_local = datetime.combine(target, time.min).replace(
        tzinfo=local_timezone
    )
    start = start_local.astimezone(timezone.utc)
    end = (start_local + timedelta(days=1)).astimezone(timezone.utc)
    rows = list(
        (
            await session.scalars(
                select(ModelUsageLog).where(
                    ModelUsageLog.created_at >= start,
                    ModelUsageLog.created_at < end,
                )
            )
        ).all()
    )
    budget = Decimal(
        str(
            await get_setting(
                session, "daily_model_budget", settings.daily_model_budget
            )
        )
    )
    total_cost = sum(
        (Decimal(str(item.estimated_cost or 0)) for item in rows), Decimal("0")
    )

    def breakdown(key_name: str) -> list[UsageBreakdown]:
        grouped: dict[str, list[ModelUsageLog]] = {}
        for row in rows:
            key = str(getattr(row, key_name) or "未标记")
            grouped.setdefault(key, []).append(row)
        return [
            UsageBreakdown(
                key=key,
                calls=len(items),
                input_tokens=sum(item.input_tokens for item in items),
                output_tokens=sum(item.output_tokens for item in items),
                estimated_cost=sum(
                    (
                        Decimal(str(item.estimated_cost or 0))
                        for item in items
                    ),
                    Decimal("0"),
                ),
            )
            for key, items in sorted(grouped.items())
        ]

    question_titles = {
        item.id: item.title
        for item in (
            await session.scalars(
                select(Question).where(
                    Question.id.in_(
                        [row.question_id for row in rows if row.question_id]
                    )
                )
            )
        ).all()
    }
    by_question_raw = breakdown("question_id")
    by_question = [
        item.model_copy(
            update={"key": question_titles.get(item.key, item.key)}
        )
        for item in by_question_raw
    ]
    manual_image_generations = int(
        (
            await session.scalar(
                select(func.count(ImageVersion.id)).where(
                    ImageVersion.created_at >= start,
                    ImageVersion.created_at < end,
                    ImageVersion.workflow_mode == "copy_prompt_and_upload",
                    ImageVersion.prompt_zh != "",
                )
            )
        )
        or 0
    )
    return ModelUsageOverview(
        cost_known=not any(item.provider in {"codex", "codex_cli"} for item in rows),
        usage_known=not any(item.provider in {"codex", "codex_cli"} for item in rows),
        date=target,
        calls=len(rows),
        input_tokens=sum(item.input_tokens for item in rows),
        output_tokens=sum(item.output_tokens for item in rows),
        estimated_cost=total_cost,
        daily_budget=budget,
        budget_remaining=max(budget - total_cost, Decimal("0"))
        if budget > 0
        else None,
        budget_exceeded=budget > 0 and total_cost >= budget,
        cache_hits=sum(bool(item.cache_hit) for item in rows),
        fallback_calls=sum(bool(item.fallback_used) for item in rows),
        retries=sum(item.retry_count for item in rows),
        manual_image_generations=manual_image_generations,
        by_stage=breakdown("stage"),
        by_question=by_question,
    )
