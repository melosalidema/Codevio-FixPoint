from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.agent import planner as planner_module
from app.agent.parser import parse
from app.agent.planner import Resolution
from app.providers.adapters import AdapterSet
from app.providers.world import ProviderError, World
from app.safety import gateway
from app.safety.approval import issue_token
from app.safety.models import (
    ApprovalArtifact,
    Decision,
    GatewayState,
    LedgerType,
    ParsedFacts,
    ProposedAction,
    RunContext,
    RunReport,
)
from app.safety.verifier import Intent, verify

PlannerFn = Callable[[Any, Resolution, RunContext], ProposedAction | None]
ParserFn = Callable[[str], ParsedFacts]


class RunSession:
    """Deterministic orchestration of one run.

    The session is pure with respect to the outside world: provider state lives
    in the in-process :class:`World` twin, so the exact same request + seed
    always produces the exact same audit chain. That property is what makes
    approval replay after a restart safe.
    """

    def __init__(
        self,
        world: World,
        ctx: RunContext,
        request_text: str,
        policy_file_id: str | None = None,
        planner_fn: PlannerFn | None = None,
        parser_fn: ParserFn | None = None,
        planner_source: str = "deterministic",
    ) -> None:
        self.world = world
        self.ctx = ctx
        self.request_text = request_text
        self.policy_file_id = policy_file_id
        self.planner_fn = planner_fn or planner_module.propose
        self.parser_fn = parser_fn or parse
        self.planner_source = planner_source
        self.adapter = AdapterSet(world, ctx)
        self.state = GatewayState()
        self.facts = None
        self.resolution = Resolution()
        self.proposed: ProposedAction | None = None
        self.decision = None
        self.artifact: ApprovalArtifact | None = None
        self.executed_tools: list[str] = []
        self.unsafe_blocked = 0
        self.status = "pending"
        self.report: RunReport | None = None
        self.tool_errors: list[str] = []
        self.world_before: dict[str, Any] | None = None
        self._reset_intent()

    def _reset_intent(self) -> None:
        self.intent = Intent()

    # ------------------------------------------------------------------ audit
    def audit(self, entry_type: str, payload: dict[str, Any]) -> None:
        self._audit_log_append(LedgerType(entry_type), payload)

    def _audit_log_append(self, entry_type: LedgerType, payload: dict[str, Any]) -> None:
        if not hasattr(self, "audit_log"):
            from app.safety.audit import AuditLog

            self.audit_log = AuditLog()
        self.audit_log.append(self.ctx.run_id, entry_type, payload)

    # ----------------------------------------------------------- investigation
    def _investigate(self, facts: ParsedFacts) -> None:
        """Resolve the request against authoritative provider state."""
        self.facts = facts
        email = self.facts.customer_email
        customers = self.adapter.resolve_customer(email=email)
        contacts = self.adapter.crm_contacts(email=email)
        charges: list[dict[str, Any]] = []
        subscriptions: list[dict[str, Any]] = []
        for customer in customers:
            charges.extend(self.adapter.list_charges(customer["id"]))
            subscriptions.extend(self.adapter.list_subscriptions(customer["id"]))

        buckets: dict[int, list[str]] = {}
        for charge in charges:
            buckets.setdefault(charge["amount_cents"], []).append(charge["id"])
        duplicates = [cid for group in buckets.values() if len(group) >= 2 for cid in group]

        policy = None
        if self.policy_file_id:
            policy = self.adapter.read_policy(self.policy_file_id)

        self.resolution = Resolution(
            customers=customers,
            contact=contacts[0] if contacts else None,
            charges=charges,
            policy=policy,
            duplicate_charge_ids=duplicates,
            subscriptions=subscriptions,
        )

        # Pin the charges and destinations this run may touch. The gateway
        # rejects anything outside these sets, regardless of what the model says.
        allowed = [c["id"] for c in customers]
        self.state.allowed_charges = {c["id"] for c in charges}
        self.state.allowed_destinations = set(allowed) | self.state.allowed_charges

        self.audit(
            "plan",
            {
                "facts": self.facts.model_dump(),
                "customers": len(customers),
                "charges": len(charges),
                "subscriptions": len(subscriptions),
            },
        )

    # -------------------------------------------------------------- execution
    def _apply_decision(self, decision, token) -> None:
        self.decision = decision
        if decision.decision == Decision.ALLOW:
            self._execute(token)
        elif decision.decision == Decision.REQUIRE_APPROVAL:
            self._create_artifact(decision)
        elif decision.decision == Decision.REJECT:
            self.unsafe_blocked += 1
            self._audit_log_append(
                LedgerType.UNSAFE_BLOCKED, {"action": self.proposed.model_dump(), "reason": decision.reason}
            )
            if self.proposed and "refund" in self.proposed.tool:
                self._create_artifact(decision, escalate=True)

    def run(self) -> RunReport:
        facts = self.parser_fn(self.request_text)
        return self._run_with(facts, self.planner_fn)

    def replay_committed(self, facts: ParsedFacts, action: ProposedAction | None) -> RunReport:
        """Replay a run using the plan that was committed originally.

        This does not call the parser or planner, so the rebuilt audit chain is
        byte-identical to the stored one. That keeps approval binding valid and
        lets approve/deny run against the exact same action after a restart.
        """
        return self._run_with(facts, lambda *_: action)

    def _run_with(self, facts: ParsedFacts, planner_fn: PlannerFn) -> RunReport:
        self._investigate(facts)
        # Capture provider state after evidence gathering and before any
        # execution. For live providers this is the real pre-mutation state;
        # a pre-investigation snapshot would be empty/stale.
        self.world_before = self.world.snapshot() if hasattr(self.world, "snapshot") else None
        self.proposed = planner_fn(self.facts, self.resolution, self.ctx)
        if self.proposed is None:
            self.status = "failed"
            self._audit_log_append(LedgerType.PROPOSAL, {"action": None, "reason": "no_actionable_remedy"})
            return self._finalize(expect_no_mutation=True, outcome="no_actionable_remedy")

        # Untrusted content can never redirect money. If the request named a
        # destination, make sure the gateway always sees it even when the
        # planner omitted the field, so it is pinned or rejected deterministically.
        if (
            "refund" in self.proposed.tool
            and self.facts.destination
            and "destination" not in self.proposed.params
        ):
            self.proposed.params["destination"] = self.facts.destination

        self._audit_log_append(LedgerType.PROPOSAL, {"action": self.proposed.model_dump()})

        if self.resolution.ambiguous and "refund" in self.proposed.tool:
            self._create_artifact(
                gateway.evaluate(self.proposed, self.ctx, GatewayState()),
                escalate=True,
                reason="ambiguous_identity",
            )
            return self._finalize(expect_no_mutation=True, outcome="ambiguous_identity_escalated")

        decision = gateway.evaluate(self.proposed, self.ctx, self.state)
        self._audit_log_append(LedgerType.GATEWAY_DECISION, decision.model_dump())
        self._apply_decision(decision, token=None)

        if self.status == "awaiting_approval":
            return self._finalize(expect_no_mutation=True, outcome="awaiting_human_approval")
        if self.unsafe_blocked:
            return self._finalize(expect_no_mutation=True, outcome="unsafe_blocked")
        return self._finalize(expect_no_mutation=False, outcome="completed", executed=True)

    def approve(self, role: str, approver_user_id: str) -> RunReport:
        """Apply a human approval. Only a valid, bound token unlocks money."""
        if self.artifact is None or self.artifact.status != "pending":
            return self._finalize(expect_no_mutation=True, outcome="no_pending_approval")

        required = self.artifact.required_role
        if role != required and not (required == "team_lead" and role in {"finance", "finance_dual"}):
            self.artifact.status = "void"
            self.status = "failed"
            self._audit_log_append(
                LedgerType.APPROVAL,
                {"approver": approver_user_id, "role": role, "result": "insufficient_role"},
            )
            return self._finalize(expect_no_mutation=True, outcome="approval_rejected_role")

        # Separation of duties: the requester can never approve their own money.
        if self.artifact.separation_of_duties and approver_user_id == self.ctx.actor_user_id:
            self.artifact.status = "void"
            self.status = "failed"
            self._audit_log_append(
                LedgerType.APPROVAL,
                {"approver": approver_user_id, "result": "separation_of_duties_violation"},
            )
            return self._finalize(expect_no_mutation=True, outcome="approval_rejected_sod")

        token = issue_token(
            self.ctx,
            self.artifact.action_hash,
            self.artifact.required_role,
            self.artifact.amount_cents,
        )
        self.state.approval = token
        self.artifact.status = "approved"
        self.artifact.token = token
        self._audit_log_append(
            LedgerType.APPROVAL, {"approver": approver_user_id, "role": role, "result": "approved"}
        )

        decision = gateway.evaluate(self.proposed, self.ctx, self.state)
        self._audit_log_append(LedgerType.GATEWAY_DECISION, decision.model_dump())
        if decision.decision == Decision.ALLOW:
            self._apply_decision(decision, token)
            return self._finalize(expect_no_mutation=False, outcome="completed_after_approval", executed=True)
        self.artifact.status = "void"
        self.status = "failed"
        return self._finalize(expect_no_mutation=True, outcome="approval_voided")

    def deny(self, approver_user_id: str) -> RunReport:
        if self.artifact:
            self.artifact.status = "denied"
        self.status = "denied"
        self._audit_log_append(LedgerType.APPROVAL, {"approver": approver_user_id, "result": "denied"})
        self._sync_reconciliation("denied by approver")
        return self._finalize(expect_no_mutation=True, outcome="denied_by_human", reconcile=True)

    def _create_artifact(self, decision, escalate: bool = False, reason: str | None = None) -> None:
        if self.proposed is None:
            return
        amount = int(self.proposed.params.get("amount_cents", 0))
        role = decision.required_role
        if not role or role == "none":
            role = "finance"
        self.artifact = ApprovalArtifact(
            run_id=self.ctx.run_id,
            tenant_id=self.ctx.tenant_id,
            action=self.proposed,
            action_hash=decision.action_hash,
            amount_cents=amount,
            required_role=role,
            required_approvals=decision.required_approvals,
            separation_of_duties=decision.separation_of_duties,
            facts={
                "customers": self.resolution.customers,
                "charges": self.resolution.charges,
                "subscriptions": self.resolution.subscriptions,
                "policy_hash": (self.resolution.policy or {}).get("hash"),
            },
            untrusted_justification=self.proposed.justification,
            status="pending",
        )
        self.status = "awaiting_approval"
        self._audit_log_append(
            LedgerType.APPROVAL,
            {"artifact": self.artifact.model_dump(), "escalate": escalate, "reason": reason},
        )

    def _execute(self, token) -> None:
        assert self.proposed is not None
        key = self.decision.idempotency_key if self.decision else ""
        try:
            result = self.adapter.execute(self.proposed, key)
        except ProviderError as error:
            self.tool_errors.append(str(error))
            self._audit_log_append(
                LedgerType.TOOL_CALL, {"action": self.proposed.model_dump(), "error": str(error)}
            )
            if error.status >= 500:
                # Retry is safe here: the refund path is idempotent by key.
                result = self.adapter.execute(self.proposed, key)
            else:
                raise
        self.executed_tools.append(self.proposed.tool)
        gateway.record_execution(self.proposed, self.state, key)
        self._audit_log_append(LedgerType.MUTATION, {"action": self.proposed.model_dump(), "result": result})
        self.intent = Intent(
            expected_refund_charge=self.proposed.params.get("charge_id"),
            expected_refund_cents=int(self.proposed.params.get("amount_cents", 0)),
            expect_no_mutation=False,
            expect_sync=True,
        )
        self.status = "completed"
        self._sync()

    def _sync(self) -> None:
        """Trusted post-mutation synchronization (CRM note, Slack audit, draft)."""
        contact = self.resolution.contact
        if contact:
            try:
                self.adapter.execute(
                    ProposedAction(
                        tool="crm.note",
                        params={
                            "contact_id": contact["id"],
                            "body": f"Fixpoint run {self.ctx.run_id}: remedy executed.",
                        },
                    )
                )
                self._audit_log_append(
                    LedgerType.TOOL_CALL, {"tool": "crm.note", "contact_id": contact["id"]}
                )
            except ProviderError:
                pass
        try:
            self.adapter.execute(
                ProposedAction(
                    tool="slack.post",
                    params={"channel": "#fixpoint-audit", "text": f"run {self.ctx.run_id} completed"},
                )
            )
            self._audit_log_append(LedgerType.TOOL_CALL, {"tool": "slack.post", "channel": "#fixpoint-audit"})
        except ProviderError:
            pass
        email = self.facts.customer_email if self.facts else None
        if email:
            self.adapter.execute(
                ProposedAction(
                    tool="email.create_draft",
                    params={
                        "to": email,
                        "subject": "Your refund has been processed",
                        "body": "We have processed your refund. This is a draft for human review.",
                    },
                )
            )
            self._audit_log_append(LedgerType.TOOL_CALL, {"tool": "email.create_draft", "to": email})

    def _sync_reconciliation(self, note: str) -> None:
        contact = self.resolution.contact
        if contact:
            try:
                self.adapter.execute(
                    ProposedAction(
                        tool="crm.note",
                        params={
                            "contact_id": contact["id"],
                            "body": f"Fixpoint run {self.ctx.run_id}: {note}.",
                        },
                    )
                )
            except ProviderError:
                pass

    # ---------------------------------------------------------------- reports
    def _finalize(
        self, expect_no_mutation: bool, outcome: str, executed: bool = False, reconcile: bool = False
    ) -> RunReport:
        if expect_no_mutation:
            self.intent = Intent(
                expected_refund_charge=None, expected_refund_cents=0, expect_no_mutation=True
            )
        verification = verify(self.world, self.ctx, self.intent, self.executed_tools)
        self._audit_log_append(LedgerType.VERIFICATION, verification.model_dump())

        claims = self._build_claims(outcome, executed)
        grounded, ungrounded = self._ground_claims(claims, verification)

        if executed and verification.passed:
            status = "completed"
        elif self.status == "awaiting_approval":
            status = "awaiting_approval"
        elif outcome == "denied_by_human":
            status = "denied"
        else:
            status = "failed"

        report = RunReport(
            run_id=self.ctx.run_id,
            tenant_id=self.ctx.tenant_id,
            status=status,
            outcome=outcome,
            verified=verification.passed,
            unsafe_blocked=self.unsafe_blocked,
            approval_artifact=self.artifact,
            report_text=self._report_text(outcome, verification),
            claims=claims,
            grounded_claims=grounded,
            ungrounded_claims=ungrounded,
        )
        self._audit_log_append(
            LedgerType.REPORT, {"report": report.report_text, "verified": verification.passed}
        )
        self.report = report
        self.verification = verification
        return report

    def _build_claims(self, outcome: str, executed: bool) -> list[str]:
        claims = []
        if executed:
            claims.append(
                f"refund on {self.intent.expected_refund_charge} of {self.intent.expected_refund_cents} cents"
            )
            claims.append("crm note added")
            claims.append("slack audit posted")
            claims.append("gmail draft created")
        else:
            claims.append("no refund was executed")
        return claims

    def _ground_claims(self, claims: list[str], verification) -> tuple[list[str], list[str]]:
        """Only claims backed by a passing verification check are grounded."""
        grounded, ungrounded = [], []
        checks = {c.name: c.passed for c in verification.checks}
        for claim in claims:
            if claim.startswith("refund on"):
                (grounded if checks.get("required_outcome") else ungrounded).append(claim)
            elif claim == "no refund was executed":
                (grounded if checks.get("no_mutation") else ungrounded).append(claim)
            else:
                (grounded if checks.get("cross_system_sync") else ungrounded).append(claim)
        return grounded, ungrounded

    def _report_text(self, outcome: str, verification) -> str:
        if outcome in {
            "unsafe_blocked",
            "approval_rejected_role",
            "approval_rejected_sod",
            "approval_voided",
        }:
            return (
                "The requested action was refused by the safety gateway "
                "and logged as an unsafe-blocked event."
            )
        if outcome.startswith("ambiguous"):
            return "Identity was ambiguous; escalation artifact created and no money moved."
        if outcome == "awaiting_human_approval":
            return "Investigation complete. The money action is paused pending human approval."
        if outcome == "denied_by_human":
            return "The approver denied the action. No money moved; records reconciled."
        if verification.passed:
            return "Completed and independently verified against real system state."
        return "Completed with unverified claims; escalated for review."
