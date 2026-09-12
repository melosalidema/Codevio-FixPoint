from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.deps import AppSettings, DbSession

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(db: DbSession, settings: AppSettings) -> dict[str, str]:
    """Liveness + database readiness probe (used by Railway healthcheck)."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception as error:  # noqa: BLE001 - health probes report, never crash
        raise HTTPException(status_code=503, detail="database_unavailable") from error
    return {"status": "ok", "database": "ok", "version": settings.version, "env": settings.env}
