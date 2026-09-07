"""persist browser capture v2 diagnostics

Revision ID: 20260827_0006
Revises: 20260823_0005
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260827_0006"
down_revision: str | None = "20260823_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {
        item["name"] for item in sa.inspect(op.get_bind()).get_columns("collection_jobs")
    }
    additions = {
        "capture_version": sa.Column("capture_version", sa.Integer()),
        "capture_method": sa.Column("capture_method", sa.String(32)),
        "capture_page_url": sa.Column("capture_page_url", sa.String(1000)),
        "visible_answer_count": sa.Column("visible_answer_count", sa.Integer()),
        "collected_answer_count": sa.Column("collected_answer_count", sa.Integer()),
        "capture_diagnostics_json": sa.Column(
            "capture_diagnostics_json", sa.JSON(), nullable=False, server_default="[]"
        ),
    }
    for name, column in additions.items():
        if name not in columns:
            op.add_column("collection_jobs", column)


def downgrade() -> None:
    columns = {
        item["name"] for item in sa.inspect(op.get_bind()).get_columns("collection_jobs")
    }
    for name in (
        "capture_diagnostics_json",
        "collected_answer_count",
        "visible_answer_count",
        "capture_page_url",
        "capture_method",
        "capture_version",
    ):
        if name in columns:
            op.drop_column("collection_jobs", name)
