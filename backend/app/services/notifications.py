"""Outbound decision notifications (Formspree email).

Every refund decision funnels through :mod:`app.services.run_service`:
autonomous completion inside a run, and human approve/deny on a paused run.
This module turns those into a Formspree submission that emails the linked
inbox, so operators hear about approvals and denials even when nobody is
watching the console.

Delivery is fire-and-forget and strictly best-effort: a notification failure is
logged and can never change a run's outcome, move money, or block a response.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger("fixpoint.notifications")

# Outcomes that count as an approval (money moved) or a denial (no money moved).
APPROVED_OUTCOMES = {"completed", "completed_after_approval"}
DENIED_OUTCOMES = {
    "denied_by_human",
    "approval_rejected_role",
    "approval_rejected_sod",
    "approval_voided",
}

# The event loop keeps only weak references to tasks; hold strong ones until
# delivery finishes so a notification can never be garbage-collected mid-flight.
_inflight: set[asyncio.Task[None]] = set()


def format_usd(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def decision_fields(
    *,
    decision: str,
    outcome: str,
    run_id: str,
    request_text: str,
    facts: dict[str, Any] | None,
    amount_cents: int,
    actor: str = "",
    role: str = "",
    automatic: bool = False,
    trigger: str = "api",
) -> dict[str, str]:
    """Build the Formspree submission for one decision (pure, testable)."""
    facts = facts or {}
    order_id = str(facts.get("order_id") or "")
    customer_email = str(facts.get("customer_email") or "")
    label = "Refund approved" if decision == "approved" else "Refund denied"
    decided_by = "Fixpoint agent (automatic)" if automatic else (actor or "unknown operator")

    return {
        "event": f"refund_{decision}",
        "subject": f"{label} · {format_usd(amount_cents)}" + (f" · order {order_id}" if order_id else ""),
        # Sets the notification's Reply-To, so the operator can answer the customer.
        "email": customer_email,
        "decision": decision,
        "outcome": outcome,
        "run_id": run_id,
        "order_id": order_id,
        "customer_email": customer_email,
        "amount_display": format_usd(amount_cents),
        "amount_cents": str(amount_cents),
        "decided_by": decided_by,
        "role": role,
        "automatic": "true" if automatic else "false",
        "trigger": trigger,
        "request_text": request_text,
    }


def schedule_decision_notification(fields: dict[str, str]) -> None:
    """Queue one best-effort Formspree notification (no-op when disabled)."""
    settings = get_settings()
    if not settings.notify_formspree_enabled or not settings.notify_formspree_form_id:
        return
    task = asyncio.create_task(_post_to_formspree(fields))
    _inflight.add(task)
    task.add_done_callback(_inflight.discard)


def notify_decision(
    *,
    decision: str,
    outcome: str,
    run_id: str,
    request_text: str,
    facts: dict[str, Any] | None,
    amount_cents: int,
    actor: str = "",
    role: str = "",
    automatic: bool = False,
    trigger: str = "api",
) -> None:
    schedule_decision_notification(
        decision_fields(
            decision=decision,
            outcome=outcome,
            run_id=run_id,
            request_text=request_text,
            facts=facts,
            amount_cents=amount_cents,
            actor=actor,
            role=role,
            automatic=automatic,
            trigger=trigger,
        )
    )


async def _post_to_formspree(fields: dict[str, str]) -> None:
    settings = get_settings()
    url = f"https://formspree.io/f/{settings.notify_formspree_form_id}"
    try:
        async with httpx.AsyncClient(timeout=settings.notify_formspree_timeout_seconds) as client:
            response = await client.post(
                url,
                json={**fields, "_gotcha": ""},
                headers={"Accept": "application/json"},
            )
        if response.status_code >= 400:
            logger.warning(
                "formspree notification rejected (%s): %s", response.status_code, response.text[:200]
            )
        else:
            logger.info(
                "formspree notification sent: %s run=%s", fields.get("event"), fields.get("run_id")
            )
    except Exception as error:  # noqa: BLE001 - a notification must never break a run
        logger.warning("formspree notification failed: %s", error)
