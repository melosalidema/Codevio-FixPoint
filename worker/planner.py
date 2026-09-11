from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.schemas import ParsedFacts, ProposedAction, RunContext


@dataclass
class Resolution:
    customers: list[dict[str, Any]] = field(default_factory=list)
    contact: dict[str, Any] | None = None
    charges: list[dict[str, Any]] = field(default_factory=list)
    policy: dict[str, Any] | None = None
    duplicate_charge_ids: list[str] = field(default_factory=list)

    @property
    def ambiguous(self) -> bool:
        return len(self.customers) > 1

    @property
    def resolved_customer(self) -> dict[str, Any] | None:
        if len(self.customers) == 1:
            return self.customers[0]
        return None


def propose(facts: ParsedFacts, resolution: Resolution, ctx: RunContext) -> ProposedAction | None:
    if facts.requested_action != "refund":
        return None
    if not resolution.charges:
        return None

    target: dict[str, Any] | None = None
    if facts.amount_cents is not None:
        for charge in resolution.charges:
            if charge["amount_cents"] == facts.amount_cents:
                target = charge
                break
    if target is None and resolution.duplicate_charge_ids:
        for charge in resolution.charges:
            if charge["id"] in resolution.duplicate_charge_ids:
                target = charge
                break
    if target is None:
        target = resolution.charges[0]

    amount = facts.amount_cents if facts.amount_cents is not None else target["amount_cents"]
    params: dict[str, Any] = {
        "charge_id": target["id"],
        "amount_cents": int(amount),
        "reason": "duplicate charge" if target["id"] in resolution.duplicate_charge_ids else "policy_exception",
    }
    if facts.destination:
        params["destination"] = facts.destination

    return ProposedAction(
        tool="stripe.refund",
        params=params,
        justification=f"Customer requested refund for order {facts.order_id or 'n/a'}",
        evidence_refs=[f"stripe:{target['id']}"],
    )
