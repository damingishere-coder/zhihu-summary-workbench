from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


TemplateType = Literal["knowledge_card", "comparison_table"]
CanvasSize = Literal["1080x1440", "1242x1660"]


class InfographicPoint(BaseModel):
    title: str = Field(min_length=1, max_length=28)
    description: str = Field(min_length=1, max_length=110)


class InfographicContentData(BaseModel):
    title: str = Field(min_length=1, max_length=48)
    one_line_conclusion: str = Field(min_length=1, max_length=96)
    consensus: list[InfographicPoint] = Field(default_factory=list, max_length=4)
    disagreements: list[str] = Field(default_factory=list, max_length=4)
    conditions: list[str] = Field(default_factory=list, max_length=4)
    suggestions: list[str] = Field(default_factory=list, max_length=4)
    visual_keywords: list[str] = Field(default_factory=list, max_length=8)
    source_cluster_ids: list[str] = Field(default_factory=list, max_length=16)
    source_answer_ids: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_text_budget(self) -> "InfographicContentData":
        text_total = len(self.title) + len(self.one_line_conclusion)
        text_total += sum(
            len(item.title) + len(item.description) for item in self.consensus
        )
        text_total += sum(
            len(item)
            for values in (
                self.disagreements,
                self.conditions,
                self.suggestions,
            )
            for item in values
        )
        if text_total > 920:
            raise ValueError("信息图正文总长度超过 920 字，请精简后再渲染")
        return self


class GenerateInfographicContentRequest(BaseModel):
    template_type: TemplateType = "knowledge_card"
    canvas_size: CanvasSize = "1080x1440"


class GenerateImagePromptRequest(BaseModel):
    visual_style: str = Field(default="克制的知识编辑插画", max_length=200)
    aspect_ratio: str = Field(default="3:4", max_length=20)


class ImageEditorUpdate(BaseModel):
    content: InfographicContentData
    template_type: TemplateType = "knowledge_card"
    canvas_size: CanvasSize = "1080x1440"
    font_scale: float = Field(default=1, ge=0.8, le=1.25)
    brand_name: str = Field(default="知乎问题总结工作台", max_length=32)
    footer_text: str = Field(
        default="内容由 AI 辅助整理，请结合来源人工核验", max_length=64
    )
    background_position_x: int = Field(default=50, ge=0, le=100)
    background_position_y: int = Field(default=50, ge=0, le=100)
    background_scale: float = Field(default=1, ge=1, le=2)


class ImageVersionRead(BaseModel):
    id: str
    version: int
    content_json: dict[str, Any]
    prompt_zh: str
    prompt_en: str
    background_url: str | None
    thumbnail_url: str | None
    rendered_url: str | None
    download_url: str | None
    html_snapshot_available: bool
    render_status: str
    canvas_width: int
    canvas_height: int
    overflow: list[dict[str, Any]]
    render_log: list[dict[str, Any]]
    uploaded_name: str | None
    content_type: str | None
    byte_size: int
    background_deleted: bool
    copy_state: dict[str, Any]
    created_at: datetime


class ImageTemplateRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str
    name: str
    template_type: TemplateType
    template_schema: dict[str, Any] = Field(alias="schema_json")
    enabled: bool


class ImageWorkspaceRead(BaseModel):
    id: str
    article_draft_id: str
    status: str
    current_version: int
    use_css_background: bool
    current: ImageVersionRead | None
    versions: list[ImageVersionRead]
    templates: list[ImageTemplateRead] = Field(default_factory=list)


class ImageCopyRequest(BaseModel):
    language: str = Field(pattern="^(zh|en)$")


class CssModeRequest(BaseModel):
    enabled: bool


class ImageRestoreRequest(BaseModel):
    version: int = Field(ge=1)


class RenderImageRequest(BaseModel):
    version: int | None = Field(default=None, ge=1)


class BatchRenderRequest(BaseModel):
    image_ids: list[str] = Field(min_length=1, max_length=20)


class BatchRenderResult(BaseModel):
    rendered: list[str] = Field(default_factory=list)
    failed: dict[str, str] = Field(default_factory=dict)
