from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


PROTOCOL_VERSION = 1
MAX_BRIDGE_PAYLOAD_BYTES = 6 * 1024 * 1024


class BrowserBridgeStatus(BaseModel):
    connection: Literal["connected", "disconnected", "unpaired"]
    zhihu_auth: Literal["authenticated", "login_required", "verification_required", "unknown"]
    extension_version: str = ""
    last_seen_at: datetime | None = None
    last_check_at: datetime | None = None
    active_job_id: str | None = None
    message: str


class PairingStartResponse(BaseModel):
    pairing_code: str
    expires_at: datetime
    websocket_url: str
    message: str


class UnpairResponse(BaseModel):
    revoked_clients: int
    message: str


class BridgeAuthor(BaseModel):
    name: str = Field(default="匿名用户", max_length=200)
    url_token: str = Field(default="", max_length=300)


class BridgeQuestionPayload(BaseModel):
    id: str = Field(pattern=r"^\d{1,32}$")
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(default="", max_length=1000)
    detail: str = Field(default="", max_length=200_000)
    excerpt: str = Field(default="", max_length=20_000)
    answer_count: int = Field(default=0, ge=0, le=100_000_000)
    follower_count: int = Field(default=0, ge=0, le=100_000_000)

    @field_validator("title")
    @classmethod
    def title_must_have_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("问题标题不能为空")
        return value


class BridgeAnswerPayload(BaseModel):
    id: str = Field(pattern=r"^\d{1,32}$")
    question_id: str = Field(pattern=r"^\d{1,32}$")
    author: BridgeAuthor = Field(default_factory=BridgeAuthor)
    url: str = Field(default="", max_length=1000)
    content: str = Field(default="", max_length=250_000)
    voteup_count: int = Field(default=0, ge=0, le=2_000_000_000)
    comment_count: int = Field(default=0, ge=0, le=2_000_000_000)
    created_time: int | None = Field(default=None, ge=0)
    updated_time: int | None = Field(default=None, ge=0)


class ImportBundleV1(BaseModel):
    format: Literal["ImportBundleV1"] = "ImportBundleV1"
    version: Literal[1] = 1
    collected_at: datetime
    mode: Literal["representative", "complete"] = "representative"
    question: BridgeQuestionPayload
    answers: list[BridgeAnswerPayload] = Field(min_length=1, max_length=500)
    warnings: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("answers")
    @classmethod
    def answers_belong_to_question(
        cls, answers: list[BridgeAnswerPayload], info
    ) -> list[BridgeAnswerPayload]:
        question = info.data.get("question")
        if question and any(item.question_id != question.id for item in answers):
            raise ValueError("回答 question_id 与导入问题不一致")
        ids = [item.id for item in answers]
        if len(ids) != len(set(ids)):
            raise ValueError("导入数据包含重复回答 id")
        return answers


class ImportAnswersResponse(BaseModel):
    question_id: str
    collection_job_id: str
    resumed_task_id: str | None = None
    fetched: int
    created: int
    updated: int
    included: int
    filtered: int
    message: str


class RetryCollectionResponse(BaseModel):
    task_id: str
    collection_job_id: str
    status: str
    dispatched: bool
    message: str
