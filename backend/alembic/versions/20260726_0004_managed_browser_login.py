"""将旧浏览器目录失败任务迁移为等待扫码登录。

Revision ID: 20260726_0004
Revises: 20260724_0003
Create Date: 2026-07-26
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260726_0004"
down_revision: str | None = "20260724_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_ERROR_PATTERN = "%未配置知乎本地浏览器目录%"


def upgrade() -> None:
    connection = op.get_bind()
    task_jobs = sa.table(
        "task_jobs",
        sa.column("id", sa.String()),
        sa.column("question_id", sa.String()),
        sa.column("status", sa.String()),
        sa.column("stage", sa.String()),
        sa.column("error_message", sa.Text()),
        sa.column("completed_at", sa.DateTime(timezone=True)),
    )
    questions = sa.table(
        "questions",
        sa.column("id", sa.String()),
        sa.column("status", sa.String()),
    )
    affected_questions = sa.select(task_jobs.c.question_id).where(
        task_jobs.c.status == "failed",
        task_jobs.c.error_message.like(LEGACY_ERROR_PATTERN),
    )
    connection.execute(
        questions.update()
        .where(questions.c.id.in_(affected_questions))
        .values(status="waiting_login")
    )
    connection.execute(
        task_jobs.update()
        .where(
            task_jobs.c.status == "failed",
            task_jobs.c.error_message.like(LEGACY_ERROR_PATTERN),
        )
        .values(
            status="waiting_login",
            stage="waiting_login",
            completed_at=None,
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    task_jobs = sa.table(
        "task_jobs",
        sa.column("question_id", sa.String()),
        sa.column("status", sa.String()),
        sa.column("stage", sa.String()),
        sa.column("error_message", sa.Text()),
    )
    questions = sa.table(
        "questions",
        sa.column("id", sa.String()),
        sa.column("status", sa.String()),
    )
    affected_questions = sa.select(task_jobs.c.question_id).where(
        task_jobs.c.status == "waiting_login",
        task_jobs.c.error_message.like(LEGACY_ERROR_PATTERN),
    )
    connection.execute(
        questions.update()
        .where(questions.c.id.in_(affected_questions))
        .values(status="candidate")
    )
    connection.execute(
        task_jobs.update()
        .where(
            task_jobs.c.status == "waiting_login",
            task_jobs.c.error_message.like(LEGACY_ERROR_PATTERN),
        )
        .values(status="failed", stage="failed")
    )
