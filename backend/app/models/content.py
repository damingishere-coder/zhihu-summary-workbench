from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models.common import (
    TimestampMixin,
    UuidPrimaryKeyMixin,
    utc_now,
)


class QuestionScore(Base, UuidPrimaryKeyMixin):
    __tablename__ = "question_scores"

    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    value_score: Mapped[float] = mapped_column(Float, default=0)
    risk_level: Mapped[str] = mapped_column(String(32), default="normal")
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class Answer(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "answers"

    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    answer_external_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False
    )
    author_name: Mapped[str] = mapped_column(String(200), default="")
    author_url: Mapped[str] = mapped_column(String(1000), default="")
    answer_url: Mapped[str] = mapped_column(String(1000), default="")
    html_content: Mapped[str] = mapped_column(Text, default="")
    markdown_content: Mapped[str] = mapped_column(Text, default="")
    plain_content: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    vote_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    media_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    fetch_batch: Mapped[str] = mapped_column(String(64), default="", index=True)
    included_for_analysis: Mapped[bool] = mapped_column(Boolean, default=True)
    filter_reason: Mapped[str] = mapped_column(String(500), default="")
    raw_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AnswerVersion(Base, UuidPrimaryKeyMixin):
    __tablename__ = "answer_versions"
    __table_args__ = (UniqueConstraint("answer_id", "version"),)

    answer_id: Mapped[str] = mapped_column(
        ForeignKey("answers.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    plain_content: Mapped[str] = mapped_column(Text)
    raw_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class AnswerAnalysis(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "answer_analysis"

    answer_id: Mapped[str] = mapped_column(
        ForeignKey("answers.id", ondelete="CASCADE"), unique=True
    )
    summary: Mapped[str] = mapped_column(Text, default="")
    structured_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    quality_score: Mapped[float] = mapped_column(Float, default=0)
    relevance_score: Mapped[float] = mapped_column(Float, default=0)
    information_density: Mapped[float] = mapped_column(Float, default=0)
    include: Mapped[bool] = mapped_column(Boolean, default=True)
    reason: Mapped[str] = mapped_column(String(500), default="")


class Claim(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "claims"

    answer_id: Mapped[str] = mapped_column(
        ForeignKey("answers.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ClaimEmbedding(Base, UuidPrimaryKeyMixin):
    __tablename__ = "claim_embeddings"

    claim_id: Mapped[str] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), unique=True
    )
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    dimensions: Mapped[int] = mapped_column(Integer)
    vector: Mapped[bytes] = mapped_column(LargeBinary)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class ClaimCluster(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "claim_clusters"

    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(300), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    cluster_type: Mapped[str] = mapped_column(String(32), default="consensus")
    confidence: Mapped[float] = mapped_column(Float, default=0)
    support_count: Mapped[int] = mapped_column(Integer, default=0)
    opposing_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    applicable_conditions: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_mainstream: Mapped[bool] = mapped_column(Boolean, default=False)
    is_minority: Mapped[bool] = mapped_column(Boolean, default=False)
    is_controversial: Mapped[bool] = mapped_column(Boolean, default=False)
    information_gain: Mapped[float] = mapped_column(Float, default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ClusterAnswerLink(Base, UuidPrimaryKeyMixin):
    __tablename__ = "cluster_answer_links"
    __table_args__ = (UniqueConstraint("cluster_id", "answer_id"),)

    cluster_id: Mapped[str] = mapped_column(
        ForeignKey("claim_clusters.id", ondelete="CASCADE")
    )
    answer_id: Mapped[str] = mapped_column(
        ForeignKey("answers.id", ondelete="CASCADE")
    )
    relation: Mapped[str] = mapped_column(String(32), default="supports")


class ArticleParagraphSource(Base, UuidPrimaryKeyMixin):
    __tablename__ = "article_paragraph_sources"

    article_version_id: Mapped[str] = mapped_column(
        ForeignKey("article_versions.id", ondelete="CASCADE"), index=True
    )
    paragraph_id: Mapped[str] = mapped_column(String(64), index=True)
    answer_id: Mapped[str | None] = mapped_column(
        ForeignKey("answers.id", ondelete="SET NULL")
    )
    cluster_id: Mapped[str | None] = mapped_column(
        ForeignKey("claim_clusters.id", ondelete="SET NULL")
    )


class OpinionMap(Base, UuidPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "opinion_maps"
    __table_args__ = (UniqueConstraint("question_id", "version"),)

    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="generated")
    content_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
