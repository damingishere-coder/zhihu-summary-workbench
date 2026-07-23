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
    created_at: datetime
    updated_at: datetime


class DraftListResponse(BaseModel):
    items: list[DraftRead]
    total: int


class DraftUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    content: str | None = Field(default=None, min_length=1, max_length=100_000)

