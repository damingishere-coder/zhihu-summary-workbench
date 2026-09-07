from __future__ import annotations

from datetime import datetime
from typing import Literal, TypeAlias
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


PROTOCOL_VERSION = 1
MAX_BRIDGE_PAYLOAD_BYTES = 6 * 1024 * 1024


class BridgeCaptureDiagnostic(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    level: Literal["info", "warning", "error"] = "info"
    message: str = Field(min_length=1, max_length=500)


class BrowserCaptureSummary(BaseModel):
    job_id: str
    status: str
    source: str
    capture_version: int | None = None
    capture_method: str | None = None
    page_url: str | None = None
    visible_answer_count: int | None = None
    collected_answer_count: int | None = None
    diagnostics: list[BridgeCaptureDiagnostic] = Field(default_factory=list)


class BrowserBridgeStatus(BaseModel):
    connection: Literal["connected", "disconnected", "unpaired"]
    zhihu_auth: Literal["authenticated", "login_required", "verification_required", "unknown"]
    extension_version: str = ""
    last_seen_at: datetime | None = None
    last_check_at: datetime | None = None
    active_job_id: str | None = None
    latest_capture: BrowserCaptureSummary | None = None
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


class BridgeCaptureMetadata(BaseModel):
    method: Literal["rendered_dom", "same_origin_api"]
    page_url: str = Field(min_length=1, max_length=1000)
    visible_answer_count: int = Field(ge=0, le=100_000_000)
    collected_answer_count: int = Field(ge=0, le=100_000_000)
    stop_reason: str = Field(default="", max_length=64)
    reached_end: bool = False
    elapsed_seconds: float = Field(default=0, ge=0, le=1800)
    diagnostics: list[BridgeCaptureDiagnostic] = Field(default_factory=list, max_length=30)

    @field_validator("page_url")
    @classmethod
    def page_url_must_be_zhihu(cls, value: str) -> str:
        parsed = urlsplit(value.strip())
        if parsed.scheme != "https" or parsed.hostname not in {
            "zhihu.com",
            "www.zhihu.com",
        }:
            raise ValueError("采集页面必须是知乎 HTTPS 地址")
        return value.strip()


class _BridgeBundleBase(BaseModel):
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


class ImportBundleV1(_BridgeBundleBase):
    format: Literal["ImportBundleV1"] = "ImportBundleV1"
    version: Literal[1] = 1


class CollectionBundleV2(_BridgeBundleBase):
    format: Literal["CollectionBundleV2"] = "CollectionBundleV2"
    version: Literal[2] = 2
    capture: BridgeCaptureMetadata

    @field_validator("capture")
    @classmethod
    def capture_count_matches_answers(
        cls, capture: BridgeCaptureMetadata, info
    ) -> BridgeCaptureMetadata:
        answers = info.data.get("answers") or []
        if capture.collected_answer_count != len(answers):
            raise ValueError("采集统计与回答数量不一致")
        if capture.visible_answer_count < capture.collected_answer_count:
            raise ValueError("可见回答数量不能少于已采集数量")
        return capture


class CollectionBundleV3(CollectionBundleV2):
    format: Literal["CollectionBundleV3"] = "CollectionBundleV3"
    version: Literal[3] = 3
    answers: list[BridgeAnswerPayload] = Field(min_length=1)


BridgeCollectionBundle: TypeAlias = ImportBundleV1 | CollectionBundleV2 | CollectionBundleV3


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
