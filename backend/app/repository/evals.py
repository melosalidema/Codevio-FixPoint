from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EvalResult


async def record_results(
    db: AsyncSession,
    batch_id: str,
    results: list[dict[str, Any]],
) -> None:
    """Persist one evaluation batch for the dashboard history."""
    for result in results:
        db.add(
            EvalResult(
                batch_id=batch_id,
                scenario_id=result["id"],
                title=result.get("title", ""),
                passed=bool(result.get("passed")),
                observed=result.get("observed", {}),
                failed=list(result.get("failed", [])),
            )
        )
    await db.flush()


async def latest_batch(db: AsyncSession) -> tuple[str | None, list[EvalResult]]:
    """Return the most recently recorded batch of scenario results."""
    newest = await db.scalar(select(EvalResult).order_by(EvalResult.id.desc()).limit(1))
    if newest is None:
        return None, []
    result = await db.execute(
        select(EvalResult).where(EvalResult.batch_id == newest.batch_id).order_by(EvalResult.scenario_id)
    )
    return newest.batch_id, list(result.scalars().all())
