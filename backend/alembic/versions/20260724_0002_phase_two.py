"""补齐第二阶段采集、分析、审核和手动图片工作流字段。

Revision ID: 20260724_0002
Revises: 20260723_0001
Create Date: 2026-07-24
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260724_0002"
down_revision: str | None = "20260723_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_names(table_name: str) -> set[str]:
    return {
        item["name"] for item in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _add_missing_columns(
    table_name: str, columns: list[sa.Column]
) -> None:
    existing = _column_names(table_name)
    missing = [column for column in columns if column.name not in existing]
    if not missing:
        return
    with op.batch_alter_table(table_name) as batch:
        for column in missing:
            batch.add_column(column)


def upgrade() -> None:
    _add_missing_columns(
        "questions",
        [
            sa.Column("hot_rank", sa.Integer(), nullable=True),
            sa.Column("hot_score", sa.String(100), nullable=False, server_default="")
            ,
            sa.Column(
                "answer_count", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "follower_count", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column("fetched_at", sa.DateTime(timezone=True)),
        ],
    )

    _add_missing_columns(
        "answers",
        [
            sa.Column(
                "author_url", sa.String(1000), nullable=False, server_default=""
            ),
            sa.Column("published_at", sa.DateTime(timezone=True)),
            sa.Column("external_updated_at", sa.DateTime(timezone=True)),
            sa.Column(
                "sort_order", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "media_json", sa.JSON(), nullable=False, server_default="{}"
            ),
            sa.Column(
                "fetch_batch", sa.String(64), nullable=False, server_default=""
            ),
        ],
    )
    answer_indexes = {
        item["name"] for item in sa.inspect(op.get_bind()).get_indexes("answers")
    }
    if "ix_answers_fetch_batch" not in answer_indexes:
        with op.batch_alter_table("answers") as batch:
            batch.create_index("ix_answers_fetch_batch", ["fetch_batch"])

    _add_missing_columns(
        "answer_analysis",
        [
            sa.Column(
                "information_density",
                sa.Float(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "include", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
            sa.Column(
                "reason", sa.String(500), nullable=False, server_default=""
            ),
        ],
    )

    _add_missing_columns(
        "claim_clusters",
        [
            sa.Column(
                "support_count", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "opposing_reasons", sa.JSON(), nullable=False, server_default="[]"
            ),
            sa.Column(
                "applicable_conditions", sa.JSON(), nullable=False, server_default="[]"
            ),
            sa.Column(
                "is_mainstream", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column(
                "is_minority", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
            sa.Column(
                "is_controversial",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "information_gain", sa.Float(), nullable=False, server_default="0"
            ),
        ],
    )
    if "opinion_maps" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "opinion_maps",
            sa.Column("question_id", sa.String(36), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("content_json", sa.JSON(), nullable=False),
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["question_id"], ["questions.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("question_id", "version"),
        )
        op.create_index(
            "ix_opinion_maps_question_id", "opinion_maps", ["question_id"]
        )

    _add_missing_columns(
        "article_drafts",
        [
            sa.Column(
                "review_result", sa.JSON(), nullable=False, server_default="{}"
            ),
            sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        ],
    )

    _add_missing_columns(
        "image_drafts",
        [
            sa.Column(
                "use_css_background",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        ],
    )

    _add_missing_columns(
        "image_versions",
        [
            sa.Column(
                "workflow_mode",
                sa.String(64),
                nullable=False,
                server_default="copy_prompt_and_upload",
            ),
            sa.Column(
                "copy_state", sa.JSON(), nullable=False, server_default="{}"
            ),
            sa.Column("uploaded_name", sa.String(500)),
            sa.Column("content_type", sa.String(128)),
            sa.Column("byte_size", sa.Integer(), nullable=False, server_default="0")
            ,
            sa.Column(
                "background_deleted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        ],
    )


def downgrade() -> None:
    with op.batch_alter_table("image_versions") as batch:
        batch.drop_column("background_deleted")
        batch.drop_column("byte_size")
        batch.drop_column("content_type")
        batch.drop_column("uploaded_name")
        batch.drop_column("copy_state")
        batch.drop_column("workflow_mode")
    with op.batch_alter_table("image_drafts") as batch:
        batch.drop_column("use_css_background")
    with op.batch_alter_table("article_drafts") as batch:
        batch.drop_column("reviewed_at")
        batch.drop_column("review_result")
    op.drop_index("ix_opinion_maps_question_id", table_name="opinion_maps")
    op.drop_table("opinion_maps")
    with op.batch_alter_table("claim_clusters") as batch:
        batch.drop_column("information_gain")
        batch.drop_column("is_controversial")
        batch.drop_column("is_minority")
        batch.drop_column("is_mainstream")
        batch.drop_column("applicable_conditions")
        batch.drop_column("opposing_reasons")
        batch.drop_column("support_count")
    with op.batch_alter_table("answer_analysis") as batch:
        batch.drop_column("reason")
        batch.drop_column("include")
        batch.drop_column("information_density")
    with op.batch_alter_table("answers") as batch:
        batch.drop_index("ix_answers_fetch_batch")
        batch.drop_column("fetch_batch")
        batch.drop_column("media_json")
        batch.drop_column("sort_order")
        batch.drop_column("external_updated_at")
        batch.drop_column("published_at")
        batch.drop_column("author_url")
    with op.batch_alter_table("questions") as batch:
        batch.drop_column("fetched_at")
        batch.drop_column("follower_count")
        batch.drop_column("answer_count")
        batch.drop_column("hot_score")
        batch.drop_column("hot_rank")
