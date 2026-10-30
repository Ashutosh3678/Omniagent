"""tasks hold a validated multi-step plan instead of a single action

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

Json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("tasks", sa.Column("plan", Json, nullable=False, server_default=sa.text("'[]'")))
    op.add_column("tasks", sa.Column("held_back", Json, nullable=False, server_default=sa.text("'[]'")))
    op.add_column("tasks", sa.Column("confidence", sa.Float))

    # Old single-action tasks become a two-step plan so history still reads correctly.
    tasks = sa.table("tasks", sa.column("id", sa.String), sa.column("action", Json), sa.column("plan", Json))
    bind = op.get_bind()
    for row in bind.execute(sa.select(tasks.c.id, tasks.c.action)).all():
        action = row.action or {}
        if action.get("type") != "open_notepad":
            continue
        plan = [
            {"index": 0, "action": {"type": "open_app", "app": "notepad"}, "description": "Open Notepad", "confidence": 1.0},
            {
                "index": 1,
                "action": {"type": "type_text", "text": action.get("message") or "Hello from OmniAgent"},
                "description": "Type text",
                "confidence": 1.0,
            },
        ]
        bind.execute(tasks.update().where(tasks.c.id == row.id).values(plan=plan))

    op.drop_column("tasks", "action")


def downgrade() -> None:
    op.add_column("tasks", sa.Column("action", Json, nullable=False, server_default=sa.text("'{}'")))
    op.drop_column("tasks", "confidence")
    op.drop_column("tasks", "held_back")
    op.drop_column("tasks", "plan")
