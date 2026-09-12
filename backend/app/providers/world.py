from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ProviderError(Exception):
    """Typed provider failure (status codes drive retry decisions)."""

    def __init__(self, provider: str, status: int, message: str) -> None:
        super().__init__(f"{provider} error {status}: {message}")
        self.provider = provider
        self.status = status
        self.message = message


@dataclass
class Customer:
    id: str
    email: str
    name: str
    tenant_id: str


@dataclass
class Charge:
    id: str
    customer_id: str
    amount_cents: int
    tenant_id: str
    status: str = "succeeded"
    refunded_cents: int = 0


@dataclass
class Contact:
    id: str
    email: str
    name: str
    tenant_id: str
    status: str = "open"
    notes: list[str] = field(default_factory=list)
    owner: str = "unassigned"


@dataclass
class Draft:
    id: str
    to: str
    subject: str
    body: str
    tenant_id: str
    sent: bool = False


@dataclass
class Document:
    id: str
    name: str
    content: str
    version_hash: str
    tenant_id: str


class StripeTwin:
    """Billing twin with idempotent refunds and injectable failures."""

    def __init__(self, world: World) -> None:
        self._world = world
        self.failures_remaining = 0
        self.failure_status = 500
        self.fail_refund_remaining = 0
        self._refund_keys: dict[str, str] = {}

    def list_customers(
        self, tenant_id: str, email: str | None = None, name: str | None = None
    ) -> list[Customer]:
        self._maybe_fail()
        out = []
        for customer in self._world.customers.values():
            if customer.tenant_id != tenant_id:
                continue
            if email and customer.email.lower() == email.lower():
                out.append(customer)
            elif name and name.lower() in customer.name.lower():
                out.append(customer)
            elif not email and not name:
                out.append(customer)
        return out

    def get_customer(self, tenant_id: str, customer_id: str) -> Customer | None:
        customer = self._world.customers.get(customer_id)
        if customer and customer.tenant_id == tenant_id:
            return customer
        return None

    def list_charges(self, tenant_id: str, customer_id: str | None = None) -> list[Charge]:
        self._maybe_fail()
        return [
            charge
            for charge in self._world.charges.values()
            if charge.tenant_id == tenant_id and (customer_id is None or charge.customer_id == customer_id)
        ]

    def get_charge(self, tenant_id: str, charge_id: str) -> Charge | None:
        charge = self._world.charges.get(charge_id)
        if charge and charge.tenant_id == tenant_id:
            return charge
        return None

    def refund(
        self, tenant_id: str, charge_id: str, amount_cents: int, idempotency_key: str
    ) -> dict[str, Any]:
        self._maybe_fail()
        if self.fail_refund_remaining > 0:
            self.fail_refund_remaining -= 1
            raise ProviderError("stripe", self.failure_status, "injected refund failure")
        existing = self._refund_keys.get(idempotency_key)
        if existing:
            return {"id": existing, "charge_id": charge_id, "amount_cents": amount_cents, "duplicate": True}
        charge = self.get_charge(tenant_id, charge_id)
        if charge is None:
            raise ProviderError("stripe", 404, "charge not found for tenant")
        if charge.refunded_cents + amount_cents > charge.amount_cents:
            raise ProviderError("stripe", 400, "refund exceeds charge amount")
        charge.refunded_cents += amount_cents
        charge.status = "refunded" if charge.refunded_cents == charge.amount_cents else "partially_refunded"
        refund_id = f"re_{len(self._refund_keys) + 1:04d}"
        self._refund_keys[idempotency_key] = refund_id
        return {"id": refund_id, "charge_id": charge_id, "amount_cents": amount_cents, "duplicate": False}

    def _maybe_fail(self) -> None:
        if self.failures_remaining > 0:
            self.failures_remaining -= 1
            raise ProviderError("stripe", self.failure_status, "injected failure")


class GmailTwin:
    """Email twin. Draft-only by contract: it exposes no send method."""

    def __init__(self, world: World) -> None:
        self._world = world
        self.failures_remaining = 0

    def read_thread(self, tenant_id: str, thread_id: str) -> list[dict[str, Any]]:
        self._maybe_fail()
        return [m for m in self._world.threads if m["tenant_id"] == tenant_id and m["thread_id"] == thread_id]

    def create_draft(self, tenant_id: str, to: str, subject: str, body: str, thread_id: str = "") -> Draft:
        self._maybe_fail()
        draft = Draft(
            id=f"draft_{len(self._world.drafts) + 1:04d}",
            to=to,
            subject=subject,
            body=body,
            tenant_id=tenant_id,
        )
        self._world.drafts.append(draft)
        return draft

    def _maybe_fail(self) -> None:
        if self.failures_remaining > 0:
            self.failures_remaining -= 1
            raise ProviderError("gmail", 500, "injected failure")


class SlackTwin:
    """Slack twin pinned to an allow-list of channels."""

    ALLOWED_CHANNELS = {"#fixpoint-audit", "#refund-approvals"}

    def __init__(self, world: World) -> None:
        self._world = world
        self.failures_remaining = 0

    def post_message(self, tenant_id: str, channel: str, text: str) -> dict[str, Any]:
        self._maybe_fail()
        if channel not in self.ALLOWED_CHANNELS:
            raise ProviderError("slack", 403, f"channel {channel} not allowed")
        message = {"tenant_id": tenant_id, "channel": channel, "text": text}
        self._world.slack.append(message)
        return message

    def _maybe_fail(self) -> None:
        if self.failures_remaining > 0:
            self.failures_remaining -= 1
            raise ProviderError("slack", 500, "injected failure")


class CrmTwin:
    """CRM twin (HubSpot-shaped) for notes and contact status."""

    def __init__(self, world: World) -> None:
        self._world = world

    def find_contacts(
        self, tenant_id: str, email: str | None = None, name: str | None = None
    ) -> list[Contact]:
        out = []
        for contact in self._world.contacts.values():
            if contact.tenant_id != tenant_id:
                continue
            if email and contact.email.lower() == email.lower():
                out.append(contact)
            elif name and name.lower() in contact.name.lower():
                out.append(contact)
        return out

    def add_note(self, tenant_id: str, contact_id: str, body: str) -> Contact:
        contact = self._world.contacts.get(contact_id)
        if contact is None or contact.tenant_id != tenant_id:
            raise ProviderError("hubspot", 404, "contact not found")
        contact.notes.append(body)
        return contact

    def update_status(self, tenant_id: str, contact_id: str, status: str) -> Contact:
        contact = self._world.contacts.get(contact_id)
        if contact is None or contact.tenant_id != tenant_id:
            raise ProviderError("hubspot", 404, "contact not found")
        contact.status = status
        return contact


class DriveTwin:
    """Read-only document twin (policy docs, evidence)."""

    def __init__(self, world: World) -> None:
        self._world = world

    def get_document(self, tenant_id: str, file_id: str) -> Document | None:
        document = self._world.documents.get(file_id)
        if document and document.tenant_id == tenant_id:
            return document
        return None


class World:
    """A resettable set of provider twins with one shared seed."""

    def __init__(self, seed: dict[str, Any] | None = None) -> None:
        self.customers: dict[str, Customer] = {}
        self.charges: dict[str, Charge] = {}
        self.contacts: dict[str, Contact] = {}
        self.documents: dict[str, Document] = {}
        self.threads: list[dict[str, Any]] = []
        self.drafts: list[Draft] = []
        self.slack: list[dict[str, Any]] = []
        self.stripe = StripeTwin(self)
        self.gmail = GmailTwin(self)
        self.slack_api = SlackTwin(self)
        self.crm = CrmTwin(self)
        self.drive = DriveTwin(self)
        self.reset(seed or {})

    def reset(self, seed: dict[str, Any] | None = None) -> None:
        seed = seed or {}
        self.customers = {
            c["id"]: Customer(c["id"], c["email"], c["name"], c["tenant_id"])
            for c in seed.get("customers", [])
        }
        self.charges = {
            c["id"]: Charge(
                c["id"],
                c["customer_id"],
                c["amount_cents"],
                c["tenant_id"],
                c.get("status", "succeeded"),
                c.get("refunded_cents", 0),
            )
            for c in seed.get("charges", [])
        }
        self.contacts = {
            c["id"]: Contact(
                c["id"],
                c["email"],
                c["name"],
                c["tenant_id"],
                c.get("status", "open"),
                list(c.get("notes", [])),
                c.get("owner", "unassigned"),
            )
            for c in seed.get("contacts", [])
        }
        self.documents = {
            d["id"]: Document(d["id"], d["name"], d["content"], d["version_hash"], d["tenant_id"])
            for d in seed.get("documents", [])
        }
        self.threads = list(seed.get("threads", []))
        self.drafts = []
        self.slack = []
        self.stripe.failures_remaining = 0
        self.stripe.failure_status = 500
        self.stripe.fail_refund_remaining = 0
        self.stripe._refund_keys = {}
        self.gmail.failures_remaining = 0
        self.slack_api.failures_remaining = 0

    def snapshot(self) -> dict[str, Any]:
        """A compact, serializable view of provider state for the UI diff."""
        return {
            "charges": {
                cid: {"status": c.status, "refunded_cents": c.refunded_cents, "amount_cents": c.amount_cents}
                for cid, c in self.charges.items()
            },
            "contacts": {
                cid: {"status": c.status, "notes": len(c.notes), "owner": c.owner}
                for cid, c in self.contacts.items()
            },
            "drafts": [{"id": d.id, "to": d.to, "sent": d.sent} for d in self.drafts],
            "slack": list(self.slack),
        }
