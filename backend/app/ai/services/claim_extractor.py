from __future__ import annotations

from backend.app.ai.providers.base import (
    StructuredOutputProvider,
    StructuredProviderResult,
)
from backend.app.ai.services.interfaces import AnswerClaimExtractor
from backend.app.schemas.ai import AnswerClaimExtraction


DEFAULT_SYSTEM_PROMPT = """你是知乎回答观点提取器。只基于提供的回答提取观点，不补充外部事实。
区分观点、理由和风险；不要把个人经历改写为普遍事实。输出必须通过给定结构校验。"""


class ClaimExtractionService(AnswerClaimExtractor):
    def __init__(self, provider: StructuredOutputProvider):
        self.provider = provider

    async def extract(
        self,
        *,
        question_title: str,
        answer_text: str,
    ) -> StructuredProviderResult[AnswerClaimExtraction]:
        user_prompt = f"问题：{question_title}\n\n示例回答：\n{answer_text}"
        return await self.provider.generate_structured(
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_schema=AnswerClaimExtraction,
            model_role="fast_text_model",
        )

