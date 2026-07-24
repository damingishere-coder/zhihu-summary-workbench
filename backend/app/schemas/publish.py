from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


PublishMode = Literal["manual", "assisted"]


class PublishReadiness(BaseModel):
    draft_id: str
    ready: bool
    article_approved: bool
    article_version_id: str | None = None
    article_version: int | None = None
    image_rendered: bool
    image_version_id: str | None = None
    image_version: int | None = None
    risk_level: str
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PublishScheduleCreate(BaseModel):
    article_draft_id: str
    scheduled_for: datetime
    mode: PublishMode = "manual"


class PublishScheduleUpdate(BaseModel):
    scheduled_for: datetime | None = None
    mode: PublishMode | None = None
    sort_order: int | None = Field(default=None, ge=0)


class PublishScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    article_draft_id: str
    article_title: str = ""
    article_version_id: str | None
    article_version: int | None = None
    image_version_id: str | None
    image_version: int | None = None
    scheduled_for: datetime
    mode: str
    status: str
    requires_confirmation: bool
    sort_order: int
    interval_minutes: int
    conflict_state: dict[str, Any]
    confirmed_at: datetime | None
    confirmed_by: str | None
    executed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PublishExecuteRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=32)


class PublishRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    schedule_id: str | None
    article_version_id: str | None
    image_version_id: str | None
    status: str
    final_url: str | None
    error_message: str | None
    screenshot_url: str | None = None
    attempt_count: int
    details: dict[str, Any]
    created_at: datetime


class BrowserSafetyState(BaseModel):
    adapter: str = "zhihu"
    state: Literal[
        "ready",
        "profile_missing",
        "login_required",
        "captcha_required",
        "risk_controlled",
        "browser_unavailable",
    ]
    safe_to_continue: bool
    message: str
    profile_configured: bool
    screenshot_url: str | None = None


class DailyPlanUpdate(BaseModel):
    execute_time: str | None = Field(
        default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$"
    )
    question_limit: int | None = Field(default=None, ge=1, le=100)
    hot_quota: int | None = Field(default=None, ge=0, le=100)
    manual_quota: int | None = Field(default=None, ge=0, le=100)
    max_concurrency: int | None = Field(default=None, ge=1, le=20)
    max_answers: int | None = Field(default=None, ge=1, le=500)
    daily_publish_limit: int | None = Field(default=None, ge=1, le=100)
    publish_interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    auto_production: bool | None = None
    auto_publish: bool | None = None


class DailyPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    plan_date: date
    question_limit: int
    hot_quota: int
    manual_quota: int
    status: str
    execute_time: str
    max_concurrency: int
    max_answers: int
    daily_publish_limit: int
    publish_interval_minutes: int
    auto_production: bool
    auto_publish: bool
    last_executed_at: datetime | None
    result: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class DailyPlanRunResult(BaseModel):
    plan: DailyPlanRead
    queued_task_ids: list[str] = Field(default_factory=list)
    skipped_question_ids: list[str] = Field(default_factory=list)
    message: str


class UsageBreakdown(BaseModel):
    key: str
    calls: int
    input_tokens: int
    output_tokens: int
    estimated_cost: Decimal


class ModelUsageOverview(BaseModel):
    date: date
    calls: int
    input_tokens: int
    output_tokens: int
    estimated_cost: Decimal
    daily_budget: Decimal
    budget_remaining: Decimal | None
    budget_exceeded: bool
    cache_hits: int
    fallback_calls: int
    retries: int
    manual_image_generations: int
    by_stage: list[UsageBreakdown]
    by_question: list[UsageBreakdown]


class OpenSourceReferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    version: str
    license_name: str
    source_url: str
    usage_note: str
    created_at: datetime
