"""Arga digital-twin provider backend (env-gated, HTTP).

Arga twins are stateful, API-compatible replicas of Stripe, Gmail, Slack,
HubSpot and Google Drive. This backend implements the same surface the agent
uses against the in-process twins (``app.providers.world.World``) so the engine,
adapters and verifier are unchanged.

Enabled with ``FIXPOINT_PROVIDER_BACKEND=arga`` plus per-service URLs/tokens
written by ``scripts/arga_provision.py``. If it is not configured, or the Arga
CLI/twins are unavailable, the deterministic in-process twins remain the default
and the app still runs with zero external dependencies.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.providers.world import NoteRecord, RefundRecord, SlackTwin

# ---- view objects mirroring the in-process twins ------------------------------


@dataclass
class ArgaCustomer:
    id: str
    email: str
    name: str
    tenant_id: str


@dataclass
class ArgaCharge:
    id: str
    customer_id: str
    amount_cents: int
    tenant_id: str
    status: str = "succeeded"
    refunded_cents: int = 0


@dataclass
class ArgaContact:
    id: str
    email: str
    name: str
    tenant_id: str
    status: str = "open"
    notes: list[str] = field(default_factory=list)
    owner: str = "unassigned"


@dataclass
class ArgaDraft:
    id: str
    to: str
    subject: str
    body: str
    tenant_id: str
    sent: bool = False


@dataclass
class ArgaDocument:
    id: str
    name: str
    content: str
    version_hash: str
    tenant_id: str


class ArgaError(RuntimeError):
    pass


class ArgaClient:
    """Thin httpx wrapper for one twin service."""

    def __init__(self, base_url: str, token: str = "", timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.transport: httpx.BaseTransport | None = None  # injectable for tests

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        return self._request("GET", path, params=params, headers=headers)

    def post_json(self, path: str, body: dict[str, Any], headers: dict[str, str] | None = None) -> Any:
        merged = {**self._headers(), "Content-Type": "application/json", **(headers or {})}
        return self._request("POST", path, json_body=body, headers=merged)

    def post_form(self, path: str, data: dict[str, Any], headers: dict[str, str] | None = None) -> Any:
        merged = {**self._headers(), "Content-Type": "application/x-www-form-urlencoded", **(headers or {})}
        return self._request("POST", path, form=data, headers=merged)

    def _request(self, method: str, path: str, **kw: Any) -> Any:
        url = f"{self.base_url}{path}"
        headers = kw.pop("headers", None) or self._headers()
        request_kwargs: dict[str, Any] = {}
        if kw.get("params") is not None:
            request_kwargs["params"] = kw["params"]
        if kw.get("json_body") is not None:
            request_kwargs["json"] = kw["json_body"]
        if kw.get("form") is not None:
            request_kwargs["data"] = kw["form"]
        try:
            with httpx.Client(transport=self.transport, timeout=self.timeout) as client:
                response = client.request(method, url, headers=headers, **request_kwargs)
        except httpx.HTTPError as error:
            raise ArgaError(f"transport_error: {error}") from error
        if response.status_code >= 400:
            raise ArgaError(f"http_{response.status_code}: {response.text[:200]}")
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}


class StripeArga:
    supports_failure_injection = True

    def __init__(self, client: ArgaClient, cache: dict[str, ArgaCharge] | None = None) -> None:
        self.client = client
        self.fail_refund_remaining = 0  # parity with the in-process twin
        self._cache = cache if cache is not None else {}
        self.refunds: list[RefundRecord] = []

    def list_customers(
        self, tenant_id: str, email: str | None = None, name: str | None = None
    ) -> list[ArgaCustomer]:
        params = {"email": email} if email else ({"name": name} if name else None)
        data = self.client.get("/v1/customers", params=params)
        return [
            ArgaCustomer(c["id"], c.get("email") or "", c.get("name") or "", tenant_id)
            for c in data.get("data", [])
        ]

    def list_charges(self, tenant_id: str, customer_id: str | None = None) -> list[ArgaCharge]:
        params = {"customer": customer_id} if customer_id else None
        data = self.client.get("/v1/charges", params=params)
        charges = [self._charge(c, tenant_id) for c in data.get("data", [])]
        for charge in charges:
            self._cache[charge.id] = charge
        return charges

    def get_charge(self, tenant_id: str, charge_id: str) -> ArgaCharge | None:
        try:
            data = self.client.get(f"/v1/charges/{charge_id}")
        except ArgaError:
            return None
        charge = self._charge(data, tenant_id)
        self._cache[charge.id] = charge
        return charge

    def refund(
        self,
        tenant_id: str,
        charge_id: str,
        amount_cents: int,
        idempotency_key: str,
        *,
        run_id: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        data = self.client.post_form(
            "/v1/refunds",
            {"charge": charge_id, "amount": amount_cents},
            headers={"Idempotency-Key": idempotency_key},
        )
        cached = self._cache.get(charge_id)
        if cached is not None and data.get("status") != "duplicate":
            cached.refunded_cents += amount_cents
            cached.status = (
                "refunded" if cached.refunded_cents >= cached.amount_cents else "partially_refunded"
            )
        refund_id = data.get("id", "")
        if refund_id:
            self.refunds.append(
                RefundRecord(
                    id=refund_id,
                    charge_id=charge_id,
                    amount_cents=amount_cents,
                    tenant_id=tenant_id,
                    status=str(data.get("status", "succeeded") or "succeeded"),
                    currency=str(data.get("currency", "usd")),
                    reason=reason,
                    metadata={"run_id": run_id} if run_id else {},
                )
            )
        return {
            "id": data.get("id", ""),
            "charge_id": charge_id,
            "amount_cents": amount_cents,
            "duplicate": data.get("status") == "duplicate",
        }

    def list_refunds(self, tenant_id: str, charge_id: str) -> list[RefundRecord]:
        data = self.client.get("/v1/refunds", params={"charge": charge_id})
        return [self._refund(row, tenant_id, charge_id) for row in data.get("data", [])]

    def list_subscriptions(self, tenant_id: str, customer_id: str) -> list[dict[str, Any]]:
        data = self.client.get("/v1/subscriptions", params={"customer": customer_id, "status": "all"})
        return [
            {
                "id": row.get("id", ""),
                "customer_id": customer_id,
                "status": row.get("status", ""),
                "currency": row.get("currency", "usd"),
                "created": row.get("created"),
                "items": row.get("items", {}),
                "metadata": row.get("metadata", {}),
            }
            for row in data.get("data", [])
        ]

    @staticmethod
    def _refund(data: dict[str, Any], tenant_id: str, charge_id: str) -> RefundRecord:
        return RefundRecord(
            id=data.get("id", ""),
            charge_id=data.get("charge", charge_id),
            amount_cents=int(data.get("amount", 0)),
            tenant_id=tenant_id,
            status=data.get("status", "succeeded"),
            currency=data.get("currency", "usd"),
            reason=data.get("reason", "") or "",
            created=data.get("created"),
            metadata=dict(data.get("metadata", {}) or {}),
        )

    @staticmethod
    def _charge(data: dict[str, Any], tenant_id: str) -> ArgaCharge:
        amount = data.get("amount", data.get("amount_cents", 0))
        refunded = data.get("amount_refunded", 0)
        return ArgaCharge(
            id=data.get("id", ""),
            customer_id=data.get("customer", ""),
            amount_cents=int(amount),
            tenant_id=tenant_id,
            status=data.get("status", "succeeded"),
            refunded_cents=int(refunded),
        )


class GmailArga:
    def __init__(self, client: ArgaClient) -> None:
        self.client = client
        self._drafts: list[ArgaDraft] = []

    def create_draft(
        self, tenant_id: str, to: str, subject: str, body: str, thread_id: str = ""
    ) -> ArgaDraft:
        raw = base64.urlsafe_b64encode(
            f"To: {to}\r\nSubject: {subject}\r\n\r\n{body}".encode()
        ).decode()
        payload: dict[str, Any] = {"message": {"raw": raw}}
        if thread_id:
            payload["message"]["threadId"] = thread_id
        data = self.client.post_json("/gmail/v1/users/me/drafts", payload)
        draft_id = data.get("id", f"draft_{len(self._drafts) + 1:04d}")
        draft = ArgaDraft(id=draft_id, to=to, subject=subject, body=body, tenant_id=tenant_id)
        self._drafts.append(draft)
        return draft

    @property
    def drafts(self) -> list[ArgaDraft]:
        return self._drafts


class SlackArga:
    def __init__(self, client: ArgaClient) -> None:
        self.client = client
        self._messages: list[dict[str, Any]] = []

    def post_message(self, tenant_id: str, channel: str, text: str) -> dict[str, Any]:
        if channel not in SlackTwin.ALLOWED_CHANNELS:
            raise ArgaError(f"channel {channel} not allowed")
        self.client.post_json("/api/chat.postMessage", {"channel": channel, "text": text})
        message = {"tenant_id": tenant_id, "channel": channel, "text": text}
        self._messages.append(message)
        return message

    @property
    def messages(self) -> list[dict[str, Any]]:
        return self._messages


class CrmArga:
    def __init__(self, client: ArgaClient) -> None:
        self.client = client
        self._notes: dict[str, list[str]] = {}
        self._contacts: dict[str, ArgaContact] = {}

    def find_contacts(
        self, tenant_id: str, email: str | None = None, name: str | None = None
    ) -> list[ArgaContact]:
        filters = []
        if email:
            filters.append({"propertyName": "email", "operator": "EQ", "value": email})
        if name:
            filters.append({"propertyName": "firstname", "operator": "CONTAINS_TOKEN", "value": name})
        body = {"filterGroups": [{"filters": filters}]} if filters else {"filterGroups": []}
        data = self.client.post_json("/crm/v3/objects/contacts/search", body)
        contacts = []
        for row in data.get("results", []):
            props = row.get("properties", {}) or {}
            contact = ArgaContact(
                id=str(row.get("id", "")),
                email=props.get("email", ""),
                name=f"{props.get('firstname', '')} {props.get('lastname', '')}".strip(),
                tenant_id=tenant_id,
                notes=list(self._notes.get(str(row.get("id", "")), [])),
            )
            self._contacts[contact.id] = contact
            contacts.append(contact)
        return contacts

    def add_note(self, tenant_id: str, contact_id: str, body: str) -> ArgaContact:
        # Mirror HubSpot: create the note and associate it with the contact
        # (note_to_contact type id 202) so it appears on the record.
        self.client.post_json(
            "/crm/v3/objects/notes",
            {
                "properties": {"hs_note_body": body},
                "associations": [
                    {
                        "to": {"id": contact_id},
                        "types": [
                            {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}
                        ],
                    }
                ],
            },
        )
        self._notes.setdefault(contact_id, []).append(body)
        contact = self._contacts.get(contact_id)
        if contact is None:
            contact = ArgaContact(id=contact_id, email="", name="", tenant_id=tenant_id)
            self._contacts[contact_id] = contact
        contact.notes = list(self._notes[contact_id])
        return contact

    def list_notes(self, tenant_id: str, contact_id: str) -> list[NoteRecord]:
        """Fresh read: association lookup, then a batch read of the notes."""
        associations = self.client.get(f"/crm/v4/objects/contacts/{contact_id}/associations/notes")
        note_ids = [
            str(row.get("toObjectId") or row.get("id") or "")
            for row in associations.get("results", [])
        ]
        note_ids = [note_id for note_id in note_ids if note_id]
        if not note_ids:
            return []
        data = self.client.post_json(
            "/crm/v3/objects/notes/batch/read",
            {"inputs": [{"id": note_id} for note_id in note_ids], "properties": ["hs_note_body"]},
        )
        return [
            NoteRecord(
                id=str(row.get("id", "")),
                contact_id=contact_id,
                body=str((row.get("properties") or {}).get("hs_note_body") or ""),
                tenant_id=tenant_id,
                created=row.get("createdAt"),
            )
            for row in data.get("results", [])
        ]

    def update_status(self, tenant_id: str, contact_id: str, status: str) -> ArgaContact:
        self.client.post_json(f"/crm/v3/objects/contacts/{contact_id}", {"properties": {"status": status}})
        contact = self._contacts.get(contact_id)
        if contact is None:
            contact = ArgaContact(id=contact_id, email="", name="", tenant_id=tenant_id)
            self._contacts[contact_id] = contact
        contact.status = status
        return contact

    @property
    def contacts(self) -> dict[str, ArgaContact]:
        return self._contacts


class DriveArga:
    def __init__(self, client: ArgaClient) -> None:
        self.client = client

    def get_document(self, tenant_id: str, file_id: str) -> ArgaDocument | None:
        try:
            meta = self.client.get(f"/drive/v3/files/{file_id}", params={"fields": "id,name,version"})
            content = self.client.get(f"/drive/v3/files/{file_id}", params={"alt": "media"})
        except ArgaError:
            return None
        return ArgaDocument(
            id=file_id,
            name=meta.get("name", file_id),
            content=content.get("raw", "") if isinstance(content, dict) else str(content),
            version_hash=str(meta.get("version", "")),
            tenant_id=tenant_id,
        )


class ArgaBackend:
    """A World-compatible facade backed by Arga twins."""

    def __init__(
        self,
        *,
        stripe: ArgaClient,
        gmail: ArgaClient,
        slack: ArgaClient,
        hubspot: ArgaClient,
        drive: ArgaClient,
    ) -> None:
        self._charges: dict[str, ArgaCharge] = {}
        self.stripe = StripeArga(stripe, cache=self._charges)
        self.gmail = GmailArga(gmail)
        self.slack_api = SlackArga(slack)
        self.crm = CrmArga(hubspot)
        self.drive = DriveArga(drive)

    @classmethod
    def from_settings(cls, settings: Any) -> ArgaBackend:
        return cls(
            stripe=ArgaClient(settings.arga_stripe_url, settings.arga_stripe_token),
            gmail=ArgaClient(settings.arga_gmail_url, settings.arga_gmail_token),
            slack=ArgaClient(settings.arga_slack_url, settings.arga_slack_token),
            hubspot=ArgaClient(settings.arga_hubspot_url, settings.arga_hubspot_token),
            drive=ArgaClient(settings.arga_drive_url, settings.arga_drive_token),
        )

    @property
    def charges(self) -> dict[str, ArgaCharge]:
        return self._charges

    @property
    def contacts(self) -> dict[str, ArgaContact]:
        return self.crm.contacts

    @property
    def drafts(self) -> list[ArgaDraft]:
        return self.gmail.drafts

    @property
    def slack(self) -> list[dict[str, Any]]:
        return self.slack_api.messages

    def snapshot(self) -> dict[str, Any]:
        return {
            "charges": {
                cid: {"status": c.status, "refunded_cents": c.refunded_cents, "amount_cents": c.amount_cents}
                for cid, c in self._charges.items()
            },
            "contacts": {
                cid: {"status": c.status, "notes": len(c.notes), "owner": c.owner}
                for cid, c in self.contacts.items()
            },
            "drafts": [{"id": d.id, "to": d.to, "sent": d.sent} for d in self.drafts],
            "slack": list(self.slack),
        }
