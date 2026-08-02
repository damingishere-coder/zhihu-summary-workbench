from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DraftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    question_id: str
    question_title: str = ""
    status: str
    current_version: int
    title: str
    content: str
    analysis_snapshot: dict[str, Any]
    review_result: dict[str, Any]
    reviewed_at: datetime | None
    paragraph_sources: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class DraftListResponse(BaseModel):
    items: list[DraftRead]
    total: int


class DraftUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    content: str | None = Field(default=None, min_length=1, max_length=100_000)


class DraftReviewRequest(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    reason: str = Field(default="", max_length=2000)


class DraftVersionRead(BaseModel):
    id: str
    version: int
    title: str
    content: str
    source_task_id: str | None
    created_at: datetime


class DraftRewriteRequest(BaseModel):
    scope: str = Field(pattern="^(paragraph|selection)$")
    text: str = Field(min_length=1, max_length=20_000)
    instruction: str = Field(default="", max_length=1000)


class DraftRewriteResult(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


class DraftRewriteResponse(BaseModel):
    text: str
    usage: dict[str, float | int] = Field(default_factory=dict)
