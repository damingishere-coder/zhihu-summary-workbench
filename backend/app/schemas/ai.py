from __future__ import annotations

from pydantic import BaseModel, Field


class AnswerClaimExtraction(BaseModel):
    summary: str = Field(min_length=1, max_length=1000)
    core_claims: list[str] = Field(min_length=1, max_length=12)
    supporting_reasons: list[str] = Field(default_factory=list, max_length=12)
    position: str = Field(default="中立", max_length=100)
    risks_or_limitations: list[str] = Field(default_factory=list, max_length=12)
    quality_score: int = Field(ge=0, le=100)
    relevance_score: int = Field(ge=0, le=100)


class ModelUsage(BaseModel):
    provider: str
    model: str
    model_role: str
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    estimated_cost: float = 0


class ClaimExtractionResult(BaseModel):
    analysis: AnswerClaimExtraction
    usage: ModelUsage


class ImageWorkflowCapability(BaseModel):
    provider: str = "manual"
    mode: str = "copy_prompt_and_upload"
    automatic_generation_available: bool = False
    manual_upload_available: bool = True

