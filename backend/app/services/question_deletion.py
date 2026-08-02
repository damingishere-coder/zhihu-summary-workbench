from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import REPOSITORY_ROOT
from backend.app.models.content import (
    Answer,
    AnswerAnalysis,
    AnswerVersion,
    ArticleParagraphSource,
    Claim,
    ClaimCluster,
    ClaimEmbedding,
    ClusterAnswerLink,
    OpinionMap,
    QuestionScore,
)
from backend.app.models.core import (
    ArticleDraft,
    ArticleVersion,
    AuditLog,
    ModelUsageLog,
    Question,
    QuestionSource,
    TaskJob,
    TaskLog,
)
from backend.app.models.media import (
    ImageDraft,
    ImageVersion,
    PublishRecord,
    PublishSchedule,
)


logger = logging.getLogger(__name__)

TERMINAL_TASK_STATUSES = {
    "waiting_review",
    "review_approved",
    "failed",
    "cancelled",
    "waiting_login",
    "waiting_verification",
}


async def _ids(
    session: AsyncSession,
    model: type,
    condition,
) -> list[str]:
    return list((await session.scalars(select(model.id).where(condition))).all())


async def _delete_ids(
    session: AsyncSession,
    model: type,
    ids: list[str],
) -> None:
    if ids:
        await session.execute(delete(model).where(model.id.in_(ids)))


def _controlled_file_paths(raw_paths: set[str]) -> list[Path]:
    data_root = (REPOSITORY_ROOT / "data").resolve()
    paths: list[Path] = []
    for raw_path in raw_paths:
        if not raw_path:
            continue
        try:
            path = Path(raw_path).expanduser().resolve()
        except (OSError, RuntimeError):
            logger.warning("忽略无法解析的关联文件路径：%s", raw_path)
            continue
        if path != data_root and data_root in path.parents:
            paths.append(path)
        else:
            logger.warning("拒绝删除 data 目录外的关联文件：%s", path)
    return paths


def _remove_files(paths: list[Path]) -> None:
    data_root = (REPOSITORY_ROOT / "data").resolve()
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.exception("问题已从数据库删除，但关联文件清理失败：%s", path)
            continue
        parent = path.parent
        while parent != data_root and data_root in parent.parents:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent


async def permanently_delete_question(
    session: AsyncSession,
    question: Question,
) -> None:
    active_task = await session.scalar(
        select(TaskJob.id).where(
            TaskJob.question_id == question.id,
            TaskJob.status.not_in(TERMINAL_TASK_STATUSES),
        )
    )
    if active_task:
        raise ValueError("该问题仍有排队或运行中的任务，请先取消任务并等待停止后再删除")

    task_ids = await _ids(
        session, TaskJob, TaskJob.question_id == question.id
    )
    draft_ids = await _ids(
        session, ArticleDraft, ArticleDraft.question_id == question.id
    )
    article_version_ids = (
        await _ids(
            session,
            ArticleVersion,
            ArticleVersion.draft_id.in_(draft_ids),
        )
        if draft_ids
        else []
    )
    image_draft_ids = (
        await _ids(
            session,
            ImageDraft,
            ImageDraft.article_draft_id.in_(draft_ids),
        )
        if draft_ids
        else []
    )
    image_versions = (
        (
            await session.scalars(
                select(ImageVersion).where(
                    ImageVersion.image_draft_id.in_(image_draft_ids)
                )
            )
        ).all()
        if image_draft_ids
        else []
    )
    image_version_ids = [item.id for item in image_versions]

    schedule_conditions = []
    if draft_ids:
        schedule_conditions.append(PublishSchedule.article_draft_id.in_(draft_ids))
    if article_version_ids:
        schedule_conditions.append(
            PublishSchedule.article_version_id.in_(article_version_ids)
        )
    if image_version_ids:
        schedule_conditions.append(
            PublishSchedule.image_version_id.in_(image_version_ids)
        )
    schedule_ids = (
        await _ids(session, PublishSchedule, or_(*schedule_conditions))
        if schedule_conditions
        else []
    )

    record_conditions = []
    if schedule_ids:
        record_conditions.append(PublishRecord.schedule_id.in_(schedule_ids))
    if article_version_ids:
        record_conditions.append(
            PublishRecord.article_version_id.in_(article_version_ids)
        )
    if image_version_ids:
        record_conditions.append(
            PublishRecord.image_version_id.in_(image_version_ids)
        )
    publish_records = (
        (
            await session.scalars(
                select(PublishRecord).where(or_(*record_conditions))
            )
        ).all()
        if record_conditions
        else []
    )
    publish_record_ids = [item.id for item in publish_records]

    answer_ids = await _ids(
        session, Answer, Answer.question_id == question.id
    )
    claim_ids = await _ids(
        session, Claim, Claim.question_id == question.id
    )
    cluster_ids = await _ids(
        session, ClaimCluster, ClaimCluster.question_id == question.id
    )

    raw_paths = {
        value
        for item in image_versions
        for value in (
            item.background_path,
            item.thumbnail_path,
            item.rendered_path,
            item.html_snapshot_path,
        )
        if value
    }
    raw_paths.update(
        item.screenshot_path for item in publish_records if item.screenshot_path
    )
    controlled_paths = _controlled_file_paths(raw_paths)

    entity_ids = {
        question.id,
        *task_ids,
        *draft_ids,
        *article_version_ids,
        *image_draft_ids,
        *image_version_ids,
        *schedule_ids,
        *publish_record_ids,
        *answer_ids,
        *claim_ids,
        *cluster_ids,
    }

    try:
        await _delete_ids(session, PublishRecord, publish_record_ids)
        await _delete_ids(session, PublishSchedule, schedule_ids)
        if article_version_ids:
            await session.execute(
                delete(ArticleParagraphSource).where(
                    ArticleParagraphSource.article_version_id.in_(
                        article_version_ids
                    )
                )
            )
        await _delete_ids(session, ImageVersion, image_version_ids)
        await _delete_ids(session, ImageDraft, image_draft_ids)
        await _delete_ids(session, ArticleVersion, article_version_ids)
        await _delete_ids(session, ArticleDraft, draft_ids)

        if claim_ids:
            await session.execute(
                delete(ClaimEmbedding).where(
                    ClaimEmbedding.claim_id.in_(claim_ids)
                )
            )
        if cluster_ids or answer_ids:
            link_conditions = []
            if cluster_ids:
                link_conditions.append(
                    ClusterAnswerLink.cluster_id.in_(cluster_ids)
                )
            if answer_ids:
                link_conditions.append(
                    ClusterAnswerLink.answer_id.in_(answer_ids)
                )
            await session.execute(
                delete(ClusterAnswerLink).where(or_(*link_conditions))
            )
        if answer_ids:
            await session.execute(
                delete(AnswerAnalysis).where(
                    AnswerAnalysis.answer_id.in_(answer_ids)
                )
            )
            await session.execute(
                delete(AnswerVersion).where(
                    AnswerVersion.answer_id.in_(answer_ids)
                )
            )
        await _delete_ids(session, Claim, claim_ids)
        await _delete_ids(session, ClaimCluster, cluster_ids)
        await session.execute(
            delete(OpinionMap).where(OpinionMap.question_id == question.id)
        )
        await _delete_ids(session, Answer, answer_ids)
        await session.execute(
            delete(QuestionScore).where(QuestionScore.question_id == question.id)
        )

        if task_ids:
            await session.execute(
                delete(ModelUsageLog).where(
                    or_(
                        ModelUsageLog.question_id == question.id,
                        ModelUsageLog.task_id.in_(task_ids),
                    )
                )
            )
            await session.execute(
                delete(TaskLog).where(TaskLog.task_id.in_(task_ids))
            )
        else:
            await session.execute(
                delete(ModelUsageLog).where(
                    ModelUsageLog.question_id == question.id
                )
            )
        await _delete_ids(session, TaskJob, task_ids)
        await session.execute(
            delete(QuestionSource).where(
                QuestionSource.question_id == question.id
            )
        )
        if entity_ids:
            await session.execute(
                delete(AuditLog).where(AuditLog.entity_id.in_(entity_ids))
            )
        await session.execute(
            delete(Question).where(Question.id == question.id)
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    _remove_files(controlled_paths)
