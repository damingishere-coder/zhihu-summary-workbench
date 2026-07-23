from __future__ import annotations

import re
import time
from typing import TypeVar

from pydantic import BaseModel

from backend.app.ai.providers.base import (
    StructuredOutputProvider,
    StructuredProviderResult,
    TextGenerationProvider,
    ProviderUsage,
)
from backend.app.schemas.ai import AnswerClaimExtraction


T = TypeVar("T", bound=BaseModel)


class MockProvider(TextGenerationProvider, StructuredOutputProvider):
    name = "mock"
    model = "deterministic-claim-extractor-v1"

    async def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model_role: str,
    ) -> tuple[str, ProviderUsage]:
        started = time.perf_counter()
        text = f"Mock 模式已处理输入：{user_prompt[:120]}"
        usage = ProviderUsage(
            provider=self.name,
            model=self.model,
            model_role=model_role,
            input_tokens=max(1, len(user_prompt) // 2),
            output_tokens=max(1, len(text) // 2),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        return text, usage

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[T],
        model_role: str,
    ) -> StructuredProviderResult[T]:
        started = time.perf_counter()
        if output_schema is not AnswerClaimExtraction:
            raise TypeError(f"MockProvider 尚未注册结构：{output_schema.__name__}")

        answer_match = re.search(r"示例回答：\s*(.+)", user_prompt, re.DOTALL)
        answer = (answer_match.group(1) if answer_match else user_prompt).strip()
        sentences = [
            item.strip("。！？!?；; ")
            for item in re.split(r"[。！？!?；;\n]+", answer)
            if item.strip()
        ]
        claims = sentences[:4] or ["需要先补充可分析的回答内容"]
        summary = "；".join(claims[:2])
        data = AnswerClaimExtraction(
            summary=summary[:1000],
            core_claims=claims,
            supporting_reasons=claims[1:3],
            position="建议型",
            risks_or_limitations=["第一阶段结果用于验证流程，需要人工审核"],
            quality_score=min(92, 55 + len(answer) // 20),
            relevance_score=88,
        )
        usage = ProviderUsage(
            provider=self.name,
            model=self.model,
            model_role=model_role,
            input_tokens=max(1, len(user_prompt) // 2),
            output_tokens=max(1, len(data.model_dump_json()) // 2),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        return StructuredProviderResult(
            data=output_schema.model_validate(data.model_dump()),
            usage=usage,
        )

