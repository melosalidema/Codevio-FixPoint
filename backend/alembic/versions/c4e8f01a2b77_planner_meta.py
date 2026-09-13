"""planner metadata

Revision ID: c4e8f01a2b77
Revises: 9f2c7a1b4d10
Create Date: 2026-09-13 10:35:00.000000

Non-hashed LLM/planner telemetry for the run detail (model, tokens, latency,
fallback reason). Kept off the hash chain on purpose: replay must not depend on
model output.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e8f01a2b77"
down_revision: str | None = "9f2c7a1b4d10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("planner_meta", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "planner_meta")
