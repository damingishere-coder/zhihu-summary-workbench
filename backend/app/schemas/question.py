from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ZHIHU_QUESTION_URL = re.compile(
    r"^https://(?:www\.)?zhihu\.com/question/(?P<id>\d+)(?:[/?#].*)?$",
    re.IGNORECASE,
)


class QuestionCreate(BaseModel):
    url: str = Field(max_length=1000)
    title: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=10_000)
    sample_answer: str = Field(default="", max_length=30_000)
    priority: Literal["high", "medium", "low"] = "medium"

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        normalized = value.strip()
        if not ZHIHU_QUESTION_URL.match(normalized):
            raise ValueError("请输入标准知乎问题链接，例如 https://www.zhihu.com/question/123456")
        return normalized


class QuestionImportRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=100)
    priority: Literal["high", "medium", "low"] = "medium"

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            normalized = value.strip()
            if not normalized:
                continue
            if not ZHIHU_QUESTION_URL.match(normalized):
                raise ValueError(f"不是标准知乎问题链接：{normalized}")
            cleaned.append(normalized)
        if not cleaned:
            raise ValueError("至少提供一个有效链接")
        return cleaned


class QuestionUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=10_000)
    sample_answer: str | None = Field(default=None, max_length=30_000)
    priority: Literal["high", "medium", "low"] | None = None
    status: Literal["candidate", "queued", "waiting_review", "ignored"] | None = None


class QuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    external_id: str | None
    title: str
    url: str
    description: str
    sample_answer: str
    source: str
    status: str
    priority: str
    created_at: datetime
    updated_at: datetime


class QuestionListResponse(BaseModel):
    items: list[QuestionRead]
    total: int


class QuestionImportItem(BaseModel):
    url: str
    status: Literal["created", "duplicate", "failed"]
    question_id: str | None = None
    message: str = ""


class QuestionImportResponse(BaseModel):
    items: list[QuestionImportItem]
    created: int
    duplicate: int
    failed: int


class QuestionDetail(QuestionRead):
    latest_task_id: str | None = None
    latest_draft_id: str | None = None

