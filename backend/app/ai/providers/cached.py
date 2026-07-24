from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.providers.base import (
    ProviderConfigurationError,
    ProviderUsage,
    StructuredOutputProvider,
    StructuredProviderResult,
)
from backend.app.models.core import ModelResponseCache, ModelUsageLog


T = TypeVar("T", bound=BaseModel)


class CachedStructuredProvider(StructuredOutputProvider):
    """为结构化文本调用提供数据库缓存和预算闸门。"""

    def __init__(
        self,
        inner: StructuredOutputProvider,
        session: AsyncSession,
        *,
        fingerprint: str,
        cache_enabled: bool,
        daily_budget: float,
        pause_on_budget_exceeded: bool,
    ):
        self.inner = inner
        self.session = session
        self.fingerprint = fingerprint
        self.cache_enabled = cache_enabled
        self.daily_budget = max(0.0, daily_budget)
        self.pause_on_budget_exceeded = pause_on_budget_exceeded

    async def _ensure_budget(self) -> None:
        if not self.pause_on_budget_exceeded or self.daily_budget <= 0:
            return
        today = datetime.now(timezone.utc).date()
        day_start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
        used = await self.session.scalar(
            select(func.coalesce(func.sum(ModelUsageLog.estimated_cost), 0)).where(
                ModelUsageLog.created_at >= day_start
            )
        )
        if Decimal(str(used or 0)) >= Decimal(str(self.daily_budget)):
            raise ProviderConfigurationError(
                f"今日文本模型预算已达到 ¥{self.daily_budget:.4f}，"
                "新的模型请求已暂停；缓存结果仍可使用"
            )

    def _cache_key(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[T],
        model_role: str,
    ) -> str:
        raw = json.dumps(
            {
                "fingerprint": self.fingerprint,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "schema": output_schema.model_json_schema(),
                "model_role": model_role,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[T],
        model_role: str,
    ) -> StructuredProviderResult[T]:
        cache_key = self._cache_key(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_schema=output_schema,
            model_role=model_role,
        )
        if self.cache_enabled:
            cached = await self.session.scalar(
                select(ModelResponseCache).where(
                    ModelResponseCache.cache_key == cache_key
                )
            )
            if cached:
                cached.hit_count += 1
                await self.session.flush()
                return StructuredProviderResult(
                    data=output_schema.model_validate(cached.response_json),
                    usage=ProviderUsage(
                        provider=cached.provider,
                        model=cached.model,
                        model_role=model_role,
                        cache_hit=True,
                    ),
                )

        await self._ensure_budget()
        result = await self.inner.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_schema=output_schema,
            model_role=model_role,
        )
        if self.cache_enabled:
            self.session.add(
                ModelResponseCache(
                    cache_key=cache_key,
                    schema_name=output_schema.__name__,
                    provider=result.usage.provider,
                    model=result.usage.model,
                    model_role=model_role,
                    response_json=result.data.model_dump(mode="json"),
                    hit_count=0,
                )
            )
            await self.session.flush()
        return result
