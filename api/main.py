from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from core.schemas import Envelope, RunContext
from evals.runner import run_all
from twins.world import World
from worker.run_engine import RunSession

app = FastAPI(title="Fixpoint Control Plane", version="0.1.0")

SESSIONS: dict[str, RunSession] = {}

DEFAULT_CAPABILITIES = [
    "stripe.read",
    "stripe.refund",
    "email.draft",
    "slack.post",
    "crm.write",
    "drive.read",
]


class RunRequest(BaseModel):
    request_text: str
    tenant_id: str = "t_123"
    actor_user_id: str = "u_88"
    capabilities: list[str] = Field(default_factory=lambda: list(DEFAULT_CAPABILITIES))
    seed: dict[str, Any] | None = None
    policy_file_id: str | None = "doc_policy"


class DecisionRequest(BaseModel):
    approver_user_id: str = "u_99"
    role: str = "team_lead"


def _seed_for(tenant_id: str) -> dict[str, Any]:
    return {
        "customers": [{"id": "cus_acme", "email": "jane@acme.com", "name": "Jane Doe", "tenant_id": tenant_id}],
        "charges": [
            {"id": "ch_100", "customer_id": "cus_acme", "amount_cents": 4200, "tenant_id": tenant_id},
            {"id": "ch_101", "customer_id": "cus_acme", "amount_cents": 4200, "tenant_id": tenant_id},
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/runs")
def create_run(body: RunRequest) -> dict[str, Any]:
    run_id = uuid.uuid4().hex
    ctx = RunContext(
        run_id=run_id,
        tenant_id=body.tenant_id,
        actor_user_id=body.actor_user_id,
        trigger="api",
        capabilities=body.capabilities,
        envelope=Envelope(),
    )
    world = World(body.seed or _seed_for(body.tenant_id))
    session = RunSession(world, ctx, body.request_text, policy_file_id=body.policy_file_id)
    report = session.run()
    SESSIONS[run_id] = session
    return {"report": report.model_dump(), "world": world.snapshot()}


@app.post("/runs/{run_id}/approve")
def approve_run(run_id: str, body: DecisionRequest) -> dict[str, Any]:
    session = SESSIONS.get(run_id)
    if session is None:
        raise HTTPException(status_code=404, detail="run not found")
    report = session.approve(body.role, body.approver_user_id)
    return {"report": report.model_dump(), "world": session.world.snapshot()}


@app.post("/runs/{run_id}/deny")
def deny_run(run_id: str, body: DecisionRequest) -> dict[str, Any]:
    session = SESSIONS.get(run_id)
    if session is None:
        raise HTTPException(status_code=404, detail="run not found")
    report = session.deny(body.approver_user_id)
    return {"report": report.model_dump(), "world": session.world.snapshot()}


@app.get("/runs/{run_id}/audit")
def audit_run(run_id: str) -> dict[str, Any]:
    session = SESSIONS.get(run_id)
    if session is None:
        raise HTTPException(status_code=404, detail="run not found")
    ok, reason = session.audit_log.verify_chain()
    return {"chain_ok": ok, "reason": reason, "entries": [e.model_dump() for e in session.audit_log.entries]}


@app.post("/webhooks/{provider}")
def webhook(provider: str, x_signature: str = Header(default=""), x_timestamp: str = Header(default="0")) -> dict[str, Any]:
    from core import webhooks

    ok, reason = webhooks.verify("{}", int(x_timestamp), x_signature, set(), f"{provider}-{x_timestamp}")
    if not ok:
        raise HTTPException(status_code=401, detail=f"webhook_rejected:{reason}")
    return {"accepted": True}


@app.get("/evals")
def evals() -> dict[str, Any]:
    results = run_all()
    passed = sum(1 for r in results if r["passed"])
    return {"passed": passed, "total": len(results), "results": results}
