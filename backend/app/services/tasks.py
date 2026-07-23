from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from backend.app.ai.providers.base import ProviderError
from backend.app.ai.providers.factory import create_structured_provider
from backend.app.ai.services.claim_extractor import ClaimExtractionService
from backend.app.core.config import Settings
from backend.app.core.state_machine import assert_task_transition
from backend.app.models.common import utc_now
from backend.app.models.core import (
    ArticleDraft,
    ArticleVersion,
    ModelUsageLog,
    Question,
    TaskJob,
    TaskLog,
)
from backend.app.services.queue import QueueBroker
from backend.app.services.settings import configured_settings_copy, provider_mode


logger = logging.getLogger(__name__)


async def add_task_log(
    session: AsyncSession,
    task: TaskJob,
    *,
    stage: str,
    message: str,
    level: str = "info",
    metadata: dict[str, object] | None = None,
) -> None:
    session.add(
        TaskLog(
            task_id=task.id,
            level=level,
            stage=stage,
            message=message,
            metadata_json=metadata or {},
        )
    )


async def publish_task_state(broker: QueueBroker, task: TaskJob) -> None:
    await broker.publish(
        {
            "type": "task_progress",
            "task_id": task.id,
            "question_id": task.question_id,
            "status": task.status,
            "stage": task.stage,
            "progress": task.progress,
            "error_message": task.error_message,
        }
    )


async def create_task(
    session: AsyncSession,
    broker: QueueBroker,
    question: Question,
    settings: Settings,
) -> TaskJob:
    active = await session.scalar(
        select(TaskJob).where(
            TaskJob.question_id == question.id,
            TaskJob.status.in_(["queued", "extracting_claims"]),
        )
    )
    if active:
        raise ValueError("该问题已经有正在执行的任务")

    task = TaskJob(
        question_id=question.id,
        status="queued",
        stage="queued",
        progress=0,
        max_retries=settings.task_max_retries,
        payload={"sample_answer_supplied": bool(question.sample_answer)},
    )
    question.status = "queued"
    session.add(task)
    await session.flush()
    await add_task_log(
        session, task, stage="queued", message="任务已创建，等待 Worker"
    )
    await session.commit()
    await session.refresh(task)
    try:
        await broker.enqueue(task.id)
    except Exception as exc:
        task.status = "failed"
        task.stage = "queued"
        task.error_message = f"队列不可用：{exc}"
        question.status = "candidate"
        await add_task_log(
            session,
            task,
            stage="queued",
            message=task.error_message,
            level="error",
        )
        await session.commit()
        raise RuntimeError(task.error_message) from exc
    return task


async def retry_task(
    session: AsyncSession, broker: QueueBroker, task: TaskJob
) -> TaskJob:
    if task.status not in {"failed", "cancelled"}:
        raise ValueError("只有失败或已取消任务可以重试")
    if task.retry_count >= task.max_retries:
        raise ValueError("该任务已达到最大重试次数")
    assert_task_transition(task.status, "queued")
    task.status = "queued"
    task.stage = "queued"
    task.progress = 0
    task.retry_count += 1
    task.error_message = None
    task.cancel_requested = False
    task.started_at = None
    task.completed_at = None
    task.question.status = "queued"
    await add_task_log(
        session,
        task,
        stage="queued",
        message=f"任务已重新入队，第 {task.retry_count} 次重试",
    )
    await session.commit()
    await broker.enqueue(task.id)
    return task


async def cancel_task(
    session: AsyncSession, broker: QueueBroker, task: TaskJob
) -> TaskJob:
    if task.status not in {"queued", "extracting_claims"}:
        raise ValueError("当前任务状态不能取消")
    task.cancel_requested = True
    if task.status == "queued":
        assert_task_transition(task.status, "cancelled")
        task.status = "cancelled"
        task.stage = "cancelled"
        task.completed_at = utc_now()
        task.question.status = "candidate"
        await add_task_log(
            session, task, stage="cancelled", message="任务已由用户取消"
        )
    else:
        await add_task_log(
            session,
            task,
            stage=task.stage,
            message="已收到取消请求，将在当前模型调用结束后停止",
            level="warning",
        )
    await session.commit()
    await publish_task_state(broker, task)
    return task


async def _load_task(
    session: AsyncSession, task_id: str, *, with_logs: bool = False
) -> TaskJob | None:
    options = [selectinload(TaskJob.question)]
    if with_logs:
        options.append(selectinload(TaskJob.logs))
    return await session.scalar(
        select(TaskJob).options(*options).where(TaskJob.id == task_id)
    )


async def _set_progress(
    session: AsyncSession,
    broker: QueueBroker,
    task: TaskJob,
    *,
    stage: str,
    progress: int,
    message: str,
) -> None:
    task.stage = stage
    task.progress = progress
    await add_task_log(session, task, stage=stage, message=message)
    await session.commit()
    await publish_task_state(broker, task)


def _build_minimal_draft(question: Question, analysis: dict[str, object]) -> str:
    claims = analysis.get("core_claims", [])
    reasons = analysis.get("supporting_reasons", [])
    claim_lines = "\n".join(f"- {item}" for item in claims)
    reason_lines = "\n".join(f"- {item}" for item in reasons) or "- 暂无额外理由"
    return (
        f"# {question.title}\n\n"
        f"## 一句话概览\n\n{analysis.get('summary', '')}\n\n"
        f"## 初步观点\n\n{claim_lines}\n\n"
        f"## 支持理由\n\n{reason_lines}\n\n"
        "> 第一阶段最小草稿：由结构化观点提取结果生成，必须人工审核；"
        "真实回答采集、观点聚类和正式文章生成将在第二阶段完成。"
    )


async def process_task(
    task_id: str,
    *,
    worker_id: str,
    settings: Settings,
    broker: QueueBroker,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        task = await _load_task(session, task_id)
        if not task or task.status != "queued":
            return
        if task.cancel_requested:
            await cancel_task(session, broker, task)
            return

        assert_task_transition(task.status, "extracting_claims")
        task.status = "extracting_claims"
        task.stage = "preparing_input"
        task.progress = 10
        task.worker_id = worker_id
        task.started_at = utc_now()
        task.question.status = "extracting_claims"
        await add_task_log(
            session,
            task,
            stage="preparing_input",
            message="Worker 已领取任务，正在准备结构化输入",
        )
        await session.commit()
        await publish_task_state(broker, task)

        try:
            mode = await provider_mode(session, settings)
            runtime_settings = await configured_settings_copy(session, settings)
            provider = create_structured_provider(mode, runtime_settings)
            service = ClaimExtractionService(provider)
            await _set_progress(
                session,
                broker,
                task,
                stage="extracting_claims",
                progress=35,
                message=f"正在使用 {mode} Provider 提取观点",
            )
            answer_text = (
                task.question.sample_answer
                or task.question.description
                or task.question.title
            )
            result = await service.extract(
                question_title=task.question.title,
                answer_text=answer_text,
            )

            await session.refresh(task)
            if task.cancel_requested:
                assert_task_transition(task.status, "cancelled")
                task.status = "cancelled"
                task.stage = "cancelled"
                task.completed_at = utc_now()
                task.question.status = "candidate"
                await add_task_log(
                    session,
                    task,
                    stage="cancelled",
                    message="模型调用结束后已按请求取消任务，结果未写入草稿",
                    level="warning",
                )
                await session.commit()
                await publish_task_state(broker, task)
                return

            await _set_progress(
                session,
                broker,
                task,
                stage="saving_result",
                progress=80,
                message="结构化输出校验通过，正在保存结果和版本",
            )
            analysis = result.data.model_dump()
            usage = result.usage
            session.add(
                ModelUsageLog(
                    question_id=task.question_id,
                    task_id=task.id,
                    provider=usage.provider,
                    model_role=usage.model_role,
                    model=usage.model,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    estimated_cost=usage.estimated_cost,
                    duration_ms=usage.duration_ms,
                    status="success",
                )
            )
            draft_content = _build_minimal_draft(task.question, analysis)
            draft = ArticleDraft(
                question_id=task.question_id,
                status="waiting_review",
                current_version=1,
                title=f"{task.question.title}｜第一阶段结构化草稿",
                content=draft_content,
                analysis_snapshot=analysis,
            )
            session.add(draft)
            await session.flush()
            session.add(
                ArticleVersion(
                    draft_id=draft.id,
                    version=1,
                    title=draft.title,
                    content=draft.content,
                    source_task_id=task.id,
                )
            )
            assert_task_transition(task.status, "waiting_review")
            task.status = "waiting_review"
            task.stage = "waiting_review"
            task.progress = 100
            task.result = {
                "analysis": analysis,
                "draft_id": draft.id,
                "provider": usage.provider,
                "model": usage.model,
            }
            task.completed_at = utc_now()
            task.question.status = "waiting_review"
            await add_task_log(
                session,
                task,
                stage="waiting_review",
                message="观点提取完成，最小草稿已进入人工审核",
            )
            await session.commit()
            await publish_task_state(broker, task)
        except Exception as exc:
            logger.exception("任务 %s 执行失败", task_id)
            await session.rollback()
            task = await _load_task(session, task_id)
            if not task:
                return
            task.status = "failed"
            task.stage = "failed"
            task.error_message = str(exc)
            task.completed_at = utc_now()
            task.question.status = "candidate"
            await add_task_log(
                session,
                task,
                stage="failed",
                message=f"任务失败：{exc}",
                level="error",
            )
            await session.commit()
            await publish_task_state(broker, task)

