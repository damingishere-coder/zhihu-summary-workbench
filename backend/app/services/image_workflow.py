from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.providers.manual_image import ManualImageWorkflowProvider
from backend.app.core.config import REPOSITORY_ROOT
from backend.app.models.content import OpinionMap
from backend.app.models.core import ArticleDraft
from backend.app.models.media import ImageDraft, ImageVersion
from backend.app.schemas.analysis import OpinionMapData
from backend.app.schemas.image import ImageVersionRead, ImageWorkspaceRead


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
IMAGE_SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": ("png", "image/png"),
    b"\xff\xd8\xff": ("jpg", "image/jpeg"),
    b"RIFF": ("webp", "image/webp"),
}


def _asset_url(version: ImageVersion) -> str | None:
    if not version.background_path or version.background_deleted:
        return None
    return f"/api/images/versions/{version.id}/background"


def version_to_read(version: ImageVersion) -> ImageVersionRead:
    return ImageVersionRead(
        id=version.id,
        version=version.version,
        content_json=version.content_json or {},
        prompt_zh=version.prompt_zh,
        prompt_en=version.prompt_en,
        background_url=_asset_url(version),
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
        item = ImageDraft(
            article_draft_id=draft_id,
            status="draft",
            current_version=0,
            use_css_background=True,
        )
        session.add(item)
        await session.flush()
    return item


async def generate_prompt_version(
    session: AsyncSession,
    draft: ArticleDraft,
    *,
    visual_style: str,
    aspect_ratio: str,
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
            raise ValueError("草稿还没有观点地图，无法生成图片 Prompt")
        opinion_data = OpinionMapData.model_validate(snapshot)
    else:
        opinion_data = OpinionMapData.model_validate(opinion.content_json)
    provider = ManualImageWorkflowProvider()
    infographic = provider.infographic_content(
        question_title=draft.question.title,
        opinion_map=opinion_data,
    )
    prompt_zh, prompt_en = provider.prompts(
        question_title=draft.question.title,
        infographic=infographic,
        visual_style=visual_style,
        aspect_ratio=aspect_ratio,
    )
    image_draft = await get_image_workspace(session, draft.id, create=True)
    assert image_draft is not None
    current = None
    if image_draft.current_version:
        current = await session.scalar(
            select(ImageVersion).where(
                ImageVersion.image_draft_id == image_draft.id,
                ImageVersion.version == image_draft.current_version,
            )
        )
    image_draft.current_version += 1
    image_draft.status = "prompt_ready"
    session.add(
        ImageVersion(
            image_draft_id=image_draft.id,
            version=image_draft.current_version,
            content_json={
                **infographic,
                "visual_style": visual_style,
                "aspect_ratio": aspect_ratio,
                "suggested_size": "1080×1440",
                "negative_constraints": [
                    "不得生成中文或英文文字",
                    "不得出现水印、Logo 或二维码",
                    "避免密集细节和高干扰背景",
                ],
            },
            prompt_zh=prompt_zh,
            prompt_en=prompt_en,
            background_path=current.background_path if current else None,
            workflow_mode="copy_prompt_and_upload",
            copy_state={},
            uploaded_name=current.uploaded_name if current else None,
            content_type=current.content_type if current else None,
            byte_size=current.byte_size if current else 0,
        )
    )
    await session.commit()
    return await workspace_to_read(session, image_draft)


async def mark_prompt_copied(
    session: AsyncSession, image_draft: ImageDraft, language: str
) -> ImageWorkspaceRead:
    current = await session.scalar(
        select(ImageVersion).where(
            ImageVersion.image_draft_id == image_draft.id,
            ImageVersion.version == image_draft.current_version,
        )
    )
    if not current:
        raise ValueError("请先生成图片 Prompt")
    current.copy_state = {
        **(current.copy_state or {}),
        language: True,
    }
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
    current = await session.scalar(
        select(ImageVersion).where(
            ImageVersion.image_draft_id == image_draft.id,
            ImageVersion.version == image_draft.current_version,
        )
    )
    if not current:
        raise ValueError("请先生成图片 Prompt，再上传背景图")
    folder = (
        REPOSITORY_ROOT / "data" / "uploads" / "images" / image_draft.article_draft_id
    ).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{uuid.uuid4().hex}.{extension}"
    target.write_bytes(payload)
    image_draft.current_version += 1
    image_draft.status = "background_uploaded"
    image_draft.use_css_background = False
    session.add(
        ImageVersion(
            image_draft_id=image_draft.id,
            version=image_draft.current_version,
            content_json=current.content_json,
            prompt_zh=current.prompt_zh,
            prompt_en=current.prompt_en,
            background_path=str(target),
            workflow_mode=current.workflow_mode,
            copy_state=current.copy_state,
            uploaded_name=(upload.filename or f"background.{extension}")[:500],
            content_type=content_type,
            byte_size=len(payload),
            background_deleted=False,
        )
    )
    await session.commit()
    return await workspace_to_read(session, image_draft)


async def remove_background(
    session: AsyncSession, image_draft: ImageDraft
) -> ImageWorkspaceRead:
    current = await session.scalar(
        select(ImageVersion).where(
            ImageVersion.image_draft_id == image_draft.id,
            ImageVersion.version == image_draft.current_version,
        )
    )
    if not current:
        raise ValueError("图片工作区还没有版本")
    image_draft.current_version += 1
    image_draft.status = "css_only"
    image_draft.use_css_background = True
    session.add(
        ImageVersion(
            image_draft_id=image_draft.id,
            version=image_draft.current_version,
            content_json=current.content_json,
            prompt_zh=current.prompt_zh,
            prompt_en=current.prompt_en,
            background_path=None,
            workflow_mode=current.workflow_mode,
            copy_state=current.copy_state,
            byte_size=0,
            background_deleted=True,
        )
    )
    await session.commit()
    return await workspace_to_read(session, image_draft)


async def set_css_mode(
    session: AsyncSession, image_draft: ImageDraft, *, enabled: bool
) -> ImageWorkspaceRead:
    image_draft.use_css_background = enabled
    image_draft.status = "css_only" if enabled else image_draft.status
    await session.commit()
    return await workspace_to_read(session, image_draft)


def resolve_background_path(version: ImageVersion) -> Path:
    if not version.background_path or version.background_deleted:
        raise FileNotFoundError("该图片版本没有背景图")
    path = Path(version.background_path).resolve()
    upload_root = (REPOSITORY_ROOT / "data" / "uploads" / "images").resolve()
    if upload_root not in path.parents or not path.is_file():
        raise FileNotFoundError("背景图文件不存在或路径无效")
    return path
