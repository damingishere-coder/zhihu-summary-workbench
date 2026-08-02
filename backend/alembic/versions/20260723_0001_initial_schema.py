"""创建三阶段长期基础数据结构。

Revision ID: 20260723_0001
Revises:
Create Date: 2026-07-23
"""

from typing import Sequence

from alembic import op

from backend.app import models  # noqa: F401
from backend.app.db.base import Base


revision: str = "20260723_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)

