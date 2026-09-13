from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app.deps import AppSettings, DbSession
from app.repository import (
    get_run as get_run_row,
)
from app.repository import (
    record_webhook_event,
    webhook_event_seen,
)
from app.safety import webhooks

logger = logging.getLogger("fixpoint.webhooks")

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# Refund statuses that mean the event did not move money.
INACTIVE_REFUND_STATUSES = {"failed", "canceled"}


async def _stripe_event_link(db: DbSession, event: dict) -> tuple[str, str, str]:
    """Resolve a Stripe event to a Fixpoint run via ``metadata.run_id``.

    Returns ``(run_id, status, detail)`` where status is one of ``linked``,
    ``unlinked`` or ``mismatch``. Mismatches are recorded for escalation; state
    is never silently repaired.
    """
    event_type = str(event.get("type") or "")
    obj = (event.get("data") or {}).get("object") or {}
    metadata = obj.get("metadata") or {}
    run_id = str(metadata.get("run_id") or "")

    if not run_id and event_type == "charge.refunded":
        for refund in ((obj.get("refunds") or {}).get("data") or []):
            candidate = (refund.get("metadata") or {}).get("run_id")
            if candidate:
                run_id = str(candidate)
                break

    if not run_id:
        return "", "unlinked", "no_run_id"

    row = await get_run_row(db, str(run_id))
    if row is None:
        return run_id, "mismatch", "run_not_found"

    expected = (row.proposed_action or {}).get("params") or {}
    expected_charge = str(expected.get("charge_id") or "")
    expected_amount = expected.get("amount_cents")

    is_refund_object = str(obj.get("object") or "") == "refund"
    event_charge = str(obj.get("charge") or "") if is_refund_object else str(obj.get("id") or "")
    if event_type == "charge.refunded":
        event_amount = obj.get("amount_refunded")
    else:
        event_amount = obj.get("amount")

    if expected_charge and event_charge and event_charge != expected_charge:
        return run_id, "mismatch", "charge_mismatch"
    if (
        expected_amount is not None
        and event_amount is not None
        and int(event_amount) != int(expected_amount)
    ):
        return run_id, "mismatch", "amount_mismatch"
    return run_id, "linked", ""


@router.post("/stripe")
async def receive_stripe_webhook(request: Request, db: DbSession, settings: AppSettings) -> dict:
    """Verify, deduplicate and record a Stripe event, linking it to a run.

    v1 is record-and-link: signature verification (raw body, 300s tolerance),
    replay protection through ``webhook_events``, ``metadata.run_id`` linking,
    and mismatch flagging. There is no reconciliation engine here.

    Requests to this path that carry Fixpoint's own signature headers (rather
    than ``Stripe-Signature``) are served by the generic HMAC path for backward
    compatibility with existing integrations.
    """
    if not request.headers.get("stripe-signature") and request.headers.get("x-fixpoint-event-id"):
        return await _receive_signed_webhook("stripe", request, db)

    raw_body = (await request.body()).decode("utf-8")
    signature_header = request.headers.get("stripe-signature", "")
    ok, reason = webhooks.verify_stripe(raw_body, signature_header, settings.stripe_webhook_secret)
    if not ok:
        status_code = 503 if reason == "missing_secret" else 401
        raise HTTPException(status_code=status_code, detail=f"stripe_webhook_rejected:{reason}")

    try:
        event = json.loads(raw_body)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="invalid_json") from error
    if not isinstance(event, dict):
        raise HTTPException(status_code=400, detail="invalid_json")

    event_id = str(event.get("id") or "")
    event_type = str(event.get("type") or "")
    if not event_id.startswith("evt_"):
        raise HTTPException(status_code=400, detail="missing_event_id")

    if await webhook_event_seen(db, "stripe", event_id):
        return {"accepted": True, "duplicate": True, "event_id": event_id}

    run_id, status, detail = await _stripe_event_link(db, event)
    if status == "mismatch":
        logger.warning("stripe webhook %s (%s) flagged: %s", event_id, event_type, detail)

    try:
        await record_webhook_event(
            db,
            "stripe",
            event_id,
            event_type=event_type,
            run_id=run_id,
            status=status,
            detail=detail,
        )
        await db.commit()
    except Exception as error:  # noqa: BLE001 - unique constraint means a concurrent replay
        await db.rollback()
        raise HTTPException(status_code=409, detail="stripe_webhook_rejected:replay") from error

    return {
        "accepted": True,
        "event_id": event_id,
        "event_type": event_type,
        "run_id": run_id or None,
        "status": status,
        "detail": detail,
    }


@router.post("/{provider}")
async def receive_webhook(provider: str, request: Request, db: DbSession) -> dict:
    """Verify a provider webhook: HMAC signature, freshness, and replay.

    Replay state is stored in Postgres, so protection survives restarts. The
    signature covers the raw body plus timestamp, preventing both forgery and
    delayed replay.
    """
    return await _receive_signed_webhook(provider, request, db)


async def _receive_signed_webhook(provider: str, request: Request, db: DbSession) -> dict:
    raw_body = (await request.body()).decode("utf-8")
    signature = request.headers.get("x-fixpoint-signature", "")
    timestamp_raw = request.headers.get("x-fixpoint-timestamp", "0")
    event_id = request.headers.get("x-fixpoint-event-id", "")

    if not event_id:
        raise HTTPException(status_code=400, detail="missing_event_id")
    try:
        timestamp = int(timestamp_raw)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="invalid_timestamp") from error

    seen = await webhook_event_seen(db, provider, event_id)
    ok, reason = webhooks.verify(
        raw_body,
        timestamp,
        signature,
        {event_id} if seen else set(),
        event_id,
    )
    if not ok:
        status = 409 if reason == "replay" else 401
        raise HTTPException(status_code=status, detail=f"webhook_rejected:{reason}")

    try:
        await record_webhook_event(db, provider, event_id)
        await db.commit()
    except Exception as error:  # noqa: BLE001 - unique constraint means a concurrent replay
        await db.rollback()
        raise HTTPException(status_code=409, detail="webhook_rejected:replay") from error
    return {"accepted": True, "provider": provider, "event_id": event_id}
