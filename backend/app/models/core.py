from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.models.common import (
    TimestampMixin,
    UuidPrimaryKeyMixin,
    utc_now,
)


class Question(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "questions"

    external_id: Mapped[str | None] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sample_answer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="manual", index=True)
    status: Mapped[str] = mapped_column(String(64), default="candidate", index=True)
    priority: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    hot_rank: Mapped[int | None] = mapped_column(Integer)
    hot_score: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    answer_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    follower_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sources: Mapped[list["QuestionSource"]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["TaskJob"]] = relationship(back_populates="question")
    drafts: Mapped[list["ArticleDraft"]] = relationship(back_populates="question")


class QuestionSource(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "question_sources"

    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    question: Mapped[Question] = relationship(back_populates="sources")


class DailyPlan(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "daily_plans"

    plan_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    question_limit: Mapped[int] = mapped_column(Integer, default=10)
    hot_quota: Mapped[int] = mapped_column(Integer, default=6)
    manual_quota: Mapped[int] = mapped_column(Integer, default=4)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    execute_time: Mapped[str] = mapped_column(String(5), default="09:00")
    max_concurrency: Mapped[int] = mapped_column(Integer, default=3)
    max_answers: Mapped[int] = mapped_column(Integer, default=100)
    daily_publish_limit: Mapped[int] = mapped_column(Integer, default=10)
    publish_interval_minutes: Mapped[int] = mapped_column(Integer, default=30)
    auto_production: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_publish: Mapped[bool] = mapped_column(Boolean, default=False)
    last_executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class TaskJob(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "task_jobs"
    __table_args__ = (
        Index("ix_task_jobs_status_created", "status", "created_at"),
    )

    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), index=True
    )
    task_type: Mapped[str] = mapped_column(
        String(64), default="question_claim_extraction"
    )
    status: Mapped[str] = mapped_column(String(64), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(64), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(128))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    question: Mapped[Question] = relationship(back_populates="tasks")
    logs: Mapped[list["TaskLog"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class TaskLog(Base, UuidPrimaryKeyMixin):
    __tablename__ = "task_logs"
    __table_args__ = (Index("ix_task_logs_task_created", "task_id", "created_at"),)

    task_id: Mapped[str] = mapped_column(
        ForeignKey("task_jobs.id", ondelete="CASCADE"), index=True
    )
    level: Mapped[str] = mapped_column(String(16), default="info")
    stage: Mapped[str] = mapped_column(String(64), default="queued")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    task: Mapped[TaskJob] = relationship(back_populates="logs")


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ModelUsageLog(Base, UuidPrimaryKeyMixin):
    __tablename__ = "model_usage_logs"
    __table_args__ = (
        Index("ix_model_usage_question_created", "question_id", "created_at"),
        Index("ix_model_usage_task_created", "task_id", "created_at"),
    )

    question_id: Mapped[str | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL")
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_jobs.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_role: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0")
    )
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="success")
    error_message: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(String(64), default="", index=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class ModelResponseCache(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "model_response_cache"

    cache_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    schema_name: Mapped[str] = mapped_column(String(200), index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    model_role: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    hit_count: Mapped[int] = mapped_column(Integer, default=0)


class ArticleDraft(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "article_drafts"

    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="waiting_review")
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    review_result: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    question: Mapped[Question] = relationship(back_populates="drafts")
    versions: Mapped[list["ArticleVersion"]] = relationship(
        back_populates="draft", cascade="all, delete-orphan"
    )


class ArticleVersion(Base, UuidPrimaryKeyMixin):
    __tablename__ = "article_versions"
    __table_args__ = (UniqueConstraint("draft_id", "version"),)

    draft_id: Mapped[str] = mapped_column(
        ForeignKey("article_drafts.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_jobs.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    draft: Mapped[ArticleDraft] = relationship(back_populates="versions")


class PromptTemplate(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "prompt_templates"

    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    active_version: Mapped[int] = mapped_column(Integer, default=1)

    versions: Mapped[list["PromptVersion"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )


class PromptVersion(Base, UuidPrimaryKeyMixin):
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("template_id", "version"),)

    template_id: Mapped[str] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    model_role: Mapped[str] = mapped_column(
        String(64), default="fast_text_model", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    test_input: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    test_output: Mapped[str] = mapped_column(Text, default="", nullable=False)
    change_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by: Mapped[str] = mapped_column(
        String(128), default="operator", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    template: Mapped[PromptTemplate] = relationship(back_populates="versions")


class AuditLog(Base, UuidPrimaryKeyMixin):
    __tablename__ = "audit_logs"

    actor: Mapped[str] = mapped_column(String(128), default="system")
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(36))
    before_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    after_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class OpenSourceReference(Base, UuidPrimaryKeyMixin):
    __tablename__ = "open_source_references"

    name: Mapped[str] = mapped_column(String(200), unique=True)
    version: Mapped[str] = mapped_column(String(64), default="not-pinned")
    license_name: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    usage_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
