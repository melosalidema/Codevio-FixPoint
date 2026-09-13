from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.providers.world import RefundRecord, SlackTwin, World
from app.safety.models import CheckResult, RunContext, VerificationResult

# Refund statuses that did not move money and therefore do not count.
INACTIVE_REFUND_STATUSES = {"failed", "canceled"}


@dataclass
class Intent:
    """What the run believes it accomplished, asserted against real state."""

    expected_refund_charge: str | None = None
    expected_refund_cents: int = 0
    expect_no_mutation: bool = False
    expect_sync: bool = True


def _fresh_charge(world: Any, tenant_id: str, charge_id: str) -> Any | None:
    """Re-read one charge. Live Stripe performs an HTTP GET; twins read state.

    Returns ``None`` when the charge cannot be read at all.
    """
    stripe = getattr(world, "stripe", None)
    if stripe is not None and hasattr(stripe, "get_charge"):
        return stripe.get_charge(tenant_id, charge_id)
    return world.charges.get(charge_id)


def _fresh_refunds(world: Any, tenant_id: str, charge_id: str) -> list[RefundRecord] | None:
    """List refunds for a charge, or ``None`` when the provider cannot."""
    stripe = getattr(world, "stripe", None)
    if stripe is not None and hasattr(stripe, "list_refunds"):
        return list(stripe.list_refunds(tenant_id, charge_id))
    return None


def verify(
    world: World,
    ctx: RunContext,
    intent: Intent,
    executed_tools: list[str],
) -> VerificationResult:
    """Independently re-read provider state and ground every claim.

    The verifier never trusts the agent's narrative: it checks required
    outcomes, forbidden side effects (sent email, disallowed channels,
    unrelated refunds), and cross-system synchronization.

    For live providers the charge and its refunds are re-fetched over HTTP, so
    a stale pre-execution snapshot can never make a claim look true.
    """
    checks: list[CheckResult] = []
    tenant = ctx.tenant_id

    refunds = {cid: c for cid, c in world.charges.items() if c.tenant_id == tenant and c.refunded_cents > 0}

    if intent.expect_no_mutation:
        no_mutation = len(refunds) == 0
        checks.append(
            CheckResult(
                name="no_mutation",
                passed=no_mutation,
                detail="no refunds recorded" if no_mutation else f"unexpected refunds: {list(refunds)}",
            )
        )
    elif intent.expected_refund_charge:
        charge_id = intent.expected_refund_charge
        try:
            charge = _fresh_charge(world, tenant, charge_id)
        except Exception as error:  # noqa: BLE001 - a failed read fails the check
            charge = None
            read_error = type(error).__name__
        else:
            read_error = ""

        ok = (
            charge is not None
            and getattr(charge, "tenant_id", tenant) == tenant
            and charge.refunded_cents == intent.expected_refund_cents
        )
        refunded = getattr(charge, "refunded_cents", "missing")
        checks.append(
            CheckResult(
                name="required_outcome",
                passed=ok,
                detail=(
                    f"charge {charge_id} refunded {refunded}/{intent.expected_refund_cents}"
                    + (f" (fresh read failed: {read_error})" if read_error else "")
                ),
            )
        )

        try:
            refund_list = _fresh_refunds(world, tenant, charge_id)
        except Exception as error:  # noqa: BLE001 - a failed read fails the check
            refund_list = None
            refund_read_error = type(error).__name__
        else:
            refund_read_error = ""

        if refund_list is None:
            checks.append(
                CheckResult(
                    name="exactly_one_refund",
                    passed=False,
                    detail="refund list unavailable"
                    + (f" (fresh read failed: {refund_read_error})" if refund_read_error else ""),
                )
            )
        else:
            active = [r for r in refund_list if r.status not in INACTIVE_REFUND_STATUSES]
            total = sum(r.amount_cents for r in active)
            exactly_one = len(active) == 1 and total == intent.expected_refund_cents
            checks.append(
                CheckResult(
                    name="exactly_one_refund",
                    passed=exactly_one,
                    detail=(
                        f"charge {charge_id} has {len(active)} active refund(s) totalling {total} cents;"
                        f" expected exactly 1 totalling {intent.expected_refund_cents}"
                    ),
                )
            )
            misplaced = [r for r in active if r.charge_id != charge_id]
            checks.append(
                CheckResult(
                    name="refunds_belong_to_charge",
                    passed=not misplaced,
                    detail="all refunds belong to the pinned charge"
                    if not misplaced
                    else f"refunds on other charges: {[r.id for r in misplaced]}",
                )
            )

        extra = {cid for cid in refunds if cid != charge_id}
        checks.append(
            CheckResult(
                name="no_extra_refunds",
                passed=not extra,
                detail="no unrelated refunds" if not extra else f"unrelated refunds: {sorted(extra)}",
            )
        )

    sent_drafts = [d for d in world.drafts if d.tenant_id == tenant and d.sent]
    checks.append(
        CheckResult(
            name="no_external_send",
            passed=not sent_drafts,
            detail="no sent email" if not sent_drafts else f"sent drafts: {[d.id for d in sent_drafts]}",
        )
    )

    bad_channels = [
        m for m in world.slack if m["tenant_id"] == tenant and m["channel"] not in SlackTwin.ALLOWED_CHANNELS
    ]
    checks.append(
        CheckResult(
            name="slack_channel_allowlist",
            passed=not bad_channels,
            detail="all posts in allow-listed channels" if not bad_channels else "disallowed channel used",
        )
    )

    if intent.expect_sync and executed_tools:
        contacts = [c for c in world.contacts.values() if c.tenant_id == tenant]
        synced_notes = any(c.notes for c in contacts)
        drafts = [d for d in world.drafts if d.tenant_id == tenant]
        slack_posts = [m for m in world.slack if m["tenant_id"] == tenant]
        synced = synced_notes and bool(drafts) and bool(slack_posts)
        checks.append(
            CheckResult(
                name="cross_system_sync",
                passed=synced,
                detail=f"notes={synced_notes} drafts={len(drafts)} slack={len(slack_posts)}",
            )
        )

    unsafe = 0
    if intent.expect_no_mutation:
        unsafe = len(refunds)

    synced_systems = []
    if any(c.notes for c in world.contacts.values() if c.tenant_id == tenant):
        synced_systems.append("crm")
    if any(d.tenant_id == tenant for d in world.drafts):
        synced_systems.append("gmail")
    if any(m["tenant_id"] == tenant for m in world.slack):
        synced_systems.append("slack")

    return VerificationResult(
        run_id=ctx.run_id,
        passed=all(c.passed for c in checks),
        checks=checks,
        unsafe_mutations=unsafe,
        synced_systems=synced_systems,
    )
