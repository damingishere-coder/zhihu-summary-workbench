from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.app.schemas.ai import AnswerClaimExtraction, ModelUsage


class PublicSettings(BaseModel):
    provider_mode: Literal["mock", "deepseek"]
    deepseek_configured: bool
    deepseek_base_url: str
    fast_text_model: str
    reasoning_model: str
    fallback_text_model: str
    embedding_provider: str
    embedding_model: str
    image_generation_mode: str
    allow_manual_image_upload: bool
    daily_question_limit: int
    max_ai_concurrency: int
    request_timeout_seconds: int
    browser_user_data_dir: str
    redis_url_display: str


class SettingsUpdate(BaseModel):
    provider_mode: Literal["mock", "deepseek"] | None = None
    fast_text_model: str | None = Field(default=None, min_length=1, max_length=128)
    reasoning_model: str | None = Field(default=None, min_length=1, max_length=128)
    fallback_text_model: str | None = Field(default=None, min_length=1, max_length=128)
    embedding_model: str | None = Field(default=None, min_length=1, max_length=256)
    daily_question_limit: int | None = Field(default=None, ge=1, le=100)
    max_ai_concurrency: int | None = Field(default=None, ge=1, le=20)
    request_timeout_seconds: int | None = Field(default=None, ge=5, le=600)
    browser_user_data_dir: str | None = Field(default=None, max_length=1000)


class ModelTestRequest(BaseModel):
    provider_mode: Literal["mock", "deepseek"] | None = None
    question_title: str = Field(default="如何更高效地学习一项新技能？", min_length=1, max_length=500)
    sample_answer: str = Field(
        default="先明确目标，再把技能拆成可以每天练习的小步骤。持续获得反馈，比一次学习很久更重要。",
        min_length=1,
        max_length=30_000,
    )


class ModelTestResponse(BaseModel):
    success: bool
    provider: str
    model: str
    message: str
    analysis: AnswerClaimExtraction | None = None
    usage: ModelUsage | None = None


class SettingsValidation(BaseModel):
    provider_mode: Literal["mock", "deepseek"]
    deepseek_configured: bool

    @model_validator(mode="after")
    def validate_provider(self) -> "SettingsValidation":
        if self.provider_mode == "deepseek" and not self.deepseek_configured:
            raise ValueError("DeepSeek 模式需要在本机 .env 中配置 DEEPSEEK_API_KEY")
        return self

