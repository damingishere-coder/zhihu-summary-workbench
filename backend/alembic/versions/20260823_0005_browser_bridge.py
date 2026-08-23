"""新增 Chrome 扩展桥接客户端和采集任务。

Revision ID: 20260823_0005
Revises: 20260726_0004
Create Date: 2026-08-23
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260823_0005"
down_revision: str | None = "20260726_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())
    if "browser_bridge_clients" not in existing_tables:
        op.create_table(
        "browser_bridge_clients",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("extension_version", sa.String(length=64), nullable=False),
        sa.Column("zhihu_auth", sa.String(length=32), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
        )
        op.create_index("ix_browser_bridge_clients_token_hash", "browser_bridge_clients", ["token_hash"])
        op.create_index("ix_browser_bridge_clients_status", "browser_bridge_clients", ["status"])
        op.create_index(
            "ix_browser_bridge_clients_zhihu_auth", "browser_bridge_clients", ["zhihu_auth"]
        )
        op.create_index(
            "ix_browser_bridge_clients_status_seen",
            "browser_bridge_clients",
            ["status", "last_seen_at"],
        )

    if "collection_jobs" not in existing_tables:
        op.create_table(
        "collection_jobs",
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("question_id", sa.String(length=36), nullable=False),
        sa.Column("client_id", sa.String(length=36), nullable=True),
        sa.Column("nonce", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("max_answers", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["browser_bridge_clients.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["task_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nonce"),
        )
        op.create_index("ix_collection_jobs_task_id", "collection_jobs", ["task_id"])
        op.create_index("ix_collection_jobs_question_id", "collection_jobs", ["question_id"])
        op.create_index("ix_collection_jobs_client_id", "collection_jobs", ["client_id"])
        op.create_index("ix_collection_jobs_nonce", "collection_jobs", ["nonce"])
        op.create_index("ix_collection_jobs_status", "collection_jobs", ["status"])
        op.create_index(
            "ix_collection_jobs_status_created", "collection_jobs", ["status", "created_at"]
        )
        op.create_index(
            "ix_collection_jobs_task_created", "collection_jobs", ["task_id", "created_at"]
        )


def downgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "collection_jobs" in existing_tables:
        op.drop_table("collection_jobs")
    if "browser_bridge_clients" in existing_tables:
        op.drop_table("browser_bridge_clients")
