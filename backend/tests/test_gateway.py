from __future__ import annotations

from app.safety import gateway
from app.safety.approval import issue_token
from app.safety.canonical import action_hash
from app.safety.gateway import TOOL_CONTRACTS
from app.safety.models import Decision, GatewayState, ProposedAction, RunContext


def refund(amount: int = 4200, **params):
    base = {"charge_id": "ch_100", "amount_cents": amount, "reason": "duplicate"}
    base.update(params)
    return ProposedAction(tool="stripe.refund", params=base)


def test_unknown_tool_rejected(ctx, state):
    decision = gateway.evaluate(ProposedAction(tool="http.fetch", params={"url": "x"}), ctx, state)
    assert decision.decision == Decision.REJECT
    assert decision.reason == "unknown_tool"


def test_capability_not_granted(ctx, state):
    limited = ctx.model_copy(update={"capabilities": ["stripe.read"]})
    decision = gateway.evaluate(refund(), limited, state)
    assert decision.decision == Decision.REJECT
    assert decision.reason == "capability_not_granted"


def test_cross_tenant_rejected(ctx, state):
    decision = gateway.evaluate(refund(tenant_id="t_evil"), ctx, state)
    assert decision.decision == Decision.REJECT
    assert decision.reason == "cross_tenant"


def test_field_allowlist(ctx, state):
    decision = gateway.evaluate(refund(routing_number="123"), ctx, state)
    assert decision.decision == Decision.REJECT
    assert decision.reason == "field_not_allowed"


def test_secret_in_params(ctx, state):
    decision = gateway.evaluate(refund(card_number="4242424242424242"), ctx, state)
    assert decision.decision == Decision.REJECT
    assert decision.reason == "secret_in_params"


def test_destination_not_pinned(ctx, state):
    decision = gateway.evaluate(refund(destination="card_9999"), ctx, state)
    assert decision.decision == Decision.REJECT
    assert decision.reason == "destination_not_pinned"


def test_charge_not_pinned(ctx, state):
    decision = gateway.evaluate(refund(charge_id="ch_evil"), ctx, state)
    assert decision.decision == Decision.REJECT
    assert decision.reason == "charge_not_pinned"


def test_forbidden_op(ctx, state, monkeypatch):
    monkeypatch.setitem(
        TOOL_CONTRACTS, "records.delete", {"capability": "crm.write", "fields": {"id"}, "money": False}
    )
    decision = gateway.evaluate(ProposedAction(tool="records.delete", params={"id": "con_1"}), ctx, state)
    assert decision.decision == Decision.REJECT
    assert decision.reason == "forbidden_op"


def test_within_autonomous_envelope_allows(ctx, state):
    decision = gateway.evaluate(refund(amount=2000), ctx, state)
    assert decision.decision == Decision.ALLOW
    assert decision.reason == "within_autonomous_envelope"


def test_over_threshold_requires_team_lead(ctx, state):
    decision = gateway.evaluate(refund(amount=4200), ctx, state)
    assert decision.decision == Decision.REQUIRE_APPROVAL
    assert decision.required_role == "team_lead"


def test_over_dual_threshold_requires_two(ctx, state):
    decision = gateway.evaluate(refund(amount=100000), ctx, state)
    assert decision.decision == Decision.REQUIRE_APPROVAL
    assert decision.required_role == "finance"
    assert decision.required_approvals == 1
    decision = gateway.evaluate(refund(amount=300000), ctx, state)
    assert decision.required_role == "finance_dual"
    assert decision.required_approvals == 2
    assert decision.separation_of_duties is True
    assert decision.over_cap is True


def test_valid_approval_allows_once(ctx):
    action = refund(amount=4200)
    token = issue_token(ctx, action_hash(action), "team_lead", 4200)
    state = GatewayState(
        allowed_charges={"ch_100"},
        allowed_destinations={"ch_100"},
        approval=token,
    )
    decision = gateway.evaluate(action, ctx, state)
    assert decision.decision == Decision.ALLOW
    assert decision.reason == "approval_valid"


def test_approval_amount_mismatch_blocks(ctx):
    action = refund(amount=4200)
    token = issue_token(ctx, action_hash(action), "team_lead", 9999)
    state = GatewayState(allowed_charges={"ch_100"}, allowed_destinations={"ch_100"}, approval=token)
    decision = gateway.evaluate(action, ctx, state)
    assert decision.decision == Decision.REQUIRE_APPROVAL
    assert decision.reason == "approval_state_changed"


def test_expired_approval_blocks(ctx):
    action = refund(amount=4200)
    token = issue_token(ctx, action_hash(action), "team_lead", 4200, ttl_seconds=-10)
    state = GatewayState(allowed_charges={"ch_100"}, allowed_destinations={"ch_100"}, approval=token)
    decision = gateway.evaluate(action, ctx, state)
    assert decision.decision == Decision.REQUIRE_APPROVAL
    assert decision.reason == "approval_expired"


def test_idempotent_duplicate_is_noop(ctx, state):
    action = refund(amount=2000)
    first = gateway.evaluate(action, ctx, state)
    assert first.decision == Decision.ALLOW
    gateway.record_execution(action, state, first.idempotency_key)
    second = gateway.evaluate(action, ctx, state)
    assert second.decision == Decision.NOOP
    assert second.reason == "duplicate"


def test_velocity_limit(ctx, state):
    action = refund(amount=2000)
    state.action_counts["stripe.refund"] = ctx.envelope.max_actions_per_run
    decision = gateway.evaluate(action, ctx, state)
    assert decision.decision == Decision.REJECT
    assert decision.reason == "velocity_exceeded"


def test_low_risk_non_money_allowed(ctx, state):
    action = ProposedAction(tool="slack.post", params={"channel": "#fixpoint-audit", "text": "hi"})
    decision = gateway.evaluate(action, ctx, state)
    assert decision.decision == Decision.ALLOW


def test_context_unchanged_by_model(ctx: RunContext):
    assert ctx.tenant_id == "t_123"
