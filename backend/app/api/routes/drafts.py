from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.db.session import get_db_session
from backend.app.models.core import ArticleDraft, ArticleVersion
from backend.app.schemas.draft import DraftListResponse, DraftRead, DraftUpdate
from backend.app.services.serializers import draft_to_read


router = APIRouter(prefix="/drafts", tags=["drafts"])


async def load_draft(session: AsyncSession, draft_id: str) -> ArticleDraft | None:
    return await session.scalar(
        select(ArticleDraft)
        .options(selectinload(ArticleDraft.question))
        .where(ArticleDraft.id == draft_id)
    )


@router.get("", response_model=DraftListResponse)
async def list_drafts(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
) -> DraftListResponse:
    statement = (
        select(ArticleDraft)
        .options(selectinload(ArticleDraft.question))
        .order_by(ArticleDraft.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = (await session.scalars(statement)).all()
    total = int((await session.scalar(select(func.count(ArticleDraft.id)))) or 0)
    return DraftListResponse(
        items=[draft_to_read(item) for item in items],
        total=total,
    )


@router.get("/{draft_id}", response_model=DraftRead)
async def get_draft(
    draft_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> DraftRead:
    draft = await load_draft(session, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")
    return draft_to_read(draft)


@router.patch("/{draft_id}", response_model=DraftRead)
async def update_draft(
    draft_id: str,
    payload: DraftUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> DraftRead:
    draft = await load_draft(session, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")
    values = payload.model_dump(exclude_none=True)
    for key, value in values.items():
        setattr(draft, key, value)
    draft.current_version += 1
    session.add(
        ArticleVersion(
            draft_id=draft.id,
            version=draft.current_version,
            title=draft.title,
            content=draft.content,
            source_task_id=None,
        )
    )
    await session.commit()
    await session.refresh(draft)
    return draft_to_read(draft)

