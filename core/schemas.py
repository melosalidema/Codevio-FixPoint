from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Decision(str, Enum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    REJECT = "REJECT"
    NOOP = "NOOP"


class Envelope(BaseModel):
    max_refund_cents: int = 250_000
    approval_threshold_cents: int = 10_000
    auto_approve_cents: int = 2_500
    team_lead_cents: int = 25_000
    dual_approval_cents: int = 250_000
    forbidden_ops: list[str] = Field(default_factory=lambda: ["delete", "send_external", "public_share"])
    max_actions_per_run: int = 20


class RunContext(BaseModel):
    run_id: str
    tenant_id: str
    actor_user_id: str
    trigger: str = "unknown"
    capabilities: list[str] = Field(default_factory=list)
    envelope: Envelope = Field(default_factory=Envelope)


class ProposedAction(BaseModel):
    tool: str
    params: dict[str, Any] = Field(default_factory=dict)
    justification: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class ApprovalToken(BaseModel):
    run_id: str
    tenant_id: str
    action_hash: str
    approver_role_required: str
    amount_cents: int
    expiry: int
    nonce: str
    single_use: bool = True
    signature: str = ""


class GatewayState(BaseModel):
    allowed_charges: set[str] = Field(default_factory=set)
    allowed_destinations: set[str] = Field(default_factory=set)
    seen_idempotency_keys: set[str] = Field(default_factory=set)
    action_counts: dict[str, int] = Field(default_factory=dict)
    approval: ApprovalToken | None = None


class GatewayDecision(BaseModel):
    decision: Decision
    reason: str
    required_role: str | None = None
    action_hash: str = ""
    idempotency_key: str = ""
    over_cap: bool = False
    required_approvals: int = 1
    separation_of_duties: bool = False


class ApprovalArtifact(BaseModel):
    run_id: str
    tenant_id: str
    action: ProposedAction
    action_hash: str
    amount_cents: int
    required_role: str
    required_approvals: int = 1
    separation_of_duties: bool = False
    facts: dict[str, Any] = Field(default_factory=dict)
    untrusted_justification: str = ""
    status: Literal["pending", "approved", "denied", "void"] = "pending"
    token: ApprovalToken | None = None


class ParsedFacts(BaseModel):
    customer_email: str | None = None
    customer_name: str | None = None
    order_id: str | None = None
    requested_action: Literal["refund", "store_credit", "deny", "unknown"] = "unknown"
    amount_cents: int | None = None
    destination: str | None = None
    injection_flags: list[str] = Field(default_factory=list)
    raw_excerpt: str = ""


class LedgerType(str, Enum):
    PLAN = "plan"
    PROPOSAL = "proposal"
    GATEWAY_DECISION = "gateway_decision"
    TOOL_CALL = "tool_call"
    MUTATION = "mutation"
    APPROVAL = "approval"
    VERIFICATION = "verification"
    UNSAFE_BLOCKED = "unsafe_blocked"
    REPORT = "report"


class LedgerEntry(BaseModel):
    seq: int
    run_id: str
    type: LedgerType
    payload: dict[str, Any]
    prev_hash: str
    hash: str


class CheckResult(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class VerificationResult(BaseModel):
    run_id: str
    passed: bool
    checks: list[CheckResult] = Field(default_factory=list)
    unsafe_mutations: int = 0
    synced_systems: list[str] = Field(default_factory=list)

    def failed_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


class RunReport(BaseModel):
    run_id: str
    tenant_id: str
    status: Literal["completed", "awaiting_approval", "denied", "failed"]
    outcome: str
    verified: bool = False
    unsafe_blocked: int = 0
    approval_artifact: ApprovalArtifact | None = None
    report_text: str = ""
    claims: list[str] = Field(default_factory=list)
    grounded_claims: list[str] = Field(default_factory=list)
    ungrounded_claims: list[str] = Field(default_factory=list)
