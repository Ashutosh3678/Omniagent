"""initial: agents, tasks, screenshots

Revision ID: 0001
Revises:
Create Date: 2026-10-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

Json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("hostname", sa.String(255), nullable=False),
        sa.Column("online", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("connected_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("instruction", sa.Text, nullable=False),
        sa.Column("action", Json, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("logs", Json, nullable=False),
        sa.Column("steps", Json, nullable=False),
        sa.Column("screenshot_id", sa.String(36)),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("error", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tasks_agent_id", "tasks", ["agent_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_created_at", "tasks", ["created_at"])
    op.create_table(
        "screenshots",
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id"), primary_key=True),
        sa.Column("data", sa.LargeBinary, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("screenshots")
    op.drop_table("tasks")
    op.drop_table("agents")
