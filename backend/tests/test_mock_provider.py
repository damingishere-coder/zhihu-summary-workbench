import pytest

from backend.app.ai.providers.mock import MockProvider
from backend.app.schemas.ai import AnswerClaimExtraction


@pytest.mark.asyncio
async def test_mock_provider_returns_valid_structured_output() -> None:
    result = await MockProvider().generate_structured(
        system_prompt="提取观点",
        user_prompt="问题：如何学习？\n示例回答：拆分目标。每天练习。及时反馈。",
        output_schema=AnswerClaimExtraction,
        model_role="fast_text_model",
    )

    assert result.data.core_claims == ["拆分目标", "每天练习", "及时反馈"]
    assert result.data.quality_score >= 55
    assert result.usage.provider == "mock"
    assert result.usage.input_tokens > 0

