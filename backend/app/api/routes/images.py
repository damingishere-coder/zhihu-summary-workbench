from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import Settings, get_settings
from backend.app.db.session import get_db_session
from backend.app.models.core import ArticleDraft
from backend.app.models.media import ImageDraft, ImageTemplate, ImageVersion
from backend.app.schemas.image import (
    BatchRenderRequest,
    BatchRenderResult,
    CssModeRequest,
    GenerateImagePromptRequest,
    GenerateInfographicContentRequest,
    ImageCopyRequest,
    ImageEditorUpdate,
    ImageRestoreRequest,
    ImageTemplateRead,
    ImageWorkspaceRead,
    RenderImageRequest,
)
from backend.app.services.image_workflow import (
    generate_infographic_content_version,
    generate_prompt_version,
    get_image_workspace,
    mark_prompt_copied,
    remove_background,
    resolve_background_path,
    resolve_html_snapshot_path,
    resolve_rendered_path,
    resolve_thumbnail_path,
    restore_image_version,
    set_css_mode,
    update_infographic_version,
    upload_background,
    workspace_to_read,
)
from backend.app.services.infographic_renderer import render_image_workspace


router = APIRouter(tags=["images"])


async def _draft(session: AsyncSession, draft_id: str) -> ArticleDraft:
    item = await session.scalar(
        select(ArticleDraft)
        .options(selectinload(ArticleDraft.question))
        .where(ArticleDraft.id == draft_id)
    )
    if not item:
        raise HTTPException(status_code=404, detail="草稿不存在")
    return item


async def _workspace(session: AsyncSession, image_id: str) -> ImageDraft:
    item = await session.get(ImageDraft, image_id)
    if not item:
        raise HTTPException(status_code=404, detail="图片工作区不存在")
    return item


async def _version(
    session: AsyncSession,
    image_draft: ImageDraft,
    version_number: int | None = None,
) -> ImageVersion:
    target = version_number or image_draft.current_version
    item = await session.scalar(
        select(ImageVersion).where(
            ImageVersion.image_draft_id == image_draft.id,
            ImageVersion.version == target,
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="图片版本不存在")
    return item


@router.get("/image-templates", response_model=list[ImageTemplateRead])
async def list_image_templates(
    session: AsyncSession = Depends(get_db_session),
) -> list[ImageTemplateRead]:
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


@router.get(
    "/drafts/{draft_id}/image-workspace",
    response_model=ImageWorkspaceRead | None,
)
async def get_draft_image_workspace(
    draft_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> ImageWorkspaceRead | None:
    await _draft(session, draft_id)
    item = await get_image_workspace(session, draft_id)
    return await workspace_to_read(session, item) if item else None


@router.post(
    "/drafts/{draft_id}/generate-infographic-content",
    response_model=ImageWorkspaceRead,
)
async def generate_infographic_content(
    draft_id: str,
    payload: GenerateInfographicContentRequest,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ImageWorkspaceRead:
    draft = await _draft(session, draft_id)
    try:
        return await generate_infographic_content_version(
            session,
            draft,
            settings,
            template_type=payload.template_type,
            canvas_size=payload.canvas_size,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/drafts/{draft_id}/generate-image-prompt",
    response_model=ImageWorkspaceRead,
)
async def generate_image_prompt(
    draft_id: str,
    payload: GenerateImagePromptRequest,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ImageWorkspaceRead:
    draft = await _draft(session, draft_id)
    try:
        return await generate_prompt_version(
            session,
            draft,
            settings,
            visual_style=payload.visual_style,
            aspect_ratio=payload.aspect_ratio,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/drafts/{draft_id}/upload-visual-asset",
    response_model=ImageWorkspaceRead,
)
async def upload_visual_asset(
    draft_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
) -> ImageWorkspaceRead:
    await _draft(session, draft_id)
    item = await get_image_workspace(session, draft_id)
    if not item:
        raise HTTPException(status_code=409, detail="请先生成图片 Prompt")
    try:
        return await upload_background(session, item, file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/images/render-batch", response_model=BatchRenderResult)
async def render_batch(
    payload: BatchRenderRequest,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> BatchRenderResult:
    result = BatchRenderResult()
    for image_id in payload.image_ids:
        item = await session.get(ImageDraft, image_id)
        if not item:
            result.failed[image_id] = "图片工作区不存在"
            continue
        try:
            await render_image_workspace(session, item, settings)
            result.rendered.append(image_id)
        except (ValueError, RuntimeError) as exc:
            result.failed[image_id] = str(exc)
    return result


@router.get("/images/{image_id}", response_model=ImageWorkspaceRead)
async def get_image(
    image_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> ImageWorkspaceRead:
    item = await _workspace(session, image_id)
    return await workspace_to_read(session, item)


@router.patch("/images/{image_id}", response_model=ImageWorkspaceRead)
async def patch_image(
    image_id: str,
    payload: ImageEditorUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> ImageWorkspaceRead:
    item = await _workspace(session, image_id)
    try:
        return await update_infographic_version(session, item, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/images/{image_id}/regenerate-prompt",
    response_model=ImageWorkspaceRead,
)
async def regenerate_prompt(
    image_id: str,
    payload: GenerateImagePromptRequest,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ImageWorkspaceRead:
    item = await _workspace(session, image_id)
    draft = await _draft(session, item.article_draft_id)
    try:
        return await generate_prompt_version(
            session,
            draft,
            settings,
            visual_style=payload.visual_style,
            aspect_ratio=payload.aspect_ratio,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/images/{image_id}/render", response_model=ImageWorkspaceRead)
async def render_image(
    image_id: str,
    payload: RenderImageRequest | None = None,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ImageWorkspaceRead:
    item = await _workspace(session, image_id)
    try:
        return await render_image_workspace(
            session,
            item,
            settings,
            version_number=payload.version if payload else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post(
    "/images/{image_id}/restore", response_model=ImageWorkspaceRead
)
async def restore_version(
    image_id: str,
    payload: ImageRestoreRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ImageWorkspaceRead:
    item = await _workspace(session, image_id)
    try:
        return await restore_image_version(session, item, payload.version)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/images/{image_id}/mark-copied", response_model=ImageWorkspaceRead
)
async def mark_copied(
    image_id: str,
    payload: ImageCopyRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ImageWorkspaceRead:
    item = await _workspace(session, image_id)
    try:
        return await mark_prompt_copied(session, item, payload.language)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/images/{image_id}/upload-background",
    response_model=ImageWorkspaceRead,
)
async def upload_image_background(
    image_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
) -> ImageWorkspaceRead:
    item = await _workspace(session, image_id)
    try:
        return await upload_background(session, item, file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete(
    "/images/{image_id}/background", response_model=ImageWorkspaceRead
)
async def delete_background(
    image_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> ImageWorkspaceRead:
    item = await _workspace(session, image_id)
    try:
        return await remove_background(session, item)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/images/{image_id}/css-mode", response_model=ImageWorkspaceRead)
async def toggle_css_mode(
    image_id: str,
    payload: CssModeRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ImageWorkspaceRead:
    item = await _workspace(session, image_id)
    try:
        return await set_css_mode(session, item, enabled=payload.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/images/{image_id}/versions", response_model=ImageWorkspaceRead)
async def get_image_versions(
    image_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> ImageWorkspaceRead:
    item = await _workspace(session, image_id)
    return await workspace_to_read(session, item)


@router.get("/images/{image_id}/download")
async def download_image(
    image_id: str,
    version: int | None = Query(default=None, ge=1),
    session: AsyncSession = Depends(get_db_session),
) -> FileResponse:
    item = await _workspace(session, image_id)
    image_version = await _version(session, item, version)
    try:
        path = resolve_rendered_path(image_version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type="image/png",
        filename=f"infographic-v{image_version.version}-{image_id}.png",
    )


@router.get("/images/versions/{version_id}/background")
async def get_background_file(
    version_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> FileResponse:
    version = await session.get(ImageVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="图片版本不存在")
    try:
        path = resolve_background_path(version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type=version.content_type or "application/octet-stream",
    )


@router.get("/images/versions/{version_id}/thumbnail")
async def get_thumbnail_file(
    version_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> FileResponse:
    version = await session.get(ImageVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="图片版本不存在")
    try:
        path = resolve_thumbnail_path(version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="image/jpeg")


@router.get("/images/versions/{version_id}/html")
async def get_html_snapshot(
    version_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> FileResponse:
    version = await session.get(ImageVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="图片版本不存在")
    try:
        path = resolve_html_snapshot_path(version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="text/html; charset=utf-8")
