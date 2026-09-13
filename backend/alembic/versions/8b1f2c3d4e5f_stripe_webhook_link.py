"""stripe webhook link fields

Revision ID: 8b1f2c3d4e5f
Revises: c4e8f01a2b77
Create Date: 2026-09-13 21:30:00.000000

Record-and-link outcome for provider webhooks (Stripe v1): the event type, the
Fixpoint run linked through metadata, a status (recorded, linked, unlinked,
mismatch) and a short detail for escalation review. Replay protection still uses
the (provider, event_id) primary key.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8b1f2c3d4e5f"
down_revision: str | None = "c4e8f01a2b77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "webhook_events", sa.Column("event_type", sa.String(64), nullable=False, server_default="")
    )
    op.add_column(
        "webhook_events", sa.Column("run_id", sa.String(36), nullable=False, server_default="")
    )
    op.add_column(
        "webhook_events",
        sa.Column("status", sa.String(16), nullable=False, server_default="recorded"),
    )
    op.add_column(
        "webhook_events", sa.Column("detail", sa.String(160), nullable=False, server_default="")
    )


def downgrade() -> None:
    op.drop_column("webhook_events", "detail")
    op.drop_column("webhook_events", "status")
    op.drop_column("webhook_events", "run_id")
    op.drop_column("webhook_events", "event_type")
