from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WebhookEvent


async def webhook_event_seen(db: AsyncSession, provider: str, event_id: str) -> bool:
    return await db.get(WebhookEvent, (provider, event_id)) is not None


async def record_webhook_event(db: AsyncSession, provider: str, event_id: str) -> None:
    db.add(WebhookEvent(provider=provider, event_id=event_id))
    await db.flush()
