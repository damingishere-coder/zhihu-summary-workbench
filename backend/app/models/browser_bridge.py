from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models.common import TimestampMixin, UuidPrimaryKeyMixin


class BrowserBridgeClient(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "browser_bridge_clients"
    __table_args__ = (Index("ix_browser_bridge_clients_status_seen", "status", "last_seen_at"),)

    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="paired", index=True)
    extension_version: Mapped[str] = mapped_column(String(64), default="")
    zhihu_auth: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CollectionJob(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "collection_jobs"
    __table_args__ = (
        Index("ix_collection_jobs_status_created", "status", "created_at"),
        Index("ix_collection_jobs_task_created", "task_id", "created_at"),
    )

    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_jobs.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    client_id: Mapped[str | None] = mapped_column(
        ForeignKey("browser_bridge_clients.id", ondelete="SET NULL"), index=True
    )
    nonce: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    mode: Mapped[str] = mapped_column(String(32), default="representative")
    max_answers: Mapped[int] = mapped_column(default=20)
    source: Mapped[str] = mapped_column(String(32), default="extension")
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
