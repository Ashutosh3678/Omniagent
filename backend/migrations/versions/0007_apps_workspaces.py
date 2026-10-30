"""agents report the apps and folders their owner set up

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

Json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("agents", sa.Column("apps", Json))
    op.add_column("agents", sa.Column("workspaces", Json))


def downgrade() -> None:
    op.drop_column("agents", "workspaces")
    op.drop_column("agents", "apps")
