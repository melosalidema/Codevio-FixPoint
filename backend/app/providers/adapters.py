from __future__ import annotations

from typing import Any

from app.providers.world import World
from app.safety.models import ProposedAction, RunContext


class AdapterSet:
    """Tenant-scoped view of every provider.

    The sealed :class:`RunContext` is injected here, so provider calls always
    use the server-side tenant id. Model arguments never select a tenant or
    supply credentials.
    """

    def __init__(self, world: World, ctx: RunContext) -> None:
        self.world = world
        self.ctx = ctx

    @property
    def tenant_id(self) -> str:
        return self.ctx.tenant_id

    def resolve_customer(self, email: str | None = None, name: str | None = None) -> list[dict[str, Any]]:
        customers = self.world.stripe.list_customers(self.tenant_id, email=email, name=name)
        return [{"id": c.id, "email": c.email, "name": c.name} for c in customers]

    def crm_contacts(self, email: str | None = None, name: str | None = None) -> list[dict[str, Any]]:
        contacts = self.world.crm.find_contacts(self.tenant_id, email=email, name=name)
        return [
            {"id": c.id, "email": c.email, "name": c.name, "status": c.status, "owner": c.owner}
            for c in contacts
        ]

    def list_notes(self, contact_id: str) -> list[dict[str, Any]]:
        """Notes associated with one contact (fresh read for live HubSpot)."""
        notes = self.world.crm.list_notes(self.tenant_id, contact_id)
        return [
            {
                "id": note.id,
                "contact_id": note.contact_id,
                "body": note.body,
                "created": note.created,
            }
            for note in notes
        ]

    def list_charges(self, customer_id: str) -> list[dict[str, Any]]:
        charges = self.world.stripe.list_charges(self.tenant_id, customer_id)
        return [
            {
                "id": c.id,
                "customer_id": c.customer_id,
                "amount_cents": c.amount_cents,
                "status": c.status,
                "refunded_cents": c.refunded_cents,
            }
            for c in charges
        ]

    def get_charge(self, charge_id: str) -> dict[str, Any] | None:
        charge = self.world.stripe.get_charge(self.tenant_id, charge_id)
        if charge is None:
            return None
        return {
            "id": charge.id,
            "customer_id": charge.customer_id,
            "amount_cents": charge.amount_cents,
            "status": charge.status,
            "refunded_cents": charge.refunded_cents,
        }

    def list_refunds(self, charge_id: str) -> list[dict[str, Any]]:
        """Refunds recorded against one charge (fresh read for live Stripe)."""
        refunds = self.world.stripe.list_refunds(self.tenant_id, charge_id)
        return [
            {
                "id": refund.id,
                "charge_id": refund.charge_id,
                "amount_cents": refund.amount_cents,
                "status": refund.status,
                "currency": refund.currency,
                "reason": refund.reason,
            }
            for refund in refunds
        ]

    def list_subscriptions(self, customer_id: str) -> list[dict[str, Any]]:
        """Subscription state is evidence-only in v1 (no policy rules).

        A provider error (for example a restricted key without subscription
        read) degrades to empty evidence rather than failing the refund path.
        """
        if not hasattr(self.world.stripe, "list_subscriptions"):
            return []
        try:
            return self.world.stripe.list_subscriptions(self.tenant_id, customer_id)
        except Exception:  # noqa: BLE001 - evidence-only; never blocks the run
            return []

    def read_policy(self, file_id: str) -> dict[str, Any] | None:
        document = self.world.drive.get_document(self.tenant_id, file_id)
        if document is None:
            return None
        return {
            "id": document.id,
            "name": document.name,
            "content": document.content,
            "hash": document.version_hash,
        }

    def execute(self, action: ProposedAction, idempotency_key: str = "") -> dict[str, Any]:
        """Execute an already-authorized action.

        This method must only be reached after the Action Gateway returned
        ALLOW; the engine enforces that ordering.
        """
        tool = action.tool
        params = action.params
        if tool == "stripe.read":
            if params.get("charge_id"):
                return {"charge": self.get_charge(params["charge_id"])}
            return {"customers": self.resolve_customer(params.get("email"))}
        if tool == "stripe.refund":
            result = self.world.stripe.refund(
                self.tenant_id,
                params["charge_id"],
                int(params["amount_cents"]),
                idempotency_key or f"{params['charge_id']}:{params['amount_cents']}",
                run_id=self.ctx.run_id,
                reason=str(params.get("reason", "")),
            )
            return {"refund": result}
        if tool == "crm.note":
            contact = self.world.crm.add_note(self.tenant_id, params["contact_id"], params["body"])
            return {"contact_id": contact.id, "notes": len(contact.notes)}
        if tool == "crm.update":
            contact = self.world.crm.update_status(self.tenant_id, params["contact_id"], params["status"])
            return {"contact_id": contact.id, "status": contact.status}
        if tool == "email.create_draft":
            draft = self.world.gmail.create_draft(
                self.tenant_id,
                params["to"],
                params.get("subject", ""),
                params.get("body", ""),
                params.get("thread_id", ""),
            )
            return {"draft_id": draft.id, "to": draft.to, "sent": draft.sent}
        if tool == "slack.post":
            message = self.world.slack_api.post_message(self.tenant_id, params["channel"], params["text"])
            return {"posted": True, "channel": message["channel"]}
        if tool == "drive.read":
            return {"document": self.read_policy(params["file_id"])}
        raise ValueError(f"no adapter for tool {tool}")
