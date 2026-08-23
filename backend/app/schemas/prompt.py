from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ModelRole = Literal[
    "fast_text_model", "reasoning_model", "fallback_text_model"
]


class PromptVersionRead(BaseModel):
    id: str
    version: int
    content: str
    variables: list[str]
    model_role: str
    parameters: dict[str, Any]
    is_active: bool
    test_input: dict[str, Any]
    test_output: str
    change_note: str
    created_by: str
    created_at: datetime


class PromptTemplateRead(BaseModel):
    id: str
    key: str
    name: str
    description: str
    active_version: int
    version_count: int
    active: PromptVersionRead | None = None


class PromptCreate(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{2,127}$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    content: str = Field(min_length=10, max_length=40_000)
    variables: list[str] = Field(default_factory=list, max_length=30)
    model_role: ModelRole = "fast_text_model"
    parameters: dict[str, Any] = Field(default_factory=dict)
    change_note: str = Field(default="创建 Prompt", max_length=1000)


class PromptUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    content: str = Field(min_length=10, max_length=40_000)
    variables: list[str] = Field(default_factory=list, max_length=30)
    model_role: ModelRole = "fast_text_model"
    parameters: dict[str, Any] = Field(default_factory=dict)
    change_note: str = Field(min_length=1, max_length=1000)


class PromptActivateRequest(BaseModel):
    version: int = Field(ge=1)
    reason: str = Field(default="", max_length=1000)


class PromptTestRequest(BaseModel):
    version: int | None = Field(default=None, ge=1)
    input: dict[str, Any] = Field(default_factory=dict)
    provider_mode: Literal["mock", "codex", "deepseek"] | None = None


class PromptTestResponse(BaseModel):
    output: str
    provider: str
    model: str
    model_role: str
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    duration_ms: int


class PromptAuditRead(BaseModel):
    id: str
    action: str
    before_data: dict[str, Any]
    after_data: dict[str, Any]
    actor: str
    created_at: datetime
