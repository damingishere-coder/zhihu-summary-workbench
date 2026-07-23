from __future__ import annotations

import hashlib
import re

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.core import AuditLog, Question, QuestionSource
from backend.app.schemas.question import (
    QuestionCreate,
    QuestionImportItem,
    QuestionImportRequest,
    QuestionImportResponse,
    QuestionUpdate,
    ZHIHU_QUESTION_URL,
)


def extract_external_id(url: str) -> str | None:
    match = ZHIHU_QUESTION_URL.match(url)
    return match.group("id") if match else None


def question_hash(title: str, url: str, description: str) -> str:
    value = f"{title.strip()}|{url.strip()}|{description.strip()}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()


async def create_question(
    session: AsyncSession,
    payload: QuestionCreate,
    *,
    source: str = "manual",
) -> Question:
    external_id = extract_external_id(payload.url)
    title = payload.title.strip() or f"知乎问题 {external_id}"
    question = Question(
        external_id=external_id,
        title=title,
        url=payload.url,
        description=payload.description.strip(),
        sample_answer=payload.sample_answer.strip(),
        source=source,
        priority=payload.priority,
        status="candidate",
        content_hash=question_hash(title, payload.url, payload.description),
    )
    session.add(question)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError("该知乎问题已经在问题池中") from exc
    session.add(
        QuestionSource(
            question_id=question.id,
            source_type=source,
            source_url=payload.url,
            raw_data={"created_by": "manual_api"},
        )
    )
    session.add(
        AuditLog(
            actor="operator",
            action="question.created",
            entity_type="question",
            entity_id=question.id,
            after_data={"url": question.url, "source": source},
        )
    )
    await session.commit()
    await session.refresh(question)
    return question


async def import_questions(
    session: AsyncSession, payload: QuestionImportRequest
) -> QuestionImportResponse:
    results: list[QuestionImportItem] = []
    for url in payload.urls:
        existing = await session.scalar(select(Question).where(Question.url == url))
        if existing:
            results.append(
                QuestionImportItem(
                    url=url,
                    status="duplicate",
                    question_id=existing.id,
                    message="问题已存在",
                )
            )
            continue
        try:
            question = await create_question(
                session,
                QuestionCreate(url=url, priority=payload.priority),
                source="import",
            )
            results.append(
                QuestionImportItem(
                    url=url,
                    status="created",
                    question_id=question.id,
                    message="已导入",
                )
            )
        except ValueError as exc:
            results.append(
                QuestionImportItem(url=url, status="failed", message=str(exc))
            )
    return QuestionImportResponse(
        items=results,
        created=sum(item.status == "created" for item in results),
        duplicate=sum(item.status == "duplicate" for item in results),
        failed=sum(item.status == "failed" for item in results),
    )


async def update_question(
    session: AsyncSession, question: Question, payload: QuestionUpdate
) -> Question:
    before = {
        "title": question.title,
        "status": question.status,
        "priority": question.priority,
    }
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(question, key, value)
    question.content_hash = question_hash(
        question.title, question.url, question.description
    )
    session.add(
        AuditLog(
            actor="operator",
            action="question.updated",
            entity_type="question",
            entity_id=question.id,
            before_data=before,
            after_data=payload.model_dump(exclude_none=True),
        )
    )
    await session.commit()
    await session.refresh(question)
    return question

