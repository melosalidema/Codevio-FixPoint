from __future__ import annotations

from typing import Any

from app.safety.approval import verify_token
from app.safety.canonical import action_hash, idempotency_key, tenant_of
from app.safety.models import (
    Decision,
    GatewayDecision,
    GatewayState,
    ProposedAction,
    RunContext,
)

# Parameter names that must never enter a tool call.
SENSITIVE_KEYS = {
    "card_number",
    "cvv",
    "cvc",
    "pan",
    "password",
    "secret",
    "api_key",
    "private_key",
    "refresh_token",
    "access_token",
}

# The complete allow-list of tools, their capability, and their allowed fields.
# Anything not in this table is rejected by default.
TOOL_CONTRACTS: dict[str, dict[str, Any]] = {
    "stripe.read": {
        "capability": "stripe.read",
        "fields": {"customer_id", "email", "charge_id", "tenant_id"},
        "money": False,
    },
    "stripe.refund": {
        "capability": "stripe.refund",
        "fields": {"charge_id", "amount_cents", "reason", "tenant_id", "destination", "idempotency_key"},
        "money": True,
    },
    "crm.note": {
        "capability": "crm.write",
        "fields": {"contact_id", "body", "tenant_id"},
        "money": False,
    },
    "crm.update": {
        "capability": "crm.write",
        "fields": {"contact_id", "status", "owner", "tenant_id"},
        "money": False,
    },
    "email.create_draft": {
        "capability": "email.draft",
        "fields": {"to", "subject", "body", "thread_id", "tenant_id"},
        "money": False,
    },
    "slack.post": {
        "capability": "slack.post",
        "fields": {"channel", "text", "tenant_id"},
        "money": False,
    },
    "drive.read": {
        "capability": "drive.read",
        "fields": {"file_id", "tenant_id"},
        "money": False,
    },
}

FORBIDDEN_TOKENS = {"delete", "destroy", "send_external", "send", "public_share", "share_public", "drop"}


def required_approval(amount_cents: int, ctx: RunContext, over_cap: bool) -> tuple[str, int, bool]:
    """Map an amount to (role, number of approvals, separation of duties)."""
    env = ctx.envelope
    if over_cap or amount_cents > env.dual_approval_cents:
        return "finance_dual", 2, True
    if amount_cents > env.team_lead_cents:
        return "finance", 1, False
    if amount_cents > env.auto_approve_cents:
        return "team_lead", 1, False
    return "none", 0, False


def _reject(reason: str, action: ProposedAction, key: str = "", **extra: Any) -> GatewayDecision:
    return GatewayDecision(
        decision=Decision.REJECT,
        reason=reason,
        action_hash=action_hash(action),
        idempotency_key=key,
        **extra,
    )


def _require_approval(
    reason: str,
    action: ProposedAction,
    key: str,
    role: str,
    approvals: int,
    sod: bool,
    over_cap: bool,
) -> GatewayDecision:
    return GatewayDecision(
        decision=Decision.REQUIRE_APPROVAL,
        reason=reason,
        required_role=role,
        action_hash=action_hash(action),
        idempotency_key=key,
        over_cap=over_cap,
        required_approvals=approvals,
        separation_of_duties=sod,
    )


def evaluate(
    action: ProposedAction,
    ctx: RunContext,
    state: GatewayState | None = None,
    now: int | None = None,
) -> GatewayDecision:
    """Deny-by-default policy enforcement point.

    Check order is deliberate: identity and scope first, then data safety,
    then economics, then human authorization. Every check is deterministic.
    """
    state = state or GatewayState()
    key = idempotency_key(ctx.run_id, action.tool, action.params)
    h = action_hash(action)

    contract = TOOL_CONTRACTS.get(action.tool)
    if contract is None:
        return _reject("unknown_tool", action, key)

    if contract["capability"] not in ctx.capabilities:
        return _reject("capability_not_granted", action, key)

    # Tenant binding: the model may name a tenant, but never change authority.
    tenant = tenant_of(action.params)
    if tenant is not None and tenant != ctx.tenant_id:
        return _reject("cross_tenant", action, key)

    lowered = action.tool.lower()
    if lowered in ctx.envelope.forbidden_ops or any(tok in lowered for tok in FORBIDDEN_TOKENS):
        return _reject("forbidden_op", action, key)

    if any(k.lower() in SENSITIVE_KEYS for k in action.params):
        return _reject("secret_in_params", action, key)

    extra_fields = set(action.params) - set(contract["fields"])
    if extra_fields:
        return _reject("field_not_allowed", action, key)

    if contract["money"]:
        destination = action.params.get("destination")
        if destination is not None and destination not in state.allowed_destinations:
            return _reject("destination_not_pinned", action, key)
        charge_id = action.params.get("charge_id")
        if charge_id is not None and charge_id not in state.allowed_charges:
            return _reject("charge_not_pinned", action, key)

    count = state.action_counts.get(action.tool, 0)
    if count >= ctx.envelope.max_actions_per_run:
        return _reject("velocity_exceeded", action, key)

    if key in state.seen_idempotency_keys:
        return GatewayDecision(
            decision=Decision.NOOP,
            reason="duplicate",
            action_hash=h,
            idempotency_key=key,
        )

    if not contract["money"]:
        return GatewayDecision(
            decision=Decision.ALLOW, reason="low_risk_autonomous", action_hash=h, idempotency_key=key
        )

    amount = int(action.params.get("amount_cents", 0))
    if amount <= 0:
        return _reject("invalid_amount", action, key)

    over_cap = amount > ctx.envelope.max_refund_cents
    role, approvals, sod = required_approval(amount, ctx, over_cap)

    if role == "none" and not over_cap:
        return GatewayDecision(
            decision=Decision.ALLOW,
            reason="within_autonomous_envelope",
            action_hash=h,
            idempotency_key=key,
        )

    token = state.approval
    if token is None:
        return _require_approval(
            "over_cap" if over_cap else "over_threshold", action, key, role, approvals, sod, over_cap
        )

    valid, why = verify_token(token, now=now)
    if not valid:
        return _require_approval(f"approval_{why}", action, key, role, approvals, sod, over_cap)
    if token.action_hash != h:
        return _require_approval("approval_action_mismatch", action, key, role, approvals, sod, over_cap)
    if token.amount_cents != amount or token.tenant_id != ctx.tenant_id:
        return _require_approval("approval_state_changed", action, key, role, approvals, sod, over_cap)

    return GatewayDecision(
        decision=Decision.ALLOW,
        reason="approval_valid",
        required_role=role,
        action_hash=h,
        idempotency_key=key,
        over_cap=over_cap,
        required_approvals=approvals,
        separation_of_duties=sod,
    )


def record_execution(action: ProposedAction, state: GatewayState, key: str) -> GatewayState:
    """Record a successful mutation for idempotency and velocity accounting."""
    state.seen_idempotency_keys.add(key)
    state.action_counts[action.tool] = state.action_counts.get(action.tool, 0) + 1
    return state
