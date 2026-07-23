from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.db.session import get_db_session
from backend.app.models.core import ArticleDraft
from backend.app.models.media import ImageDraft, ImageVersion
from backend.app.schemas.image import (
    CssModeRequest,
    GenerateImagePromptRequest,
    ImageCopyRequest,
    ImageWorkspaceRead,
)
from backend.app.services.image_workflow import (
    generate_prompt_version,
    get_image_workspace,
    mark_prompt_copied,
    remove_background,
    resolve_background_path,
    set_css_mode,
    upload_background,
    workspace_to_read,
)


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
    "/drafts/{draft_id}/generate-image-prompt",
    response_model=ImageWorkspaceRead,
)
async def generate_image_prompt(
    draft_id: str,
    payload: GenerateImagePromptRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ImageWorkspaceRead:
    draft = await _draft(session, draft_id)
    try:
        return await generate_prompt_version(
            session,
            draft,
            visual_style=payload.visual_style,
            aspect_ratio=payload.aspect_ratio,
        )
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
    return await set_css_mode(session, item, enabled=payload.enabled)


@router.get("/images/{image_id}/versions", response_model=ImageWorkspaceRead)
async def get_image_versions(
    image_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> ImageWorkspaceRead:
    item = await _workspace(session, image_id)
    return await workspace_to_read(session, item)


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
