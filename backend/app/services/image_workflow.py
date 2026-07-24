from __future__ import annotations

import io
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.providers.manual_image import ManualImageWorkflowProvider
from backend.app.ai.services.content import (
    INFOGRAPHIC_SYSTEM_PROMPT,
    InfographicContentService,
)
from backend.app.core.config import REPOSITORY_ROOT, Settings
from backend.app.models.content import ClaimCluster, OpinionMap
from backend.app.models.core import ArticleDraft
from backend.app.models.media import ImageDraft, ImageTemplate, ImageVersion
from backend.app.schemas.analysis import OpinionMapData
from backend.app.schemas.image import (
    ImageEditorUpdate,
    ImageTemplateRead,
    ImageVersionRead,
    ImageWorkspaceRead,
    InfographicContentData,
)
from backend.app.services.content_pipeline import (
    _runtime_provider,
    cluster_rows,
    record_model_usage,
)
from backend.app.services.prompts import get_active_prompt


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
IMAGE_SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": ("png", "image/png"),
    b"\xff\xd8\xff": ("jpg", "image/jpeg"),
    b"RIFF": ("webp", "image/webp"),
}
CANVAS_SIZES = {
    "1080x1440": (1080, 1440),
    "1242x1660": (1242, 1660),
}


def _background_url(version: ImageVersion) -> str | None:
    if not version.background_path or version.background_deleted:
        return None
    return f"/api/images/versions/{version.id}/background"


def _thumbnail_url(version: ImageVersion) -> str | None:
    if not version.thumbnail_path or version.background_deleted:
        return None
    return f"/api/images/versions/{version.id}/thumbnail"


def _rendered_url(version: ImageVersion) -> str | None:
    if not version.rendered_path or version.render_status != "rendered":
        return None
    return f"/api/images/{version.image_draft_id}/download?version={version.version}"


def version_to_read(version: ImageVersion) -> ImageVersionRead:
    rendered_url = _rendered_url(version)
    return ImageVersionRead(
        id=version.id,
        version=version.version,
        content_json=version.content_json or {},
        prompt_zh=version.prompt_zh,
        prompt_en=version.prompt_en,
        background_url=_background_url(version),
        thumbnail_url=_thumbnail_url(version),
        rendered_url=rendered_url,
        download_url=rendered_url,
        html_snapshot_available=bool(version.html_snapshot_path),
        render_status=version.render_status,
        canvas_width=version.canvas_width,
        canvas_height=version.canvas_height,
        overflow=version.overflow_json or [],
        render_log=version.render_log_json or [],
        uploaded_name=version.uploaded_name,
        content_type=version.content_type,
        byte_size=version.byte_size,
        background_deleted=version.background_deleted,
        copy_state=version.copy_state or {},
        created_at=version.created_at,
    )


async def _versions(
    session: AsyncSession, image_draft_id: str
) -> list[ImageVersion]:
    return list(
        (
            await session.scalars(
                select(ImageVersion)
                .where(ImageVersion.image_draft_id == image_draft_id)
                .order_by(ImageVersion.version.desc())
            )
        ).all()
    )


async def _templates(session: AsyncSession) -> list[ImageTemplateRead]:
    items = (
        await session.scalars(
            select(ImageTemplate)
            .where(ImageTemplate.enabled.is_(True))
            .order_by(ImageTemplate.name)
        )
    ).all()
    return [
        ImageTemplateRead(
            id=item.id,
            name=item.name,
            template_type=item.template_type,
            schema_json=item.schema_json or {},
            enabled=item.enabled,
        )
        for item in items
    ]


async def _current_version(
    session: AsyncSession, image_draft: ImageDraft
) -> ImageVersion | None:
    if image_draft.current_version < 1:
        return None
    return await session.scalar(
        select(ImageVersion).where(
            ImageVersion.image_draft_id == image_draft.id,
            ImageVersion.version == image_draft.current_version,
        )
    )


async def workspace_to_read(
    session: AsyncSession, image_draft: ImageDraft
) -> ImageWorkspaceRead:
    versions = await _versions(session, image_draft.id)
    current = next(
        (item for item in versions if item.version == image_draft.current_version),
        versions[0] if versions else None,
    )
    return ImageWorkspaceRead(
        id=image_draft.id,
        article_draft_id=image_draft.article_draft_id,
        status=image_draft.status,
        current_version=image_draft.current_version,
        use_css_background=image_draft.use_css_background,
        current=version_to_read(current) if current else None,
        versions=[version_to_read(item) for item in versions],
        templates=await _templates(session),
    )


async def get_image_workspace(
    session: AsyncSession, draft_id: str, *, create: bool = False
) -> ImageDraft | None:
    item = await session.scalar(
        select(ImageDraft)
        .where(ImageDraft.article_draft_id == draft_id)
        .order_by(ImageDraft.created_at.desc())
        .limit(1)
    )
    if not item and create:
        template = await session.scalar(
            select(ImageTemplate)
            .where(ImageTemplate.template_type == "knowledge_card")
            .limit(1)
        )
        item = ImageDraft(
            article_draft_id=draft_id,
            template_id=template.id if template else None,
            status="draft",
            current_version=0,
            use_css_background=True,
        )
        session.add(item)
        await session.flush()
    return item


def _editor_defaults(
    infographic: dict[str, Any],
    *,
    template_type: str,
    canvas_size: str,
) -> dict[str, Any]:
    return {
        **infographic,
        "template_type": template_type,
        "canvas_size": canvas_size,
        "aspect_ratio": "3:4",
        "suggested_size": canvas_size.replace("x", "×"),
        "font_scale": 1,
        "brand_name": "知乎问题总结工作台",
        "footer_text": "内容由 AI 辅助整理，请结合来源人工核验",
        "background_position_x": 50,
        "background_position_y": 50,
        "background_scale": 1,
        "negative_constraints": [
            "不得生成中文或英文文字",
            "不得出现水印、Logo 或二维码",
            "避免密集细节和高干扰背景",
        ],
    }


async def _append_version(
    session: AsyncSession,
    image_draft: ImageDraft,
    *,
    content_json: dict[str, Any],
    prompt_zh: str = "",
    prompt_en: str = "",
    background_path: str | None = None,
    thumbnail_path: str | None = None,
    workflow_mode: str = "copy_prompt_and_upload",
    copy_state: dict[str, Any] | None = None,
    uploaded_name: str | None = None,
    content_type: str | None = None,
    byte_size: int = 0,
    background_deleted: bool = False,
) -> ImageVersion:
    image_draft.current_version += 1
    canvas_size = str(content_json.get("canvas_size") or "1080x1440")
    canvas_width, canvas_height = CANVAS_SIZES.get(
        canvas_size, CANVAS_SIZES["1080x1440"]
    )
    version = ImageVersion(
        image_draft_id=image_draft.id,
        version=image_draft.current_version,
        content_json=content_json,
        prompt_zh=prompt_zh,
        prompt_en=prompt_en,
        background_path=background_path,
        thumbnail_path=thumbnail_path,
        workflow_mode=workflow_mode,
        copy_state=copy_state or {},
        uploaded_name=uploaded_name,
        content_type=content_type,
        byte_size=byte_size,
        background_deleted=background_deleted,
        render_status="not_rendered",
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        overflow_json=[],
        render_log_json=[],
    )
    session.add(version)
    await session.flush()
    return version


async def generate_infographic_content_version(
    session: AsyncSession,
    draft: ArticleDraft,
    settings: Settings,
    *,
    template_type: str,
    canvas_size: str,
) -> ImageWorkspaceRead:
    opinion = await session.scalar(
        select(OpinionMap)
        .where(OpinionMap.question_id == draft.question_id)
        .order_by(OpinionMap.version.desc())
        .limit(1)
    )
    if not opinion:
        snapshot = draft.analysis_snapshot.get("opinion_map")
        if not isinstance(snapshot, dict):
            raise ValueError("草稿还没有观点地图，无法生成信息图内容")
        opinion_data = OpinionMapData.model_validate(snapshot)
        opinion_payload = opinion_data.model_dump(mode="json")
    else:
        opinion_payload = OpinionMapData.model_validate(
            opinion.content_json
        ).model_dump(mode="json")
    clusters = await cluster_rows(session, draft.question_id)
    provider, _ = await _runtime_provider(session, settings)
    result = await InfographicContentService(
        provider,
        await get_active_prompt(
            session,
            "infographic_content_generation",
            INFOGRAPHIC_SYSTEM_PROMPT,
        ),
    ).generate(
        question_title=draft.question.title,
        opinion_map=opinion_payload,
        clusters=clusters,
        template_type=template_type,
    )
    await record_model_usage(
        session,
        result.usage,
        question_id=draft.question_id,
        task_id=None,
        stage="generating_infographic_content",
    )
    image_draft = await get_image_workspace(session, draft.id, create=True)
    assert image_draft is not None
    current = await _current_version(session, image_draft)
    template = await session.scalar(
        select(ImageTemplate)
        .where(ImageTemplate.template_type == template_type)
        .limit(1)
    )
    image_draft.template_id = template.id if template else image_draft.template_id
    image_draft.status = "content_ready"
    await _append_version(
        session,
        image_draft,
        content_json=_editor_defaults(
            result.data.model_dump(mode="json"),
            template_type=template_type,
            canvas_size=canvas_size,
        ),
        prompt_zh=current.prompt_zh if current else "",
        prompt_en=current.prompt_en if current else "",
        background_path=current.background_path if current else None,
        thumbnail_path=current.thumbnail_path if current else None,
        workflow_mode=current.workflow_mode if current else "copy_prompt_and_upload",
        copy_state=current.copy_state if current else {},
        uploaded_name=current.uploaded_name if current else None,
        content_type=current.content_type if current else None,
        byte_size=current.byte_size if current else 0,
        background_deleted=current.background_deleted if current else False,
    )
    await session.commit()
    return await workspace_to_read(session, image_draft)


async def generate_prompt_version(
    session: AsyncSession,
    draft: ArticleDraft,
    settings: Settings,
    *,
    visual_style: str,
    aspect_ratio: str,
) -> ImageWorkspaceRead:
    image_draft = await get_image_workspace(session, draft.id)
    current = (
        await _current_version(session, image_draft) if image_draft else None
    )
    if not current or not current.content_json.get("title"):
        await generate_infographic_content_version(
            session,
            draft,
            settings,
            template_type="knowledge_card",
            canvas_size="1080x1440",
        )
        image_draft = await get_image_workspace(session, draft.id)
        assert image_draft is not None
        current = await _current_version(session, image_draft)
    assert image_draft is not None and current is not None
    infographic = InfographicContentData.model_validate(current.content_json)
    provider = ManualImageWorkflowProvider()
    prompt_zh, prompt_en = provider.prompts(
        question_title=draft.question.title,
        infographic=infographic.model_dump(mode="json"),
        visual_style=visual_style,
        aspect_ratio=aspect_ratio,
    )
    next_content = {
        **current.content_json,
        "visual_style": visual_style,
        "aspect_ratio": aspect_ratio,
    }
    image_draft.status = "prompt_ready"
    await _append_version(
        session,
        image_draft,
        content_json=next_content,
        prompt_zh=prompt_zh,
        prompt_en=prompt_en,
        background_path=current.background_path,
        thumbnail_path=current.thumbnail_path,
        workflow_mode="copy_prompt_and_upload",
        copy_state={},
        uploaded_name=current.uploaded_name,
        content_type=current.content_type,
        byte_size=current.byte_size,
        background_deleted=current.background_deleted,
    )
    await session.commit()
    return await workspace_to_read(session, image_draft)


async def update_infographic_version(
    session: AsyncSession,
    image_draft: ImageDraft,
    payload: ImageEditorUpdate,
) -> ImageWorkspaceRead:
    current = await _current_version(session, image_draft)
    if not current:
        raise ValueError("请先生成信息图内容")
    template = await session.scalar(
        select(ImageTemplate)
        .where(ImageTemplate.template_type == payload.template_type)
        .limit(1)
    )
    image_draft.template_id = template.id if template else image_draft.template_id
    image_draft.status = "edited"
    editor = payload.model_dump(mode="json", exclude={"content"})
    content_json = {
        **payload.content.model_dump(mode="json"),
        **editor,
        "aspect_ratio": "3:4",
        "suggested_size": payload.canvas_size.replace("x", "×"),
        "negative_constraints": current.content_json.get(
            "negative_constraints", []
        ),
    }
    await _append_version(
        session,
        image_draft,
        content_json=content_json,
        prompt_zh=current.prompt_zh,
        prompt_en=current.prompt_en,
        background_path=current.background_path,
        thumbnail_path=current.thumbnail_path,
        workflow_mode=current.workflow_mode,
        copy_state=current.copy_state,
        uploaded_name=current.uploaded_name,
        content_type=current.content_type,
        byte_size=current.byte_size,
        background_deleted=current.background_deleted,
    )
    await session.commit()
    return await workspace_to_read(session, image_draft)


async def restore_image_version(
    session: AsyncSession,
    image_draft: ImageDraft,
    version_number: int,
) -> ImageWorkspaceRead:
    source = await session.scalar(
        select(ImageVersion).where(
            ImageVersion.image_draft_id == image_draft.id,
            ImageVersion.version == version_number,
        )
    )
    if not source:
        raise ValueError("要恢复的图片版本不存在")
    image_draft.status = "restored"
    image_draft.use_css_background = bool(
        source.content_json.get("use_css_background", source.background_deleted)
    )
    await _append_version(
        session,
        image_draft,
        content_json={**source.content_json, "restored_from": source.version},
        prompt_zh=source.prompt_zh,
        prompt_en=source.prompt_en,
        background_path=source.background_path,
        thumbnail_path=source.thumbnail_path,
        workflow_mode=source.workflow_mode,
        copy_state=source.copy_state,
        uploaded_name=source.uploaded_name,
        content_type=source.content_type,
        byte_size=source.byte_size,
        background_deleted=source.background_deleted,
    )
    await session.commit()
    return await workspace_to_read(session, image_draft)


async def mark_prompt_copied(
    session: AsyncSession, image_draft: ImageDraft, language: str
) -> ImageWorkspaceRead:
    current = await _current_version(session, image_draft)
    if not current:
        raise ValueError("请先生成图片 Prompt")
    current.copy_state = {**(current.copy_state or {}), language: True}
    image_draft.status = "prompt_copied"
    await session.commit()
    return await workspace_to_read(session, image_draft)


def _detect_image(payload: bytes) -> tuple[str, str]:
    for signature, value in IMAGE_SIGNATURES.items():
        if payload.startswith(signature):
            if value[0] == "webp" and payload[8:12] != b"WEBP":
                continue
            return value
    raise ValueError("只允许上传 PNG、JPEG 或 WebP 图片")


def _write_thumbnail(payload: bytes, target: Path) -> None:
    try:
        with Image.open(io.BytesIO(payload)) as source:
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGB")
            thumb = ImageOps.fit(
                image,
                (360, 480),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            thumb.save(target, format="JPEG", quality=86, optimize=True)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("图片内容无法解析，请重新导出后上传") from exc


async def upload_background(
    session: AsyncSession,
    image_draft: ImageDraft,
    upload: UploadFile,
) -> ImageWorkspaceRead:
    payload = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ValueError("图片超过 10 MB，请压缩后重试")
    if not payload:
        raise ValueError("上传文件为空")
    extension, content_type = _detect_image(payload)
    current = await _current_version(session, image_draft)
    if not current:
        raise ValueError("请先生成图片 Prompt，再上传背景图")
    folder = (
        REPOSITORY_ROOT / "data" / "uploads" / "images" / image_draft.article_draft_id
    ).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    stem = uuid.uuid4().hex
    target = folder / f"{stem}.{extension}"
    thumbnail = folder / f"{stem}-thumbnail.jpg"
    target.write_bytes(payload)
    try:
        _write_thumbnail(payload, thumbnail)
    except ValueError:
        target.unlink(missing_ok=True)
        raise
    image_draft.status = "background_uploaded"
    image_draft.use_css_background = False
    content_json = {**current.content_json, "use_css_background": False}
    await _append_version(
        session,
        image_draft,
        content_json=content_json,
        prompt_zh=current.prompt_zh,
        prompt_en=current.prompt_en,
        background_path=str(target),
        thumbnail_path=str(thumbnail),
        workflow_mode=current.workflow_mode,
        copy_state=current.copy_state,
        uploaded_name=(upload.filename or f"background.{extension}")[:500],
        content_type=content_type,
        byte_size=len(payload),
        background_deleted=False,
    )
    await session.commit()
    return await workspace_to_read(session, image_draft)


async def remove_background(
    session: AsyncSession, image_draft: ImageDraft
) -> ImageWorkspaceRead:
    current = await _current_version(session, image_draft)
    if not current:
        raise ValueError("图片工作区还没有版本")
    image_draft.status = "css_only"
    image_draft.use_css_background = True
    await _append_version(
        session,
        image_draft,
        content_json={**current.content_json, "use_css_background": True},
        prompt_zh=current.prompt_zh,
        prompt_en=current.prompt_en,
        background_path=None,
        thumbnail_path=None,
        workflow_mode=current.workflow_mode,
        copy_state=current.copy_state,
        byte_size=0,
        background_deleted=True,
    )
    await session.commit()
    return await workspace_to_read(session, image_draft)


async def set_css_mode(
    session: AsyncSession, image_draft: ImageDraft, *, enabled: bool
) -> ImageWorkspaceRead:
    current = await _current_version(session, image_draft)
    if not current:
        raise ValueError("图片工作区还没有版本")
    if not enabled and (
        current.background_deleted or not current.background_path
    ):
        raise ValueError("请先上传背景图，再关闭纯 CSS 背景")
    image_draft.use_css_background = enabled
    image_draft.status = "css_only" if enabled else "background_uploaded"
    await _append_version(
        session,
        image_draft,
        content_json={**current.content_json, "use_css_background": enabled},
        prompt_zh=current.prompt_zh,
        prompt_en=current.prompt_en,
        background_path=current.background_path,
        thumbnail_path=current.thumbnail_path,
        workflow_mode=current.workflow_mode,
        copy_state=current.copy_state,
        uploaded_name=current.uploaded_name,
        content_type=current.content_type,
        byte_size=current.byte_size,
        background_deleted=current.background_deleted,
    )
    await session.commit()
    return await workspace_to_read(session, image_draft)


def _resolve_controlled_path(
    raw_path: str | None, root: Path, missing_message: str
) -> Path:
    if not raw_path:
        raise FileNotFoundError(missing_message)
    path = Path(raw_path).resolve()
    controlled_root = root.resolve()
    if controlled_root not in path.parents or not path.is_file():
        raise FileNotFoundError(missing_message)
    return path


def resolve_background_path(version: ImageVersion) -> Path:
    if version.background_deleted:
        raise FileNotFoundError("该图片版本没有背景图")
    return _resolve_controlled_path(
        version.background_path,
        REPOSITORY_ROOT / "data" / "uploads" / "images",
        "背景图文件不存在或路径无效",
    )


def resolve_thumbnail_path(version: ImageVersion) -> Path:
    if version.background_deleted:
        raise FileNotFoundError("该图片版本没有缩略图")
    return _resolve_controlled_path(
        version.thumbnail_path,
        REPOSITORY_ROOT / "data" / "uploads" / "images",
        "缩略图文件不存在或路径无效",
    )


def resolve_rendered_path(version: ImageVersion) -> Path:
    return _resolve_controlled_path(
        version.rendered_path,
        REPOSITORY_ROOT / "data" / "rendered" / "images",
        "渲染 PNG 不存在或路径无效",
    )


def resolve_html_snapshot_path(version: ImageVersion) -> Path:
    return _resolve_controlled_path(
        version.html_snapshot_path,
        REPOSITORY_ROOT / "data" / "rendered" / "images",
        "HTML 快照不存在或路径无效",
    )
