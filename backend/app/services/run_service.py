from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.engine import RunSession
from app.agent.hybrid import build_hybrid, source_label
from app.agent.parser import parse
from app.config import get_settings
from app.models import Run, RunEvent
from app.providers.factory import build_backend
from app.repository import runs as repo
from app.safety.audit import verify_entries
from app.safety.models import ParsedFacts, ProposedAction, RunContext
from app.schemas import RunCreateRequest
from app.services import notifications

# Capabilities granted to every run. The client cannot change these.
DEFAULT_CAPABILITIES = [
    "stripe.read",
    "stripe.refund",
    "email.draft",
    "slack.post",
    "crm.write",
    "drive.read",
]


class RunNotFoundError(Exception):
    """Raised when a run id does not exist."""


class RunStateError(Exception):
    """Raised when an operation is invalid for the current run state."""


def seed_for(tenant_id: str, amount_cents: int = 4200, duplicate_customer: bool = False) -> dict[str, Any]:
    """Deterministic provider seed used by the demo twins."""
    customers = [{"id": "cus_acme", "email": "jane@acme.com", "name": "Jane Doe", "tenant_id": tenant_id}]
    if duplicate_customer:
        customers.append(
            {"id": "cus_acme2", "email": "jane@acme.com", "name": "Jane Doe", "tenant_id": tenant_id}
        )
    return {
        "customers": customers,
        "charges": [
            {"id": "ch_100", "customer_id": "cus_acme", "amount_cents": amount_cents, "tenant_id": tenant_id},
            {"id": "ch_101", "customer_id": "cus_acme", "amount_cents": amount_cents, "tenant_id": tenant_id},
        ],
        "contacts": [{"id": "con_1", "email": "jane@acme.com", "name": "Jane Doe", "tenant_id": tenant_id}],
        "documents": [
            {
                "id": "doc_policy",
                "name": "Refund Policy v1",
                "content": "Refunds within 30 days. Duplicate charges fully refundable.",
                "version_hash": "sha256:policy-v1",
                "tenant_id": tenant_id,
            }
        ],
    }


def _entries_json(session: RunSession) -> list[dict[str, Any]]:
    return [entry.model_dump(mode="json") for entry in session.audit_log.entries]


def _facts_payload(session: RunSession) -> dict[str, Any] | None:
    return session.facts.model_dump(mode="json") if session.facts else None


def _action_payload(session: RunSession) -> dict[str, Any] | None:
    return session.proposed.model_dump(mode="json") if session.proposed else None


def _detail(
    *,
    run_id: str,
    tenant_id: str,
    status: str,
    outcome: str,
    verified: bool,
    unsafe_blocked: int,
    request_text: str,
    created_at: Any,
    report: dict[str, Any] | None,
    verification: dict[str, Any] | None,
    artifact: dict[str, Any] | None,
    world_before: dict[str, Any] | None,
    world_after: dict[str, Any] | None,
    chain_ok: bool,
    chain_reason: str,
    entries: list[dict[str, Any]],
    planner_source: str = "deterministic",
    provider_backend: str = "twin",
    planner_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "tenant_id": tenant_id,
        "status": status,
        "outcome": outcome,
        "verified": verified,
        "unsafe_blocked": unsafe_blocked,
        "request_text": request_text,
        "created_at": created_at,
        "report": report,
        "verification": verification,
        "approval_artifact": artifact,
        "world_before": world_before,
        "world_after": world_after,
        "planner_source": planner_source,
        "provider_backend": provider_backend,
        "planner_meta": planner_meta,
        "audit": {"chain_ok": chain_ok, "reason": chain_reason, "entries": entries},
    }


def session_detail(
    row: Run,
    session: RunSession,
    world_before: dict[str, Any] | None,
    world_after: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the API payload straight from a live (un-persisted) session."""
    report = session.report
    chain_ok, chain_reason = session.audit_log.verify_chain()
    return _detail(
        run_id=row.id,
        tenant_id=row.tenant_id,
        status=report.status if report else "pending",
        outcome=report.outcome if report else "",
        verified=bool(report.verified) if report else False,
        unsafe_blocked=report.unsafe_blocked if report else 0,
        request_text=row.request_text,
        created_at=row.created_at,
        report=report.model_dump(mode="json") if report else None,
        verification=session.verification.model_dump(mode="json")
        if getattr(session, "verification", None)
        else None,
        artifact=session.artifact.model_dump(mode="json") if session.artifact else None,
        world_before=world_before,
        world_after=world_after,
        chain_ok=chain_ok,
        chain_reason=chain_reason,
        entries=_entries_json(session),
        planner_source=getattr(session, "planner_source", "deterministic"),
        provider_backend=getattr(session, "provider_backend", "twin"),
        planner_meta=getattr(session, "planner_meta", None),
    )


async def detail_from_db(db: AsyncSession, row: Run) -> dict[str, Any]:
    """Build the API payload from persisted state, verifying the stored chain."""
    entries = await repo.events_for(db, row.id)
    chain_ok, chain_reason = verify_entries(entries)
    return _detail(
        run_id=row.id,
        tenant_id=row.tenant_id,
        status=row.status,
        outcome=row.outcome,
        verified=row.verified,
        unsafe_blocked=row.unsafe_blocked,
        request_text=row.request_text,
        created_at=row.created_at,
        report=row.report,
        verification=row.verification,
        artifact=row.approval_artifact,
        world_before=row.world_before,
        world_after=row.world_after,
        chain_ok=chain_ok,
        chain_reason=chain_reason,
        entries=[entry.model_dump(mode="json") for entry in entries],
        planner_source=row.planner_source or "deterministic",
        provider_backend=row.provider_backend or "twin",
        planner_meta=row.planner_meta,
    )


async def create_run(db: AsyncSession, body: RunCreateRequest) -> dict[str, Any]:
    """Investigate, propose, gate, execute/verify - then persist everything."""
    settings = get_settings()
    run_id = uuid4().hex
    tenant_id = body.tenant_id or settings.default_tenant_id
    actor_user_id = body.actor_user_id or settings.default_actor_user_id

    ctx = RunContext(
        run_id=run_id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        trigger="api",
        capabilities=list(DEFAULT_CAPABILITIES),
        envelope=settings.envelope,
    )
    seed = seed_for(tenant_id, body.amount_cents, body.duplicate_customer)
    world = build_backend(settings, seed)
    if getattr(world.stripe, "supports_failure_injection", False):
        world.stripe.fail_refund_remaining = body.stripe_refund_failures
    world_before = world.snapshot()

    parser, planner = build_hybrid(settings)
    session = RunSession(
        world,
        ctx,
        body.request_text,
        policy_file_id=body.policy_file_id,
        parser_fn=parser,
        planner_fn=planner,
        crm_refund_status=settings.hubspot_refund_status,
    )
    session.run()
    session.planner_source = source_label(parser, planner)
    session.planner_meta = planner.meta or {}

    # Prefer the engine's post-investigation snapshot: it reflects the real
    # provider state (including live Stripe) immediately before execution.
    snapshot_before = session.world_before or world_before

    row = await repo.create_run_row(
        db,
        run_id=run_id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        trigger="api",
        request_text=body.request_text,
        policy_file_id=body.policy_file_id,
        capabilities=ctx.capabilities,
        amount_cents=body.amount_cents,
        duplicate_customer=body.duplicate_customer,
        stripe_refund_failures=body.stripe_refund_failures,
        seed=seed,
        parsed_facts=_facts_payload(session),
        proposed_action=_action_payload(session),
        planner_source=session.planner_source,
        provider_backend=settings.provider_backend,
        planner_meta=session.planner_meta,
    )
    await repo.persist_session(db, row, session, snapshot_before, world.snapshot())
    await db.commit()
    _notify_decision_from_session(row, session, automatic=True)
    return session_detail(row, session, snapshot_before, world.snapshot())


def replay_session(row: Run) -> tuple[RunSession, Any]:
    """Rebuild a run from its persisted committed plan.

    The engine is fed the facts and action that were stored at creation time,
    so the rebuilt audit chain is identical to the persisted one. This is what
    makes approval safe across restarts even when the planner is an LLM (whose
    output is not reproducible) or the providers are external.
    """
    settings = get_settings()
    seed = row.seed or {}
    world = build_backend(settings, seed)
    if getattr(world.stripe, "supports_failure_injection", False):
        world.stripe.fail_refund_remaining = row.stripe_refund_failures
    ctx = RunContext(
        run_id=row.id,
        tenant_id=row.tenant_id,
        actor_user_id=row.actor_user_id,
        trigger=row.trigger,
        capabilities=list(row.capabilities or DEFAULT_CAPABILITIES),
        envelope=settings.envelope,
    )
    facts = ParsedFacts(**row.parsed_facts) if row.parsed_facts else parse(row.request_text)
    action = ProposedAction(**row.proposed_action) if row.proposed_action else None
    session = RunSession(
        world,
        ctx,
        row.request_text,
        policy_file_id=row.policy_file_id,
        planner_source=row.planner_source or "deterministic",
        crm_refund_status=settings.hubspot_refund_status,
    )
    session.replay_committed(facts, action)
    return session, world


def _notify_decision_from_session(
    row: Run,
    session: RunSession,
    *,
    actor: str = "",
    role: str = "",
    automatic: bool = False,
) -> None:
    """Best-effort email notification for an autonomous or human decision.

    Approved outcomes (money moved) and denied outcomes (no money moved) are
    reported to Formspree; delivery never affects the run.
    """
    report = session.report
    if report is None:
        return
    if report.outcome in notifications.APPROVED_OUTCOMES:
        decision = "approved"
    elif report.outcome in notifications.DENIED_OUTCOMES:
        decision = "denied"
    else:
        return

    amount = row.amount_cents
    if session.artifact is not None:
        amount = session.artifact.amount_cents
    elif session.proposed is not None and session.proposed.params.get("amount_cents") is not None:
        amount = int(session.proposed.params["amount_cents"])

    notifications.notify_decision(
        decision=decision,
        outcome=report.outcome,
        run_id=row.id,
        request_text=row.request_text,
        facts=row.parsed_facts,
        amount_cents=int(amount),
        actor=actor,
        role=role,
        automatic=automatic,
        trigger=row.trigger,
    )


async def _load_for_decision(db: AsyncSession, run_id: str) -> tuple[Run, list[Any]]:
    row = await repo.get_run(db, run_id)
    if row is None:
        raise RunNotFoundError(run_id)
    if row.status != "awaiting_approval":
        raise RunStateError(f"run is not awaiting approval (status={row.status})")
    entries = await repo.events_for(db, run_id)
    chain_ok, chain_reason = verify_entries(entries)
    if not chain_ok:
        raise RunStateError(f"audit chain integrity check failed: {chain_reason}")
    return row, entries


async def approve_run(db: AsyncSession, run_id: str, role: str, approver_user_id: str) -> dict[str, Any]:
    row, _ = await _load_for_decision(db, run_id)
    session, world = replay_session(row)
    session.approve(role, approver_user_id)
    await repo.persist_session(db, row, session, row.world_before, world.snapshot())
    await db.commit()
    _notify_decision_from_session(row, session, actor=approver_user_id, role=role)
    return await detail_from_db(db, row)


async def deny_run(db: AsyncSession, run_id: str, approver_user_id: str) -> dict[str, Any]:
    row, _ = await _load_for_decision(db, run_id)
    session, world = replay_session(row)
    session.deny(approver_user_id)
    await repo.persist_session(db, row, session, row.world_before, world.snapshot())
    await db.commit()
    _notify_decision_from_session(row, session, actor=approver_user_id)
    return await detail_from_db(db, row)


async def list_runs(db: AsyncSession, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    rows = await repo.list_run_rows(db, limit=limit, offset=offset)
    return [
        {
            "run_id": row.id,
            "tenant_id": row.tenant_id,
            "status": row.status,
            "outcome": row.outcome,
            "verified": row.verified,
            "unsafe_blocked": row.unsafe_blocked,
            "request_text": row.request_text,
            "created_at": row.created_at,
        }
        for row in rows
    ]


async def audit_for(db: AsyncSession, run_id: str) -> dict[str, Any] | None:
    row = await repo.get_run(db, run_id)
    if row is None:
        return None
    entries = await repo.events_for(db, run_id)
    chain_ok, chain_reason = verify_entries(entries)
    return {
        "chain_ok": chain_ok,
        "reason": chain_reason,
        "entries": [entry.model_dump(mode="json") for entry in entries],
    }


async def tamper_audit(db: AsyncSession, run_id: str) -> dict[str, Any]:
    """Demo-only: mutate one stored audit payload and expose the broken chain.

    This violates the append-only guarantee on purpose so the UI can prove the
    hash chain detects tampering. Disabled unless ``FIXPOINT_DEMO_MODE`` is on.
    """
    row = await repo.get_run(db, run_id)
    if row is None:
        raise RunNotFoundError(run_id)
    events = await repo.events_for(db, run_id)
    if not events:
        raise RunStateError("run has no audit entries")

    target_seq = events[1].seq if len(events) > 1 else events[0].seq
    target = await db.scalar(select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.seq == target_seq))
    if target is None:
        raise RunStateError("audit entry not found")
    payload = dict(target.payload or {})
    payload["_demo_tamper"] = True
    target.payload = payload
    await db.commit()
    return await audit_for(db, run_id) or {"chain_ok": False, "reason": "missing", "entries": []}
