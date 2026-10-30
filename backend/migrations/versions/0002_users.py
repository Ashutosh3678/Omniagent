"""users, per-user ownership of agents and tasks, device token hash

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    # Existing rows (pre-accounts) keep user_id NULL and are invisible to every user.
    op.add_column("agents", sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id")))
    op.add_column("agents", sa.Column("token_hash", sa.String(64)))
    op.create_index("ix_agents_user_id", "agents", ["user_id"])
    op.add_column("tasks", sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id")))
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_user_id", "tasks")
    op.drop_column("tasks", "user_id")
    op.drop_index("ix_agents_user_id", "agents")
    op.drop_column("agents", "token_hash")
    op.drop_column("agents", "user_id")
    op.drop_index("ix_users_email", "users")
    op.drop_table("users")
