from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.app.schemas.ai import AnswerClaimExtraction, ModelUsage


class PublicSettings(BaseModel):
    provider_mode: Literal["mock", "codex", "deepseek"]
    codex_configured: bool
    codex_model: str
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
    hot_question_quota: int
    manual_question_quota: int
    max_answers_per_question: int
    max_ai_concurrency: int
    request_timeout_seconds: int
    daily_plan_time: str
    daily_publish_limit: int
    publish_interval_minutes: int
    auto_production_enabled: bool
    auto_publish_enabled: bool
    daily_model_budget: float
    pause_on_budget_exceeded: bool
    response_cache_enabled: bool
    browser_user_data_dir: str
    redis_url_display: str


class SettingsUpdate(BaseModel):
    provider_mode: Literal["mock", "codex", "deepseek"] | None = None
    codex_model: str | None = Field(default=None, min_length=1, max_length=128)
    fast_text_model: str | None = Field(default=None, min_length=1, max_length=128)
    reasoning_model: str | None = Field(default=None, min_length=1, max_length=128)
    fallback_text_model: str | None = Field(default=None, min_length=1, max_length=128)
    embedding_model: str | None = Field(default=None, min_length=1, max_length=256)
    daily_question_limit: int | None = Field(default=None, ge=1, le=100)
    hot_question_quota: int | None = Field(default=None, ge=0, le=100)
    manual_question_quota: int | None = Field(default=None, ge=0, le=100)
    max_answers_per_question: int | None = Field(default=None, ge=1, le=500)
    max_ai_concurrency: int | None = Field(default=None, ge=1, le=20)
    request_timeout_seconds: int | None = Field(default=None, ge=5, le=1800)
    daily_plan_time: str | None = Field(
        default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$"
    )
    daily_publish_limit: int | None = Field(default=None, ge=1, le=100)
    publish_interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    auto_production_enabled: bool | None = None
    auto_publish_enabled: bool | None = None
    daily_model_budget: float | None = Field(default=None, ge=0, le=1_000_000)
    pause_on_budget_exceeded: bool | None = None
    response_cache_enabled: bool | None = None
    browser_user_data_dir: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_quotas(self) -> "SettingsUpdate":
        if (
            self.daily_question_limit is not None
            and self.hot_question_quota is not None
            and self.manual_question_quota is not None
            and self.hot_question_quota + self.manual_question_quota
            > self.daily_question_limit
        ):
            raise ValueError("热门配额与手动配额之和不能超过每日问题数")
        return self


class ModelTestRequest(BaseModel):
    provider_mode: Literal["mock", "codex", "deepseek"] | None = None
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
    provider_mode: Literal["mock", "codex", "deepseek"]
    deepseek_configured: bool
    codex_configured: bool = False

    @model_validator(mode="after")
    def validate_provider(self) -> "SettingsValidation":
        if self.provider_mode == "deepseek" and not self.deepseek_configured:
            raise ValueError("DeepSeek 模式需要在本机 .env 中配置 DEEPSEEK_API_KEY")
        if self.provider_mode == "codex" and not self.codex_configured:
            raise ValueError("Codex 模式需要安装 Codex CLI 并登录当前 ChatGPT 账号")
        return self
