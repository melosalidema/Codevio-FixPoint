from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.deps import AppSettings, DbSession
from app.repository import get_run as get_run_row
from app.schemas import (
    AuditResponse,
    DecisionRequest,
    RunCreateRequest,
    RunDetail,
    RunSummary,
)
from app.services import run_service

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("", response_model=RunDetail, status_code=201)
async def create_run(body: RunCreateRequest, db: DbSession) -> dict:
    """Run the agent end to end and return the full timeline.

    Returns ``awaiting_approval`` when the gateway paused a money action.
    """
    return await run_service.create_run(db, body)


@router.get("", response_model=list[RunSummary])
async def list_runs(
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    return await run_service.list_runs(db, limit=limit, offset=offset)


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(run_id: str, db: DbSession) -> dict:
    row = await get_run_row(db, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    return await run_service.detail_from_db(db, row)


@router.post("/{run_id}/approve", response_model=RunDetail)
async def approve_run(run_id: str, body: DecisionRequest, db: DbSession) -> dict:
    """Apply a human approval. The action hash must still match the stored one."""
    try:
        return await run_service.approve_run(db, run_id, body.role, body.approver_user_id)
    except run_service.RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    except run_service.RunStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{run_id}/deny", response_model=RunDetail)
async def deny_run(run_id: str, body: DecisionRequest, db: DbSession) -> dict:
    """Deny the pending action: no money moves, records are reconciled."""
    try:
        return await run_service.deny_run(db, run_id, body.approver_user_id)
    except run_service.RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    except run_service.RunStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/{run_id}/audit", response_model=AuditResponse)
async def get_audit(run_id: str, db: DbSession) -> dict:
    audit = await run_service.audit_for(db, run_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="run not found")
    return audit


@router.post("/{run_id}/audit/tamper", response_model=AuditResponse)
async def tamper_audit(run_id: str, db: DbSession, settings: AppSettings) -> dict:
    """Demo-only: break the stored chain to prove tamper detection works."""
    if not settings.demo_mode:
        raise HTTPException(status_code=403, detail="demo mode is disabled")
    try:
        return await run_service.tamper_audit(db, run_id)
    except run_service.RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="run not found") from error
    except run_service.RunStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
