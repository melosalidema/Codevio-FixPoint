from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RunCreateRequest(BaseModel):
    """Input to create a run. The envelope and capabilities are NOT accepted
    here: they are sealed server-side and can never be influenced by input."""

    request_text: str = Field(min_length=1, max_length=4000)
    tenant_id: str | None = Field(default=None, max_length=64)
    actor_user_id: str | None = Field(default=None, max_length=64)
    amount_cents: int = Field(default=4200, ge=1, le=1_000_000)
    duplicate_customer: bool = False
    stripe_refund_failures: int = Field(default=0, ge=0, le=5)
    policy_file_id: str | None = Field(default="doc_policy", max_length=64)


class DecisionRequest(BaseModel):
    """A human approval decision."""

    approver_user_id: str = Field(default="u_99", min_length=1, max_length=64)
    role: Literal["team_lead", "finance", "finance_dual"] = "team_lead"


class EnvelopeOut(BaseModel):
    max_refund_cents: int
    approval_threshold_cents: int
    auto_approve_cents: int
    team_lead_cents: int
    dual_approval_cents: int
    max_actions_per_run: int


class ConfigResponse(BaseModel):
    demo_mode: bool
    env: str
    version: str
    default_tenant_id: str
    llm_enabled: bool = False
    llm_model: str = ""
    provider_backend: str = "twin"
    envelope: EnvelopeOut


class AuditResponse(BaseModel):
    chain_ok: bool
    reason: str
    entries: list[dict[str, Any]] = Field(default_factory=list)


class RunDetail(BaseModel):
    run_id: str
    tenant_id: str
    status: str
    outcome: str
    verified: bool
    unsafe_blocked: int
    request_text: str
    created_at: datetime | None = None
    report: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    approval_artifact: dict[str, Any] | None = None
    world_before: dict[str, Any] | None = None
    world_after: dict[str, Any] | None = None
    planner_source: str = "deterministic"
    provider_backend: str = "twin"
    planner_meta: dict[str, Any] | None = None
    audit: AuditResponse


class RunSummary(BaseModel):
    run_id: str
    tenant_id: str
    status: str
    outcome: str
    verified: bool
    unsafe_blocked: int
    request_text: str
    created_at: datetime | None = None


class ScenarioOut(BaseModel):
    id: str
    title: str
    flow: str
    request: str | None = None
    expect: dict[str, Any] = Field(default_factory=dict)


class ScenarioRunOut(BaseModel):
    id: str
    title: str
    passed: bool
    observed: dict[str, Any] = Field(default_factory=dict)
    failed: list[str] = Field(default_factory=list)


class EvalRunOut(BaseModel):
    batch_id: str
    total: int
    passed: int
    unsafe_blocked: int
    results: list[ScenarioRunOut]


class EvalResultsOut(BaseModel):
    batch_id: str | None = None
    total: int
    passed: int
    unsafe_blocked: int
    results: list[ScenarioRunOut]
