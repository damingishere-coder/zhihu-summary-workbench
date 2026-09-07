from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AnswerQualityItem(BaseModel):
    answer_id: str
    relevance_score: int = Field(ge=0, le=100)
    quality_score: int = Field(ge=0, le=100)
    information_density: int = Field(ge=0, le=100)
    include: bool
    reason: str = Field(default="", max_length=500)


class AnswerQualityBatch(BaseModel):
    items: list[AnswerQualityItem] = Field(default_factory=list)


class AnswerClaimItem(BaseModel):
    answer_id: str
    source_start: int = Field(default=0, ge=0)
    source_end: int = Field(default=0, ge=0)
    summary: str = Field(min_length=1, max_length=1200)
    core_claims: list[str] = Field(default_factory=list, max_length=12)
    supporting_reasons: list[str] = Field(default_factory=list, max_length=12)
    examples: list[str] = Field(default_factory=list, max_length=10)
    data_or_evidence: list[str] = Field(default_factory=list, max_length=10)
    position: str = Field(default="中立", max_length=100)
    applicable_conditions: list[str] = Field(default_factory=list, max_length=12)
    risks_or_limitations: list[str] = Field(default_factory=list, max_length=12)
    unique_insights: list[str] = Field(default_factory=list, max_length=12)
    possible_factual_claims: list[str] = Field(default_factory=list, max_length=12)
    quality_score: int = Field(ge=0, le=100)
    relevance_score: int = Field(ge=0, le=100)


class AnswerClaimBatch(BaseModel):
    items: list[AnswerClaimItem] = Field(default_factory=list)


class ClusterSourceRelation(BaseModel):
    source_cluster_index: int = Field(ge=0)
    relation: Literal["supports", "opposes", "conditional", "related"]


class ClusterRefinementItem(BaseModel):
    source_cluster_indexes: list[int] = Field(min_length=1)
    source_relations: list[ClusterSourceRelation] = Field(default_factory=list)
    name: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=2000)
    cluster_type: Literal["consensus", "disagreement", "minority", "condition"]
    opposing_reasons: list[str] = Field(default_factory=list, max_length=12)
    applicable_conditions: list[str] = Field(default_factory=list, max_length=12)
    is_mainstream: bool = False
    is_minority: bool = False
    is_controversial: bool = False
    confidence: int = Field(ge=0, le=100)
    information_gain: int = Field(ge=0, le=100)


class ClusterRefinement(BaseModel):
    clusters: list[ClusterRefinementItem] = Field(default_factory=list)


class OpinionMapData(BaseModel):
    question_summary: str = Field(min_length=1, max_length=2000)
    one_sentence_answer: str = Field(min_length=1, max_length=500)
    main_dimensions: list[str] = Field(default_factory=list, max_length=12)
    main_consensus: list[str] = Field(default_factory=list, max_length=12)
    main_disagreements: list[str] = Field(default_factory=list, max_length=12)
    minority_but_valuable_views: list[str] = Field(
        default_factory=list, max_length=12
    )
    common_misunderstandings: list[str] = Field(default_factory=list, max_length=12)
    applicable_conditions: list[str] = Field(default_factory=list, max_length=12)
    risks: list[str] = Field(default_factory=list, max_length=12)
    practical_suggestions: list[str] = Field(default_factory=list, max_length=12)
    source_answer_ids: list[str] = Field(default_factory=list)


class ArticleParagraph(BaseModel):
    paragraph_id: str = Field(min_length=1, max_length=64)
    kind: Literal["content", "disclosure"] = "content"
    content: str = Field(min_length=1)
    cluster_ids: list[str] = Field(default_factory=list)
    source_answer_ids: list[str] = Field(default_factory=list)


class ArticleGeneration(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=100_000)
    paragraphs: list[ArticleParagraph] = Field(min_length=1)


class ArticleQualityReview(BaseModel):
    passed: bool
    score: int = Field(ge=0, le=100)
    checks: dict[str, bool] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list, max_length=30)
    risk_level: Literal["normal", "high"] = "normal"
    requires_human_review: bool = True
    summary: str = Field(default="", max_length=2000)


class AnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    question_id: str
    answer_external_id: str
    author_name: str
    author_url: str
    answer_url: str
    markdown_content: str
    plain_content: str
    vote_count: int
    comment_count: int
    published_at: datetime | None
    external_updated_at: datetime | None
    sort_order: int
    media_json: dict[str, Any]
    fetch_batch: str
    included_for_analysis: bool
    filter_reason: str
    created_at: datetime
    updated_at: datetime
    analysis: dict[str, Any] | None = None


class AnswerListResponse(BaseModel):
    items: list[AnswerRead]
    total: int
    included: int
    filtered: int


class FetchAnswersRequest(BaseModel):
    mode: Literal["representative", "complete"] = "representative"
    max_answers: int = Field(default=100, ge=1, le=500)
    collector_mode: Literal["auto", "api", "browser"] = "auto"


class FetchAnswersResponse(BaseModel):
    question_id: str
    fetched: int
    created: int
    updated: int
    included: int
    filtered: int
    collector_mode: str
    batch_id: str
    warnings: list[str] = Field(default_factory=list)


class HotQuestionFetchRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    collector_mode: Literal["auto", "api", "browser"] = "auto"


class HotQuestionFetchResponse(BaseModel):
    fetched: int
    created: int
    updated: int
    collector_mode: str
    warnings: list[str] = Field(default_factory=list)


class ClusterRead(BaseModel):
    id: str
    question_id: str
    name: str
    summary: str
    cluster_type: str
    confidence: float
    support_count: int
    opposing_reasons: list[str]
    applicable_conditions: list[str]
    is_mainstream: bool
    is_minority: bool
    is_controversial: bool
    information_gain: float
    sort_order: int = 0
    write_policy: Literal["auto", "force", "exclude"] = "auto"
    source_answer_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)


class ClusterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    summary: str | None = Field(default=None, min_length=1, max_length=2000)
    cluster_type: Literal[
        "consensus", "disagreement", "minority", "condition"
    ] | None = None
    is_mainstream: bool | None = None
    is_minority: bool | None = None
    is_controversial: bool | None = None
    applicable_conditions: list[str] | None = None
    opposing_reasons: list[str] | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10_000)
    write_policy: Literal["auto", "force", "exclude"] | None = None


class ClusterMergeRequest(BaseModel):
    cluster_ids: list[str] = Field(min_length=2, max_length=20)
    name: str | None = Field(default=None, max_length=300)


class ClusterSplitRequest(BaseModel):
    claim_ids: list[str] = Field(min_length=1)
    name: str = Field(min_length=1, max_length=300)


class AnalysisOverview(BaseModel):
    question_id: str
    answers_total: int
    answers_included: int
    clusters: list[ClusterRead]
    opinion_map: OpinionMapData | None
    opinion_map_version: int | None = None
    model_usage: dict[str, float | int]
    latest_draft_id: str | None = None


class StageRunResponse(BaseModel):
    stage: str
    message: str
    counts: dict[str, int] = Field(default_factory=dict)
    usage: dict[str, float | int] = Field(default_factory=dict)
