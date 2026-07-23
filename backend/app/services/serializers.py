from __future__ import annotations

from backend.app.models.core import ArticleDraft, TaskJob
from backend.app.schemas.draft import DraftRead
from backend.app.schemas.task import TaskLogRead, TaskRead


def task_to_read(task: TaskJob, *, include_logs: bool = False) -> TaskRead:
    return TaskRead(
        id=task.id,
        question_id=task.question_id,
        question_title=task.question.title if task.question else "",
        task_type=task.task_type,
        status=task.status,
        stage=task.stage,
        progress=task.progress,
        worker_id=task.worker_id,
        retry_count=task.retry_count,
        max_retries=task.max_retries,
        result=task.result or {},
        error_message=task.error_message,
        cancel_requested=task.cancel_requested,
        started_at=task.started_at,
        completed_at=task.completed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
        logs=[
            TaskLogRead.model_validate(log)
            for log in sorted(task.logs, key=lambda item: item.created_at)
        ]
        if include_logs
        else [],
    )


def draft_to_read(draft: ArticleDraft) -> DraftRead:
    return DraftRead(
        id=draft.id,
        question_id=draft.question_id,
        question_title=draft.question.title if draft.question else "",
        status=draft.status,
        current_version=draft.current_version,
        title=draft.title,
        content=draft.content,
        analysis_snapshot=draft.analysis_snapshot,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )

