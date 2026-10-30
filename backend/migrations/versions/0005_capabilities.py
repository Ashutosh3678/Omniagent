"""agent capabilities and per-step screenshots

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

Json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("agents", sa.Column("capabilities", Json))
    op.create_table(
        "step_screenshots",
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id"), primary_key=True),
        sa.Column("step_index", sa.Integer, primary_key=True),
        sa.Column("content_type", sa.String(32), nullable=False),
        sa.Column("data", sa.LargeBinary, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("step_screenshots")
    op.drop_column("agents", "capabilities")
