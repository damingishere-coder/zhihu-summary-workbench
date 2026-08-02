from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.api.dependencies import get_broker
from backend.app.core.config import Settings, get_settings
from backend.app.collectors.zhihu import ZhihuCollector
from backend.app.db.session import get_db_session
from backend.app.models.core import ArticleDraft, Question, QuestionSource, TaskJob
from backend.app.schemas.analysis import HotQuestionFetchRequest, HotQuestionFetchResponse
from backend.app.schemas.question import (
    QuestionCreate,
    QuestionDetail,
    QuestionImportRequest,
    QuestionImportResponse,
    QuestionListResponse,
    QuestionRead,
    QuestionUpdate,
)
from backend.app.schemas.task import TaskRead
from backend.app.services.queue import QueueBroker
from backend.app.services.question_deletion import permanently_delete_question
from backend.app.services.questions import (
    create_question,
    import_questions,
    question_hash,
    update_question,
)
from backend.app.services.settings import configured_settings_copy
from backend.app.services.serializers import task_to_read
from backend.app.services.tasks import create_task


router = APIRouter(prefix="/questions", tags=["questions"])


@router.post("/manual", response_model=QuestionRead, status_code=status.HTTP_201_CREATED)
async def add_manual_question(
    payload: QuestionCreate,
    session: AsyncSession = Depends(get_db_session),
) -> Question:
    try:
        return await create_question(session, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/import", response_model=QuestionImportResponse)
async def import_question_list(
    payload: QuestionImportRequest,
    session: AsyncSession = Depends(get_db_session),
) -> QuestionImportResponse:
    return await import_questions(session, payload)


@router.get("", response_model=QuestionListResponse)
async def list_questions(
    status_filter: str | None = Query(default=None, alias="status"),
    source: str | None = None,
    priority: str | None = None,
    search: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
) -> QuestionListResponse:
    conditions = []
    if status_filter:
        conditions.append(Question.status == status_filter)
    if source:
        conditions.append(Question.source == source)
    if priority:
        conditions.append(Question.priority == priority)
    if search:
        pattern = f"%{search.strip()}%"
        conditions.append(
            or_(Question.title.ilike(pattern), Question.url.ilike(pattern))
        )
    statement = (
        select(Question)
        .where(*conditions)
        .order_by(Question.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    count_statement = select(func.count(Question.id)).where(*conditions)
    items = (await session.scalars(statement)).all()
    total = int((await session.scalar(count_statement)) or 0)
    return QuestionListResponse(
        items=[QuestionRead.model_validate(item) for item in items],
        total=total,
    )


@router.post("/hot/fetch", response_model=HotQuestionFetchResponse)
async def fetch_hot_questions(
    payload: HotQuestionFetchRequest,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> HotQuestionFetchResponse:
    runtime = await configured_settings_copy(session, settings)
    collector = ZhihuCollector(runtime)
    try:
        collected, used_mode, warnings = await collector.fetch_hot_questions(
            limit=payload.limit,
            collector_mode=payload.collector_mode,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    created = 0
    updated = 0
    for item in collected:
        question = await session.scalar(
            select(Question).where(Question.external_id == item.external_id)
        )
        if question:
            question.title = item.title
            question.description = item.description or question.description
            question.hot_rank = item.hot_rank
            question.hot_score = item.hot_score
            question.answer_count = item.answer_count
            question.follower_count = item.follower_count
            question.source = "hot"
            question.content_hash = question_hash(
                question.title, question.url, question.description
            )
            updated += 1
        else:
            question = Question(
                external_id=item.external_id,
                title=item.title,
                url=item.url,
                description=item.description,
                sample_answer="",
                source="hot",
                status="candidate",
                priority="medium",
                content_hash=question_hash(
                    item.title, item.url, item.description
                ),
                hot_rank=item.hot_rank,
                hot_score=item.hot_score,
                answer_count=item.answer_count,
                follower_count=item.follower_count,
            )
            session.add(question)
            await session.flush()
            created += 1
        session.add(
            QuestionSource(
                question_id=question.id,
                source_type=f"hot_{used_mode}",
                source_url=item.url,
                raw_data=item.raw_snapshot,
            )
        )
    await session.commit()
    return HotQuestionFetchResponse(
        fetched=len(collected),
        created=created,
        updated=updated,
        collector_mode=used_mode,
        warnings=warnings,
    )


@router.get("/{question_id}", response_model=QuestionDetail)
async def get_question(
    question_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> QuestionDetail:
    question = await session.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="问题不存在")
    latest_task_id = await session.scalar(
        select(TaskJob.id)
        .where(TaskJob.question_id == question_id)
        .order_by(TaskJob.created_at.desc())
        .limit(1)
    )
    latest_draft_id = await session.scalar(
        select(ArticleDraft.id)
        .where(ArticleDraft.question_id == question_id)
        .order_by(ArticleDraft.created_at.desc())
        .limit(1)
    )
    return QuestionDetail(
        **QuestionRead.model_validate(question).model_dump(),
        latest_task_id=latest_task_id,
        latest_draft_id=latest_draft_id,
    )


@router.patch("/{question_id}", response_model=QuestionRead)
async def patch_question(
    question_id: str,
    payload: QuestionUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> Question:
    question = await session.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="问题不存在")
    return await update_question(session, question, payload)


@router.post("/{question_id}/queue", response_model=TaskRead, status_code=201)
async def queue_question(
    question_id: str,
    session: AsyncSession = Depends(get_db_session),
    broker: QueueBroker = Depends(get_broker),
    settings: Settings = Depends(get_settings),
) -> TaskRead:
    question = await session.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="问题不存在")
    try:
        task = await create_task(session, broker, question, settings)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    task = await session.scalar(
        select(TaskJob)
        .options(selectinload(TaskJob.question))
        .where(TaskJob.id == task.id)
    )
    return task_to_read(task)


@router.post("/{question_id}/ignore", response_model=QuestionRead)
async def ignore_question(
    question_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> Question:
    question = await session.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="问题不存在")
    return await update_question(
        session, question, QuestionUpdate(status="ignored")
    )


@router.delete("/{question_id}", status_code=204)
async def delete_question(
    question_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    question = await session.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="问题不存在")
    try:
        await permanently_delete_question(session, question)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
