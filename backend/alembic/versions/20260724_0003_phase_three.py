"""补齐第三阶段信息图、排期、成本和 Prompt 管理字段。

Revision ID: 20260724_0003
Revises: 20260724_0002
Create Date: 2026-07-24
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260724_0003"
down_revision: str | None = "20260724_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _column_names(table_name: str) -> set[str]:
    return {item["name"] for item in _inspector().get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    return {item["name"] for item in _inspector().get_indexes(table_name)}


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
        "daily_plans",
        [
            sa.Column(
                "execute_time", sa.String(5), nullable=False, server_default="09:00"
            ),
            sa.Column(
                "max_concurrency", sa.Integer(), nullable=False, server_default="3"
            ),
            sa.Column(
                "max_answers", sa.Integer(), nullable=False, server_default="100"
            ),
            sa.Column(
                "daily_publish_limit",
                sa.Integer(),
                nullable=False,
                server_default="10",
            ),
            sa.Column(
                "publish_interval_minutes",
                sa.Integer(),
                nullable=False,
                server_default="30",
            ),
            sa.Column(
                "auto_production",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "auto_publish",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("last_executed_at", sa.DateTime(timezone=True)),
            sa.Column("result", sa.JSON(), nullable=False, server_default="{}"),
        ],
    )

    _add_missing_columns(
        "model_usage_logs",
        [
            sa.Column("stage", sa.String(64), nullable=False, server_default=""),
            sa.Column(
                "cache_hit",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "fallback_used",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "retry_count", sa.Integer(), nullable=False, server_default="0"
            ),
        ],
    )
    if "ix_model_usage_logs_stage" not in _index_names("model_usage_logs"):
        with op.batch_alter_table("model_usage_logs") as batch:
            batch.create_index("ix_model_usage_logs_stage", ["stage"])

    if "model_response_cache" not in _inspector().get_table_names():
        op.create_table(
            "model_response_cache",
            sa.Column("cache_key", sa.String(64), nullable=False),
            sa.Column("schema_name", sa.String(200), nullable=False),
            sa.Column("provider", sa.String(64), nullable=False),
            sa.Column("model", sa.String(128), nullable=False),
            sa.Column("model_role", sa.String(64), nullable=False),
            sa.Column("response_json", sa.JSON(), nullable=False),
            sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("cache_key"),
        )
        op.create_index(
            "ix_model_response_cache_cache_key",
            "model_response_cache",
            ["cache_key"],
        )
        op.create_index(
            "ix_model_response_cache_schema_name",
            "model_response_cache",
            ["schema_name"],
        )

    _add_missing_columns(
        "prompt_versions",
        [
            sa.Column("parameters", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("test_input", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("test_output", sa.Text(), nullable=False, server_default=""),
            sa.Column("change_note", sa.Text(), nullable=False, server_default=""),
            sa.Column(
                "created_by",
                sa.String(128),
                nullable=False,
                server_default="operator",
            ),
        ],
    )

    _add_missing_columns(
        "image_versions",
        [
            sa.Column("thumbnail_path", sa.String(1000)),
            sa.Column("html_snapshot_path", sa.String(1000)),
            sa.Column(
                "render_status",
                sa.String(32),
                nullable=False,
                server_default="not_rendered",
            ),
            sa.Column(
                "canvas_width", sa.Integer(), nullable=False, server_default="1080"
            ),
            sa.Column(
                "canvas_height", sa.Integer(), nullable=False, server_default="1440"
            ),
            sa.Column(
                "overflow_json", sa.JSON(), nullable=False, server_default="[]"
            ),
            sa.Column(
                "render_log_json", sa.JSON(), nullable=False, server_default="[]"
            ),
        ],
    )

    _add_missing_columns(
        "publish_schedules",
        [
            sa.Column("article_version_id", sa.String(36)),
            sa.Column("image_version_id", sa.String(36)),
            sa.Column(
                "sort_order", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "interval_minutes",
                sa.Integer(),
                nullable=False,
                server_default="30",
            ),
            sa.Column(
                "conflict_state", sa.JSON(), nullable=False, server_default="{}"
            ),
            sa.Column("confirmed_at", sa.DateTime(timezone=True)),
            sa.Column("confirmed_by", sa.String(128)),
            sa.Column("executed_at", sa.DateTime(timezone=True)),
        ],
    )
    schedule_indexes = _index_names("publish_schedules")
    with op.batch_alter_table("publish_schedules") as batch:
        if "ix_publish_schedules_article_version_id" not in schedule_indexes:
            batch.create_index(
                "ix_publish_schedules_article_version_id", ["article_version_id"]
            )
        if "ix_publish_schedules_image_version_id" not in schedule_indexes:
            batch.create_index(
                "ix_publish_schedules_image_version_id", ["image_version_id"]
            )
        foreign_keys = {
            tuple(item.get("constrained_columns") or [])
            for item in _inspector().get_foreign_keys("publish_schedules")
        }
        if ("article_version_id",) not in foreign_keys:
            batch.create_foreign_key(
                "fk_publish_schedule_article_version",
                "article_versions",
                ["article_version_id"],
                ["id"],
                ondelete="RESTRICT",
            )
        if ("image_version_id",) not in foreign_keys:
            batch.create_foreign_key(
                "fk_publish_schedule_image_version",
                "image_versions",
                ["image_version_id"],
                ["id"],
                ondelete="RESTRICT",
            )

    _add_missing_columns(
        "publish_records",
        [
            sa.Column("article_version_id", sa.String(36)),
            sa.Column("image_version_id", sa.String(36)),
            sa.Column("screenshot_path", sa.String(1000)),
            sa.Column(
                "attempt_count", sa.Integer(), nullable=False, server_default="1"
            ),
        ],
    )
    with op.batch_alter_table("publish_records") as batch:
        foreign_keys = {
            tuple(item.get("constrained_columns") or [])
            for item in _inspector().get_foreign_keys("publish_records")
        }
        if ("article_version_id",) not in foreign_keys:
            batch.create_foreign_key(
                "fk_publish_record_article_version",
                "article_versions",
                ["article_version_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if ("image_version_id",) not in foreign_keys:
            batch.create_foreign_key(
                "fk_publish_record_image_version",
                "image_versions",
                ["image_version_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    with op.batch_alter_table("publish_records") as batch:
        batch.drop_constraint(
            "fk_publish_record_image_version", type_="foreignkey"
        )
        batch.drop_constraint(
            "fk_publish_record_article_version", type_="foreignkey"
        )
        batch.drop_column("attempt_count")
        batch.drop_column("screenshot_path")
        batch.drop_column("image_version_id")
        batch.drop_column("article_version_id")

    with op.batch_alter_table("publish_schedules") as batch:
        batch.drop_constraint(
            "fk_publish_schedule_image_version", type_="foreignkey"
        )
        batch.drop_constraint(
            "fk_publish_schedule_article_version", type_="foreignkey"
        )
        batch.drop_index("ix_publish_schedules_image_version_id")
        batch.drop_index("ix_publish_schedules_article_version_id")
        batch.drop_column("executed_at")
        batch.drop_column("confirmed_by")
        batch.drop_column("confirmed_at")
        batch.drop_column("conflict_state")
        batch.drop_column("interval_minutes")
        batch.drop_column("sort_order")
        batch.drop_column("image_version_id")
        batch.drop_column("article_version_id")

    with op.batch_alter_table("image_versions") as batch:
        batch.drop_column("render_log_json")
        batch.drop_column("overflow_json")
        batch.drop_column("canvas_height")
        batch.drop_column("canvas_width")
        batch.drop_column("render_status")
        batch.drop_column("html_snapshot_path")
        batch.drop_column("thumbnail_path")

    with op.batch_alter_table("prompt_versions") as batch:
        batch.drop_column("created_by")
        batch.drop_column("change_note")
        batch.drop_column("test_output")
        batch.drop_column("test_input")
        batch.drop_column("parameters")

    op.drop_index(
        "ix_model_response_cache_schema_name", table_name="model_response_cache"
    )
    op.drop_index(
        "ix_model_response_cache_cache_key", table_name="model_response_cache"
    )
    op.drop_table("model_response_cache")

    with op.batch_alter_table("model_usage_logs") as batch:
        batch.drop_index("ix_model_usage_logs_stage")
        batch.drop_column("retry_count")
        batch.drop_column("fallback_used")
        batch.drop_column("cache_hit")
        batch.drop_column("stage")

    with op.batch_alter_table("daily_plans") as batch:
        batch.drop_column("result")
        batch.drop_column("last_executed_at")
        batch.drop_column("auto_publish")
        batch.drop_column("auto_production")
        batch.drop_column("publish_interval_minutes")
        batch.drop_column("daily_publish_limit")
        batch.drop_column("max_answers")
        batch.drop_column("max_concurrency")
        batch.drop_column("execute_time")
