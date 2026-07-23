from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class GenerateImagePromptRequest(BaseModel):
    visual_style: str = Field(default="克制的知识编辑插画", max_length=200)
    aspect_ratio: str = Field(default="3:4", max_length=20)


class ImageVersionRead(BaseModel):
    id: str
    version: int
    content_json: dict[str, Any]
    prompt_zh: str
    prompt_en: str
    background_url: str | None
    uploaded_name: str | None
    content_type: str | None
    byte_size: int
    background_deleted: bool
    copy_state: dict[str, Any]
    created_at: datetime


class ImageWorkspaceRead(BaseModel):
    id: str
    article_draft_id: str
    status: str
    current_version: int
    use_css_background: bool
    current: ImageVersionRead | None
    versions: list[ImageVersionRead]


class ImageCopyRequest(BaseModel):
    language: str = Field(pattern="^(zh|en)$")


class CssModeRequest(BaseModel):
    enabled: bool
