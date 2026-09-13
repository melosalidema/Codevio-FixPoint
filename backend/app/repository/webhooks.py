from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WebhookEvent


async def webhook_event_seen(db: AsyncSession, provider: str, event_id: str) -> bool:
    return await db.get(WebhookEvent, (provider, event_id)) is not None


async def record_webhook_event(
    db: AsyncSession,
    provider: str,
    event_id: str,
    *,
    event_type: str = "",
    run_id: str = "",
    status: str = "recorded",
    detail: str = "",
) -> None:
    db.add(
        WebhookEvent(
            provider=provider,
            event_id=event_id,
            event_type=event_type,
            run_id=run_id,
            status=status,
            detail=detail[:160],
        )
    )
    await db.flush()
