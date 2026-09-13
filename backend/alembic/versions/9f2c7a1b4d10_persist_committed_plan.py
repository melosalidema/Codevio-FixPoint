"""persist committed plan

Revision ID: 9f2c7a1b4d10
Revises: 611e865934cf
Create Date: 2026-09-13 10:20:00.000000

Adds the persisted facts + proposed action so approve/deny replay the exact
committed audit chain instead of re-planning. Enables an LLM planner and an
external provider backend without breaking approval binding or the audit chain.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f2c7a1b4d10"
down_revision: str | None = "611e865934cf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("parsed_facts", sa.JSON(), nullable=True))
    op.add_column("runs", sa.Column("proposed_action", sa.JSON(), nullable=True))
    op.add_column(
        "runs",
        sa.Column("planner_source", sa.String(length=32), nullable=False, server_default="deterministic"),
    )
    op.add_column(
        "runs",
        sa.Column("provider_backend", sa.String(length=32), nullable=False, server_default="twin"),
    )


def downgrade() -> None:
    op.drop_column("runs", "provider_backend")
    op.drop_column("runs", "planner_source")
    op.drop_column("runs", "proposed_action")
    op.drop_column("runs", "parsed_facts")
