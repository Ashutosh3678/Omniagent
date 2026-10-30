"""tasks can point at a screenshot stored on the CDN

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("screenshot_ref", sa.String(400)))


def downgrade() -> None:
    op.drop_column("tasks", "screenshot_ref")
