from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for every Fixpoint table."""


class Run(Base):
    """One agent run.

    The full deterministic state of a run is reconstructable from ``seed``
    plus ``request_text``: the engine is pure, so ``approve``/``deny`` replay
    the run before applying a human decision. That means a server restart can
    never corrupt a pending approval.
    """

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    actor_user_id: Mapped[str] = mapped_column(String(64))
    trigger: Mapped[str] = mapped_column(String(32), default="api")

    request_text: Mapped[str] = mapped_column(Text)
    policy_file_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Deterministic provider twin seed + injected failure configuration.
    amount_cents: Mapped[int] = mapped_column(Integer, default=4200)
    duplicate_customer: Mapped[bool] = mapped_column(Boolean, default=False)
    stripe_refund_failures: Mapped[int] = mapped_column(Integer, default=0)
    seed: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # The committed plan. Facts and the proposed action are persisted so that
    # approve/deny can replay the exact same audit chain instead of re-planning.
    # This is what makes the planner safely replaceable (LLM or deterministic)
    # and keeps approval binding stable across restarts.
    parsed_facts: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    proposed_action: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    planner_source: Mapped[str] = mapped_column(String(32), default="deterministic")
    provider_backend: Mapped[str] = mapped_column(String(32), default="twin")
    planner_meta: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Outcome.
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    outcome: Mapped[str] = mapped_column(String(64), default="")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    unsafe_blocked: Mapped[int] = mapped_column(Integer, default=0)
    report_text: Mapped[str] = mapped_column(Text, default="")

    # Serialized safety artifacts.
    report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    verification: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    approval_artifact: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    world_before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    world_after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    events: Mapped[list[RunEvent]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="RunEvent.seq"
    )


class RunEvent(Base):
    """Append-only, hash-chained audit entry for a run."""

    __tablename__ = "run_events"
    __table_args__ = (UniqueConstraint("run_id", "seq", name="uq_run_events_run_seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    run: Mapped[Run] = relationship(back_populates="events")


class IdempotencyKey(Base):
    """Executed mutation idempotency keys, durable across restarts."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    action_hash: Mapped[str] = mapped_column(String(64), default="")
    tool: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WebhookEvent(Base):
    """Seen webhook event ids; replay protection survives restarts.

    Stripe events also carry the record-and-link outcome: ``event_type``,
    ``run_id`` when metadata links the event to a run, ``status`` (recorded,
    linked, unlinked, mismatch) and a short ``detail`` for escalation review.
    """

    __tablename__ = "webhook_events"

    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), default="", server_default="")
    run_id: Mapped[str] = mapped_column(String(36), default="", server_default="")
    status: Mapped[str] = mapped_column(String(16), default="recorded", server_default="recorded")
    detail: Mapped[str] = mapped_column(String(160), default="", server_default="")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EvalResult(Base):
    """One scenario result from an evaluation batch (dashboard history)."""

    __tablename__ = "eval_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(36), index=True)
    scenario_id: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    observed: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    failed: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
