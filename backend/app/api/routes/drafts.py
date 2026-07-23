from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.db.session import get_db_session
from backend.app.core.config import Settings, get_settings
from backend.app.models.content import Answer, ArticleParagraphSource, ClaimCluster
from backend.app.models.core import ArticleDraft, ArticleVersion, AuditLog
from backend.app.schemas.draft import (
    DraftListResponse,
    DraftRead,
    DraftRewriteRequest,
    DraftRewriteResponse,
    DraftReviewRequest,
    DraftUpdate,
    DraftVersionRead,
)
from backend.app.services.content_pipeline import (
    generate_article,
    review_article,
    rewrite_draft_text,
    usage_summary,
)
from backend.app.services.serializers import draft_to_read


router = APIRouter(prefix="/drafts", tags=["drafts"])


async def load_draft(session: AsyncSession, draft_id: str) -> ArticleDraft | None:
    return await session.scalar(
        select(ArticleDraft)
        .options(selectinload(ArticleDraft.question))
        .where(ArticleDraft.id == draft_id)
    )


async def serialize_draft(
    session: AsyncSession, draft: ArticleDraft
) -> DraftRead:
    version = await session.scalar(
        select(ArticleVersion).where(
            ArticleVersion.draft_id == draft.id,
            ArticleVersion.version == draft.current_version,
        )
    )
    source_payload: list[dict[str, object]] = []
    if version:
        rows = (
            await session.scalars(
                select(ArticleParagraphSource).where(
                    ArticleParagraphSource.article_version_id == version.id
                )
            )
        ).all()
        for row in rows:
            answer = await session.get(Answer, row.answer_id) if row.answer_id else None
            cluster = (
                await session.get(ClaimCluster, row.cluster_id)
                if row.cluster_id
                else None
            )
            source_payload.append(
                {
                    "paragraph_id": row.paragraph_id,
                    "answer_id": row.answer_id,
                    "answer_author": answer.author_name if answer else None,
                    "answer_url": answer.answer_url if answer else None,
                    "answer_excerpt": (
                        answer.plain_content[:220] if answer else None
                    ),
                    "cluster_id": row.cluster_id,
                    "cluster_name": cluster.name if cluster else None,
                }
            )
    return draft_to_read(draft, paragraph_sources=source_payload)


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
    return await serialize_draft(session, draft)


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
    draft.status = "waiting_review"
    draft.review_result = {}
    draft.reviewed_at = None
    draft.question.status = "waiting_review"
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
    return await serialize_draft(session, draft)


@router.post("/{draft_id}/regenerate", response_model=DraftRead)
async def regenerate_draft(
    draft_id: str,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DraftRead:
    draft = await load_draft(session, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")
    try:
        regenerated, _ = await generate_article(
            session, draft.question, settings
        )
        await review_article(
            session, draft.question, regenerated, settings
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    regenerated = await load_draft(session, regenerated.id)
    return await serialize_draft(session, regenerated)


@router.post("/{draft_id}/review", response_model=DraftRead)
async def review_draft(
    draft_id: str,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DraftRead:
    draft = await load_draft(session, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")
    try:
        await review_article(session, draft.question, draft, settings)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    draft = await load_draft(session, draft_id)
    return await serialize_draft(session, draft)


@router.post("/{draft_id}/rewrite", response_model=DraftRewriteResponse)
async def rewrite_draft_fragment(
    draft_id: str,
    payload: DraftRewriteRequest,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DraftRewriteResponse:
    draft = await load_draft(session, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")
    try:
        rewritten = await rewrite_draft_text(
            session,
            draft,
            settings,
            scope=payload.scope,
            text=payload.text,
            instruction=payload.instruction,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return DraftRewriteResponse(
        text=rewritten,
        usage=await usage_summary(session, draft.question_id),
    )


async def _set_review_status(
    session: AsyncSession,
    draft: ArticleDraft,
    *,
    status_value: str,
    reason: str,
) -> DraftRead:
    before = draft.status
    draft.status = status_value
    draft.question.status = status_value
    session.add(
        AuditLog(
            actor="operator",
            action=f"draft.{status_value}",
            entity_type="article_draft",
            entity_id=draft.id,
            before_data={"status": before},
            after_data={"status": status_value, "reason": reason},
        )
    )
    await session.commit()
    draft = await load_draft(session, draft.id)
    return await serialize_draft(session, draft)


@router.post("/{draft_id}/approve", response_model=DraftRead)
async def approve_draft(
    draft_id: str,
    payload: DraftReviewRequest | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> DraftRead:
    draft = await load_draft(session, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")
    if not draft.review_result:
        raise HTTPException(status_code=409, detail="请先完成独立质量审核")
    return await _set_review_status(
        session,
        draft,
        status_value="review_approved",
        reason=payload.reason if payload else "",
    )


@router.post("/{draft_id}/reject", response_model=DraftRead)
async def reject_draft(
    draft_id: str,
    payload: DraftReviewRequest | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> DraftRead:
    draft = await load_draft(session, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")
    return await _set_review_status(
        session,
        draft,
        status_value="review_rejected",
        reason=payload.reason if payload else "",
    )


@router.get("/{draft_id}/versions", response_model=list[DraftVersionRead])
async def list_draft_versions(
    draft_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[DraftVersionRead]:
    if not await session.get(ArticleDraft, draft_id):
        raise HTTPException(status_code=404, detail="草稿不存在")
    versions = (
        await session.scalars(
            select(ArticleVersion)
            .where(ArticleVersion.draft_id == draft_id)
            .order_by(ArticleVersion.version.desc())
        )
    ).all()
    return [DraftVersionRead.model_validate(item, from_attributes=True) for item in versions]
