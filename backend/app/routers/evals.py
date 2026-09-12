from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi import APIRouter

from app.deps import DbSession
from app.evals.runner import run_all
from app.repository import latest_batch, record_results
from app.schemas import EvalResultsOut, EvalRunOut

router = APIRouter(prefix="/api/evals", tags=["evaluation"])


def _unsafe_total(results: list[dict]) -> int:
    total = 0
    for result in results:
        observed = result.get("observed", {})
        total += int(observed.get("unsafe_blocked", observed.get("unsafe", 0)) or 0)
    return total


@router.post("/run", response_model=EvalRunOut)
async def run_matrix(db: DbSession) -> dict:
    """Run the full S1-S16 matrix and persist the batch."""
    results = await asyncio.to_thread(run_all)
    batch_id = uuid4().hex
    await record_results(db, batch_id, results)
    await db.commit()
    return {
        "batch_id": batch_id,
        "total": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "unsafe_blocked": _unsafe_total(results),
        "results": results,
    }


@router.get("/results", response_model=EvalResultsOut)
async def latest_results(db: DbSession) -> dict:
    """The most recent stored batch, so the dashboard survives restarts."""
    batch_id, rows = await latest_batch(db)
    results = [
        {
            "id": row.scenario_id,
            "title": row.title,
            "passed": row.passed,
            "observed": row.observed or {},
            "failed": row.failed or [],
        }
        for row in rows
    ]
    return {
        "batch_id": batch_id,
        "total": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "unsafe_blocked": _unsafe_total(results),
        "results": results,
    }
