"""device status/scope/expiry, pairing codes, audit events

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

Json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("agents", sa.Column("status", sa.String(16), nullable=False, server_default="active"))
    op.add_column(
        "agents",
        sa.Column("permitted_apps", Json, nullable=False, server_default=sa.text("'[\"notepad\"]'")),
    )
    op.add_column("agents", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.add_column("agents", sa.Column("revoked_at", sa.DateTime(timezone=True)))

    op.create_table(
        "pairing_codes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_pairing_codes_user_id", "pairing_codes", ["user_id"])
    op.create_index("ix_pairing_codes_code_hash", "pairing_codes", ["code_hash"], unique=True)

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("agent_id", sa.String(36)),
        sa.Column("task_id", sa.String(36)),
        sa.Column("event", sa.String(48), nullable=False),
        sa.Column("decision", sa.String(8), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])
    op.create_index("ix_audit_events_agent_id", "audit_events", ["agent_id"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("pairing_codes")
    for column in ("revoked_at", "expires_at", "permitted_apps", "status"):
        op.drop_column("agents", column)
