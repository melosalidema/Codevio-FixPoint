from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.deps import DbSession
from app.repository import record_webhook_event, webhook_event_seen
from app.safety import webhooks

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/{provider}")
async def receive_webhook(provider: str, request: Request, db: DbSession) -> dict:
    """Verify a provider webhook: HMAC signature, freshness, and replay.

    Replay state is stored in Postgres, so protection survives restarts. The
    signature covers the raw body plus timestamp, preventing both forgery and
    delayed replay.
    """
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
