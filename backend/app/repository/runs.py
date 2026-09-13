from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IdempotencyKey, Run, RunEvent
from app.safety.canonical import canonical_json
from app.safety.models import LedgerEntry, LedgerType


def jsonable(value: Any) -> Any:
    """Normalize enums/sets/datetimes into plain JSON-compatible data."""
    return json.loads(canonical_json(value))


def to_entry(row: RunEvent) -> LedgerEntry:
    return LedgerEntry(
        seq=row.seq,
        run_id=row.run_id,
        type=LedgerType(row.type),
        payload=row.payload or {},
        prev_hash=row.prev_hash,
        hash=row.hash,
    )


async def create_run_row(
    db: AsyncSession,
    *,
    run_id: str,
    tenant_id: str,
    actor_user_id: str,
    trigger: str,
    request_text: str,
    policy_file_id: str | None,
    capabilities: list[str],
    amount_cents: int,
    duplicate_customer: bool,
    stripe_refund_failures: int,
    seed: dict[str, Any],
    parsed_facts: dict[str, Any] | None = None,
    proposed_action: dict[str, Any] | None = None,
    planner_source: str = "deterministic",
    provider_backend: str = "twin",
    planner_meta: dict[str, Any] | None = None,
) -> Run:
    row = Run(
        id=run_id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        trigger=trigger,
        request_text=request_text,
        policy_file_id=policy_file_id,
        capabilities=list(capabilities),
        amount_cents=amount_cents,
        duplicate_customer=duplicate_customer,
        stripe_refund_failures=stripe_refund_failures,
        seed=jsonable(seed),
        parsed_facts=jsonable(parsed_facts) if parsed_facts is not None else None,
        proposed_action=jsonable(proposed_action) if proposed_action is not None else None,
        planner_source=planner_source,
        provider_backend=provider_backend,
        planner_meta=jsonable(planner_meta) if planner_meta is not None else None,
    )
    db.add(row)
    await db.flush()
    return row


async def persist_session(
    db: AsyncSession,
    row: Run,
    session: Any,
    world_before: dict[str, Any] | None,
    world_after: dict[str, Any] | None,
) -> Run:
    """Write the run outcome and append any new audit events.

    Events are append-only: existing seq values are never rewritten. This is
    what lets the tamper endpoint break the chain visibly while normal
    approval replay only appends.
    """
    report = session.report
    row.status = report.status if report else "pending"
    row.outcome = report.outcome if report else ""
    row.verified = bool(report.verified) if report else False
    row.unsafe_blocked = report.unsafe_blocked if report else 0
    row.report_text = report.report_text if report else ""
    row.report = report.model_dump(mode="json") if report else None
    verification = getattr(session, "verification", None)
    row.verification = verification.model_dump(mode="json") if verification else None
    row.approval_artifact = session.artifact.model_dump(mode="json") if session.artifact else None
    facts = getattr(session, "facts", None)
    if facts is not None:
        row.parsed_facts = jsonable(facts.model_dump(mode="json"))
    if session.proposed is not None:
        row.proposed_action = jsonable(session.proposed.model_dump(mode="json"))
    if getattr(session, "planner_source", None):
        row.planner_source = session.planner_source
    meta = getattr(session, "planner_meta", None)
    if meta is not None:
        row.planner_meta = jsonable(meta)
    if world_before is not None:
        row.world_before = jsonable(world_before)
    row.world_after = jsonable(world_after) if world_after is not None else None

    current_max = await db.scalar(select(func.max(RunEvent.seq)).where(RunEvent.run_id == row.id))
    current_max = -1 if current_max is None else int(current_max)
    for entry in session.audit_log.entries:
        if entry.seq > current_max:
            db.add(
                RunEvent(
                    run_id=row.id,
                    seq=entry.seq,
                    type=entry.type.value,
                    payload=jsonable(entry.payload),
                    prev_hash=entry.prev_hash,
                    hash=entry.hash,
                )
            )

    for key in session.state.seen_idempotency_keys:
        if await db.get(IdempotencyKey, key) is None:
            db.add(
                IdempotencyKey(
                    key=key,
                    run_id=row.id,
                    action_hash=_action_hash(session, key),
                    tool=session.proposed.tool if session.proposed else "",
                )
            )

    await db.flush()
    return row


def _action_hash(session: Any, key: str) -> str:
    """Best-effort action hash for the idempotency record (audit aid)."""
    if session.decision is not None and session.decision.idempotency_key == key:
        return session.decision.action_hash
    return ""


async def get_run(db: AsyncSession, run_id: str) -> Run | None:
    return await db.get(Run, run_id)


async def list_run_rows(db: AsyncSession, limit: int = 50, offset: int = 0) -> list[Run]:
    result = await db.execute(
        select(Run).order_by(Run.created_at.desc(), Run.id.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all())


async def events_for(db: AsyncSession, run_id: str) -> list[LedgerEntry]:
    result = await db.execute(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq))
    return [to_entry(row) for row in result.scalars().all()]
