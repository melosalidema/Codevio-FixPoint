from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.deps import DbSession
from app.evals.runner import run_scenario
from app.evals.scenarios import SCENARIOS
from app.repository import record_results
from app.schemas import ScenarioOut, ScenarioRunOut

router = APIRouter(prefix="/api/scenarios", tags=["evaluation"])


@router.get("", response_model=dict[str, list[ScenarioOut]])
async def list_scenarios() -> dict:
    return {
        "scenarios": [
            {
                "id": spec["id"],
                "title": spec["title"],
                "flow": spec["flow"],
                "request": spec.get("request"),
                "expect": spec.get("expect", {}),
            }
            for spec in SCENARIOS
        ]
    }


@router.post("/{scenario_id}/run", response_model=ScenarioRunOut)
async def run_one(scenario_id: str, db: DbSession) -> dict:
    spec = next((s for s in SCENARIOS if s["id"].lower() == scenario_id.lower()), None)
    if spec is None:
        raise HTTPException(status_code=404, detail="scenario not found")
    try:
        result = await asyncio.to_thread(run_scenario, spec)
    except Exception as error:  # noqa: BLE001 - a scenario error is a FAIL result
        result = {
            "id": spec["id"],
            "title": spec["title"],
            "passed": False,
            "observed": {},
            "failed": [f"error: {error}"],
        }
    await record_results(db, uuid4().hex, [result])
    await db.commit()
    return result
