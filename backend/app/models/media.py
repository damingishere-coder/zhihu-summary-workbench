from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models.common import TimestampMixin, UuidPrimaryKeyMixin, utc_now


class ImageTemplate(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "image_templates"

    name: Mapped[str] = mapped_column(String(200), unique=True)
    template_type: Mapped[str] = mapped_column(String(64))
    schema_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class ImageDraft(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "image_drafts"

    article_draft_id: Mapped[str] = mapped_column(
        ForeignKey("article_drafts.id", ondelete="CASCADE"), index=True
    )
    template_id: Mapped[str | None] = mapped_column(
        ForeignKey("image_templates.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(64), default="draft")
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    use_css_background: Mapped[bool] = mapped_column(Boolean, default=True)


class ImageVersion(Base, UuidPrimaryKeyMixin):
    __tablename__ = "image_versions"
    __table_args__ = (UniqueConstraint("image_draft_id", "version"),)

    image_draft_id: Mapped[str] = mapped_column(
        ForeignKey("image_drafts.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    prompt_zh: Mapped[str] = mapped_column(Text, default="")
    prompt_en: Mapped[str] = mapped_column(Text, default="")
    background_path: Mapped[str | None] = mapped_column(String(1000))
    rendered_path: Mapped[str | None] = mapped_column(String(1000))
    thumbnail_path: Mapped[str | None] = mapped_column(String(1000))
    html_snapshot_path: Mapped[str | None] = mapped_column(String(1000))
    render_status: Mapped[str] = mapped_column(
        String(32), default="not_rendered"
    )
    canvas_width: Mapped[int] = mapped_column(Integer, default=1080)
    canvas_height: Mapped[int] = mapped_column(Integer, default=1440)
    overflow_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    render_log_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    workflow_mode: Mapped[str] = mapped_column(
        String(64), default="copy_prompt_and_upload"
    )
    copy_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    uploaded_name: Mapped[str | None] = mapped_column(String(500))
    content_type: Mapped[str | None] = mapped_column(String(128))
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    background_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class PublishSchedule(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "publish_schedules"

    article_draft_id: Mapped[str] = mapped_column(
        ForeignKey("article_drafts.id", ondelete="RESTRICT"), index=True
    )
    article_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("article_versions.id", ondelete="RESTRICT"), index=True
    )
    image_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("image_versions.id", ondelete="RESTRICT"), index=True
    )
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    mode: Mapped[str] = mapped_column(String(32), default="manual")
    status: Mapped[str] = mapped_column(String(32), default="scheduled")
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=30)
    conflict_state: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[str | None] = mapped_column(String(128))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PublishRecord(Base, UuidPrimaryKeyMixin):
    __tablename__ = "publish_records"

    schedule_id: Mapped[str | None] = mapped_column(
        ForeignKey("publish_schedules.id", ondelete="SET NULL")
    )
    article_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("article_versions.id", ondelete="SET NULL")
    )
    image_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("image_versions.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(32))
    final_url: Mapped[str | None] = mapped_column(String(1000))
    error_message: Mapped[str | None] = mapped_column(Text)
    screenshot_path: Mapped[str | None] = mapped_column(String(1000))
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class BrowserSession(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "browser_sessions"

    adapter: Mapped[str] = mapped_column(String(64), default="zhihu")
    status: Mapped[str] = mapped_column(String(32), default="unknown")
    profile_reference: Mapped[str] = mapped_column(String(500), default="")
    last_error: Mapped[str | None] = mapped_column(Text)
