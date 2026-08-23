from __future__ import annotations

import logging

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from backend.app.collectors.zhihu import (
    ZhihuAuthenticationRequired,
    ZhihuCollector,
    ZhihuVerificationRequired,
)
from backend.app.core.config import Settings
from backend.app.core.state_machine import assert_task_transition
from backend.app.models.common import utc_now
from backend.app.models.core import Question, TaskJob, TaskLog
from backend.app.models.browser_bridge import CollectionJob
from backend.app.schemas.browser_bridge import ImportBundleV1
from backend.app.schemas.analysis import FetchAnswersRequest
from backend.app.services.content_pipeline import (
    evaluate_answers,
    extract_claims,
    fetch_and_store_answers,
    generate_article,
    generate_embeddings,
    generate_opinion_map,
    refine_clusters,
    review_article,
    usage_summary,
)
from backend.app.services.queue import QueueBroker
from backend.app.services.browser_bridge import (
    bridge_manager,
    bundle_to_fetch_result,
    create_collection_job,
)


logger = logging.getLogger(__name__)

LOGIN_WAITING_STATUS = "waiting_login"
VERIFICATION_WAITING_STATUS = "waiting_verification"
ALREADY_RESUMED_STATUSES = {
    "queued",
    "fetching_question",
    "fetching_answers",
    "cleaning_answers",
    "evaluating_answers",
    "extracting_claims",
    "generating_embeddings",
    "clustering_claims",
    "refining_clusters",
    "generating_opinion_map",
    "generating_article",
    "reviewing_article",
    "waiting_review",
    "review_approved",
}


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
            TaskJob.status.not_in(
                ["waiting_review", "review_approved", "failed", "cancelled"]
            ),
        )
    )
    if active:
        raise ValueError("该问题已经有正在执行的任务")

    task = TaskJob(
        question_id=question.id,
        task_type="question_content_pipeline",
        status="queued",
        stage="queued",
        progress=0,
        max_retries=settings.task_max_retries,
        payload={
            "fetch_mode": "representative",
            "collector_mode": "auto",
            "max_answers": settings.max_answers_per_question,
        },
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


async def resume_task_after_login(
    session: AsyncSession,
    broker: QueueBroker,
    task: TaskJob,
) -> TaskJob:
    return await _resume_waiting_task(
        session,
        broker,
        task,
        waiting_status=LOGIN_WAITING_STATUS,
        invalid_status_message="只有等待知乎登录的任务可以通过登录恢复",
    )


async def resume_task_after_verification(
    session: AsyncSession,
    broker: QueueBroker,
    task: TaskJob,
) -> TaskJob:
    return await _resume_waiting_task(
        session,
        broker,
        task,
        waiting_status=VERIFICATION_WAITING_STATUS,
        invalid_status_message="只有等待人工验证的任务可以通过验证确认恢复",
    )


async def retry_collection_task(
    session: AsyncSession,
    broker: QueueBroker,
    task: TaskJob,
) -> tuple[CollectionJob, bool]:
    allowed = {
        "waiting_browser",
        "waiting_login",
        "waiting_verification",
        "failed",
        "cancelled",
    }
    if task.status not in allowed:
        raise ValueError("只有等待浏览器、登录、验证或已停止的任务可以重新采集")
    existing_job_id = str((task.payload or {}).get("collection_job_id") or "")
    existing_job = (
        await session.get(CollectionJob, existing_job_id)
        if existing_job_id
        else None
    )
    if existing_job and existing_job.status == "completed":
        task.status = "queued"
        task.stage = "queued"
        task.worker_id = None
        task.error_message = None
        task.question.status = "queued"
        await add_task_log(
            session,
            task,
            stage="queued",
            message="已使用安全保存的采集结果恢复任务，无需重复采集",
            metadata={"collection_job_id": existing_job.id},
        )
        await session.commit()
        try:
            await broker.enqueue(task.id)
        except Exception as exc:
            task.status = "waiting_browser"
            task.stage = "waiting_browser"
            task.error_message = "采集结果已保存，但任务队列仍不可用"
            task.question.status = "waiting_browser"
            await session.commit()
            raise ValueError(task.error_message) from exc
        return existing_job, False
    mode = str((task.payload or {}).get("fetch_mode", "representative"))
    max_answers = min(20, int((task.payload or {}).get("max_answers", 20)))
    job = await create_collection_job(
        session,
        task,
        mode=mode,
        max_answers=max_answers,
    )
    dispatched_client_id = await bridge_manager.dispatch_job(job)
    dispatched = bool(dispatched_client_id)
    if dispatched_client_id:
        job.status = "dispatched"
        job.client_id = dispatched_client_id
        job.dispatched_at = utc_now()
        await session.commit()
    await publish_task_state(broker, task)
    return job, dispatched


async def _resume_waiting_task(
    session: AsyncSession,
    broker: QueueBroker,
    task: TaskJob,
    *,
    waiting_status: str,
    invalid_status_message: str,
) -> TaskJob:
    if task.status in ALREADY_RESUMED_STATUSES:
        return task
    if task.status != waiting_status:
        raise ValueError(invalid_status_message)
    await retry_collection_task(session, broker, task)
    return task


async def cancel_task(
    session: AsyncSession, broker: QueueBroker, task: TaskJob
) -> TaskJob:
    if task.status in {"waiting_review", "review_approved", "failed", "cancelled"}:
        raise ValueError("当前任务状态不能取消")
    task.cancel_requested = True
    if task.status in {"queued", "waiting_browser", "waiting_login", "waiting_verification"}:
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


async def _stop_if_cancelled(
    session: AsyncSession,
    broker: QueueBroker,
    task: TaskJob,
) -> bool:
    await session.refresh(task)
    if not task.cancel_requested:
        return False
    assert_task_transition(task.status, "cancelled")
    task.status = "cancelled"
    task.stage = "cancelled"
    task.completed_at = utc_now()
    task.question.status = "candidate"
    await add_task_log(
        session,
        task,
        stage="cancelled",
        message="已按用户请求在当前阶段结束后停止，已有数据和历史版本已保留",
        level="warning",
    )
    await session.commit()
    await publish_task_state(broker, task)
    return True


async def process_task(
    task_id: str,
    *,
    worker_id: str,
    settings: Settings,
    broker: QueueBroker,
    session_factory: async_sessionmaker[AsyncSession],
    collector: ZhihuCollector | None = None,
) -> None:
    async with session_factory() as session:
        task = await _load_task(session, task_id)
        if not task or task.status != "queued":
            return
        if task.cancel_requested:
            await cancel_task(session, broker, task)
            return

        assert_task_transition(task.status, "fetching_question")
        task.status = "fetching_question"
        task.stage = "fetching_question"
        task.progress = 5
        task.worker_id = worker_id
        task.started_at = utc_now()
        task.question.status = "fetching_question"
        await add_task_log(
            session,
            task,
            stage="fetching_question",
            message="Worker 已领取任务，开始读取知乎问题信息",
        )
        await session.commit()
        await publish_task_state(broker, task)

        try:
            await _set_progress(
                session,
                broker,
                task,
                stage="fetching_answers",
                progress=10,
                message="正在分页采集回答；登录或验证码阻断时会安全暂停",
            )
            assert_task_transition(task.status, "fetching_answers")
            task.status = "fetching_answers"
            task.question.status = "fetching_answers"
            await session.commit()
            precollected = None
            if collector is None:
                collection_job_id = str((task.payload or {}).get("collection_job_id") or "")
                collection_job = (
                    await session.get(CollectionJob, collection_job_id)
                    if collection_job_id
                    else None
                )
                if collection_job is None or collection_job.status != "completed":
                    collection_job = await create_collection_job(
                        session,
                        task,
                        mode=str(task.payload.get("fetch_mode", "representative")),
                        max_answers=min(
                            20,
                            int(task.payload.get("max_answers", settings.max_answers_per_question)),
                        ),
                    )
                    dispatched_client_id = await bridge_manager.dispatch_job(collection_job)
                    if dispatched_client_id:
                        collection_job.status = "dispatched"
                        collection_job.client_id = dispatched_client_id
                        collection_job.dispatched_at = utc_now()
                        await session.commit()
                    await publish_task_state(broker, task)
                    return
                try:
                    bundle = ImportBundleV1.model_validate(collection_job.result_json)
                except ValidationError as exc:
                    raise ValueError("已保存的扩展采集结果格式无效") from exc
                precollected = bundle_to_fetch_result(
                    bundle,
                    collector_mode=(
                        "chrome_extension"
                        if collection_job.source == "extension"
                        else "json_import"
                    ),
                )
            fetch_result, fetch_counts = await fetch_and_store_answers(
                session,
                task.question,
                settings,
                FetchAnswersRequest(
                    mode=str(task.payload.get("fetch_mode", "representative")),
                    collector_mode=str(
                        task.payload.get("collector_mode", "auto")
                    ),
                    max_answers=int(
                        task.payload.get(
                            "max_answers", settings.max_answers_per_question
                        )
                    ),
                ),
                collector=collector,
                precollected=precollected,
            )
            if fetch_counts["included"] < 1:
                raise ValueError("没有采集到可分析的有效回答")
            assert_task_transition(task.status, "cleaning_answers")
            task.status = "cleaning_answers"
            task.question.status = "cleaning_answers"
            await _set_progress(
                session,
                broker,
                task,
                stage="cleaning_answers",
                progress=20,
                message=(
                    f"采集 {fetch_counts['fetched']} 条回答，"
                    f"基础过滤后 {fetch_counts['included']} 条可分析"
                ),
            )

            if await _stop_if_cancelled(session, broker, task):
                return

            assert_task_transition(task.status, "evaluating_answers")
            task.status = "evaluating_answers"
            task.question.status = "evaluating_answers"
            await _set_progress(
                session,
                broker,
                task,
                stage="evaluating_answers",
                progress=30,
                message="正在批量筛选回答质量和相关性",
            )
            quality_counts = await evaluate_answers(
                session, task.question, settings, task=task
            )
            if quality_counts["included"] < 1:
                raise ValueError("质量筛选后没有可分析回答")
            if await _stop_if_cancelled(session, broker, task):
                return

            assert_task_transition(task.status, "extracting_claims")
            task.status = "extracting_claims"
            task.question.status = "extracting_claims"
            await _set_progress(
                session,
                broker,
                task,
                stage="extracting_claims",
                progress=42,
                message="正在分批提取每条回答的观点和适用条件",
            )
            claim_counts = await extract_claims(
                session, task.question, settings, task=task
            )
            if await _stop_if_cancelled(session, broker, task):
                return

            assert_task_transition(task.status, "generating_embeddings")
            task.status = "generating_embeddings"
            task.question.status = "generating_embeddings"
            await _set_progress(
                session,
                broker,
                task,
                stage="generating_embeddings",
                progress=55,
                message="正在生成观点 Embedding，未变化观点复用缓存",
            )
            embedding_counts = await generate_embeddings(
                session, task.question, settings
            )
            if await _stop_if_cancelled(session, broker, task):
                return

            assert_task_transition(task.status, "clustering_claims")
            task.status = "clustering_claims"
            task.question.status = "clustering_claims"
            await _set_progress(
                session,
                broker,
                task,
                stage="clustering_claims",
                progress=64,
                message="正在进行余弦相似度粗聚类",
            )
            assert_task_transition(task.status, "refining_clusters")
            task.status = "refining_clusters"
            task.question.status = "refining_clusters"
            await _set_progress(
                session,
                broker,
                task,
                stage="refining_clusters",
                progress=70,
                message="正在修正观点簇并识别共识、分歧和少数派",
            )
            cluster_counts = await refine_clusters(
                session, task.question, settings, task=task
            )
            if await _stop_if_cancelled(session, broker, task):
                return

            assert_task_transition(task.status, "generating_opinion_map")
            task.status = "generating_opinion_map"
            task.question.status = "generating_opinion_map"
            await _set_progress(
                session,
                broker,
                task,
                stage="generating_opinion_map",
                progress=78,
                message="正在生成可追溯的观点地图",
            )
            opinion = await generate_opinion_map(
                session, task.question, settings, task=task
            )
            if await _stop_if_cancelled(session, broker, task):
                return

            assert_task_transition(task.status, "generating_article")
            task.status = "generating_article"
            task.question.status = "generating_article"
            await _set_progress(
                session,
                broker,
                task,
                stage="generating_article",
                progress=86,
                message="正在生成总结文章和段落来源映射",
            )
            draft, article = await generate_article(
                session, task.question, settings, task=task
            )
            if await _stop_if_cancelled(session, broker, task):
                return

            assert_task_transition(task.status, "reviewing_article")
            task.status = "reviewing_article"
            task.question.status = "reviewing_article"
            await _set_progress(
                session,
                broker,
                task,
                stage="reviewing_article",
                progress=94,
                message="正在执行独立质量审核",
            )
            review = await review_article(
                session, task.question, draft, settings, task=task
            )

            assert_task_transition(task.status, "waiting_review")
            task.status = "waiting_review"
            task.stage = "waiting_review"
            task.progress = 100
            task.result = {
                "draft_id": draft.id,
                "fetch": fetch_counts,
                "collector_mode": fetch_result.collector_mode,
                "warnings": fetch_result.warnings,
                "quality": quality_counts,
                "claims": claim_counts,
                "embeddings": embedding_counts,
                "clusters": cluster_counts,
                "opinion_map_version": opinion.version,
                "article_characters": len(article.content),
                "review": review.model_dump(),
                "usage": await usage_summary(session, task.question_id),
            }
            task.completed_at = utc_now()
            task.question.status = "waiting_review"
            await add_task_log(
                session,
                task,
                stage="waiting_review",
                message="第二阶段内容流水线完成，文章和图片 Prompt 工作区已进入草稿审核",
            )
            await session.commit()
            await publish_task_state(broker, task)
        except (ZhihuAuthenticationRequired, ZhihuVerificationRequired) as exc:
            await session.rollback()
            task = await _load_task(session, task_id)
            if not task:
                return
            target = (
                "waiting_login"
                if isinstance(exc, ZhihuAuthenticationRequired)
                else "waiting_verification"
            )
            assert_task_transition(task.status, target)
            task.status = target
            task.stage = target
            task.error_message = str(exc)
            task.completed_at = None
            task.worker_id = None
            task.question.status = target
            await add_task_log(
                session,
                task,
                stage=target,
                message=(
                    f"任务等待用户操作：{exc}"
                    if target == "waiting_login"
                    else f"任务等待人工验证：{exc}"
                ),
                level="warning",
                metadata=getattr(exc, "details", None),
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
