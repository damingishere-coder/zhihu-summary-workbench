from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
import secrets

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import Settings, get_settings
from backend.app.api.dependencies import get_broker
from backend.app.db.session import get_db_session
from backend.app.models.content import Answer, AnswerAnalysis
from backend.app.models.core import Question
from backend.app.models.core import TaskJob, TaskLog
from backend.app.models.browser_bridge import CollectionJob
from backend.app.schemas.analysis import (
    AnswerListResponse,
    AnswerRead,
    FetchAnswersRequest,
    FetchAnswersResponse,
)
from backend.app.schemas.browser_bridge import (
    ImportAnswersResponse,
    ImportBundleV1,
    MAX_BRIDGE_PAYLOAD_BYTES,
)
from backend.app.services.browser_bridge import bundle_to_fetch_result
from backend.app.services.content_pipeline import fetch_and_store_answers
from backend.app.services.queue import QueueBroker


router = APIRouter(tags=["answers"])


async def _answer_read(session: AsyncSession, answer: Answer) -> AnswerRead:
    analysis = await session.scalar(
        select(AnswerAnalysis).where(AnswerAnalysis.answer_id == answer.id)
    )
    return AnswerRead(
        id=answer.id,
        question_id=answer.question_id,
        answer_external_id=answer.answer_external_id,
        author_name=answer.author_name,
        author_url=answer.author_url,
        answer_url=answer.answer_url,
        markdown_content=answer.markdown_content,
        plain_content=answer.plain_content,
        vote_count=answer.vote_count,
        comment_count=answer.comment_count,
        published_at=answer.published_at,
        external_updated_at=answer.external_updated_at,
        sort_order=answer.sort_order,
        media_json=answer.media_json or {},
        fetch_batch=answer.fetch_batch,
        included_for_analysis=answer.included_for_analysis,
        filter_reason=answer.filter_reason,
        created_at=answer.created_at,
        updated_at=answer.updated_at,
        analysis=(
            {
                **(analysis.structured_result or {}),
                "summary": analysis.summary,
                "quality_score": analysis.quality_score,
                "relevance_score": analysis.relevance_score,
                "information_density": analysis.information_density,
                "include": analysis.include,
                "reason": analysis.reason,
            }
            if analysis
            else None
        ),
    )


@router.get("/questions/{question_id}/answers", response_model=AnswerListResponse)
async def list_answers(
    question_id: str,
    included: bool | None = None,
    search: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
) -> AnswerListResponse:
    if not await session.get(Question, question_id):
        raise HTTPException(status_code=404, detail="问题不存在")
    conditions = [Answer.question_id == question_id]
    if included is not None:
        conditions.append(Answer.included_for_analysis.is_(included))
    if search:
        pattern = f"%{search.strip()}%"
        conditions.append(
            or_(
                Answer.author_name.ilike(pattern),
                Answer.plain_content.ilike(pattern),
            )
        )
    items = (
        await session.scalars(
            select(Answer)
            .where(*conditions)
            .order_by(
                Answer.included_for_analysis.desc(),
                Answer.vote_count.desc(),
                Answer.sort_order,
            )
            .offset(offset)
            .limit(limit)
        )
    ).all()
    total = int(
        (
            await session.scalar(
                select(func.count(Answer.id)).where(*conditions)
            )
        )
        or 0
    )
    included_count = int(
        (
            await session.scalar(
                select(func.count(Answer.id)).where(
                    Answer.question_id == question_id,
                    Answer.included_for_analysis.is_(True),
                )
            )
        )
        or 0
    )
    all_count = int(
        (
            await session.scalar(
                select(func.count(Answer.id)).where(
                    Answer.question_id == question_id
                )
            )
        )
        or 0
    )
    return AnswerListResponse(
        items=[await _answer_read(session, item) for item in items],
        total=total,
        included=included_count,
        filtered=all_count - included_count,
    )


@router.post(
    "/questions/{question_id}/fetch-answers",
    response_model=FetchAnswersResponse,
)
async def fetch_answers(
    question_id: str,
    payload: FetchAnswersRequest,
) -> FetchAnswersResponse:
    raise HTTPException(
        status_code=410,
        detail=(
            "旧的独立 Playwright 回答采集已停用。请创建任务并使用 Chrome 扩展采集，"
            "或导入 ImportBundleV1 JSON。"
        ),
    )


@router.post(
    "/questions/{question_id}/answers/import",
    response_model=ImportAnswersResponse,
)
async def import_answers(
    question_id: str,
    payload: ImportBundleV1,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    broker: QueueBroker = Depends(get_broker),
) -> ImportAnswersResponse:
    if len(payload.model_dump_json().encode("utf-8")) > MAX_BRIDGE_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="导入文件超过 6 MiB 上限")
    question = await session.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="问题不存在")
    if payload.question.id != question.external_id:
        raise HTTPException(status_code=409, detail="导入数据的问题 id 与当前问题不一致")
    result = bundle_to_fetch_result(payload, collector_mode="json_import")
    job = CollectionJob(
        task_id=None,
        question_id=question.id,
        nonce=secrets.token_hex(16),
        status="completed",
        mode=payload.mode,
        max_answers=len(payload.answers),
        source="import",
        capture_version=1,
        capture_method="json_import",
        collected_answer_count=len(payload.answers),
        capture_diagnostics_json=[
            {
                "code": "manual_json_import",
                "level": "warning",
                "message": "人工 JSON 导入不代表实时自动采集成功",
            }
        ],
        request_json={"question_external_id": question.external_id, "mode": payload.mode},
        result_json=payload.model_dump(mode="json"),
        completed_at=payload.collected_at,
    )
    session.add(job)
    await session.flush()
    _, counts = await fetch_and_store_answers(
        session,
        question,
        settings,
        FetchAnswersRequest(
            mode=payload.mode,
            max_answers=len(payload.answers),
            collector_mode="auto",
        ),
        precollected=result,
    )
    task = await session.scalar(
        select(TaskJob)
        .options(selectinload(TaskJob.question))
        .where(
            TaskJob.question_id == question.id,
            TaskJob.status.in_(["waiting_browser", "waiting_login", "waiting_verification"]),
        )
        .order_by(TaskJob.created_at.desc())
        .limit(1)
    )
    if task:
        job.task_id = task.id
        task.payload = {**(task.payload or {}), "collection_job_id": job.id}
        task.status = "queued"
        task.stage = "queued"
        task.worker_id = None
        task.error_message = None
        task.question.status = "queued"
        session.add(
            TaskLog(
                task_id=task.id,
                level="warning",
                stage="queued",
                message=f"已人工导入 {len(payload.answers)} 条回答，任务重新入队；此记录不代表实时自动采集成功",
                metadata_json={"collection_job_id": job.id, "source": "json_import"},
            )
        )
    await session.commit()
    if task:
        await broker.enqueue(task.id)
    return ImportAnswersResponse(
        question_id=question.id,
        collection_job_id=job.id,
        resumed_task_id=task.id if task else None,
        message=(
            "回答已作为人工 JSON 导入，关联任务已重新入队"
            if task
            else "回答已作为人工 JSON 导入"
        ),
        **counts,
    )


@router.get("/answers/{answer_id}", response_model=AnswerRead)
async def get_answer(
    answer_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> AnswerRead:
    answer = await session.get(Answer, answer_id)
    if not answer:
        raise HTTPException(status_code=404, detail="回答不存在")
    return await _answer_read(session, answer)


async def _set_included(
    session: AsyncSession, answer_id: str, *, included: bool
) -> AnswerRead:
    answer = await session.get(Answer, answer_id)
    if not answer:
        raise HTTPException(status_code=404, detail="回答不存在")
    answer.included_for_analysis = included
    answer.filter_reason = "" if included else "运营人员手动排除"
    analysis = await session.scalar(
        select(AnswerAnalysis).where(AnswerAnalysis.answer_id == answer.id)
    )
    if analysis:
        analysis.include = included
        analysis.reason = (
            "运营人员手动纳入" if included else "运营人员手动排除"
        )
    await session.commit()
    await session.refresh(answer)
    return await _answer_read(session, answer)


@router.post("/answers/{answer_id}/include", response_model=AnswerRead)
async def include_answer(
    answer_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> AnswerRead:
    return await _set_included(session, answer_id, included=True)


@router.post("/answers/{answer_id}/exclude", response_model=AnswerRead)
async def exclude_answer(
    answer_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> AnswerRead:
    return await _set_included(session, answer_id, included=False)
