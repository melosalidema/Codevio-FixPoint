"""Live HubSpot CRM provider (private-app token).

Synchronous ``httpx`` client matching the existing provider interface, so the
adapter set, engine and verifier are unchanged:

* resolve contacts by email (paginated; all matches returned so the engine can
  apply its generic ambiguity policy)
* fresh contact reads (the verifier never trusts a cache)
* create a note and associate it with the pinned contact (type id 202)
* optionally patch the configured status property
* list a contact's notes via the associations API for fresh verification

Safety notes:

* The private-app token is never logged, echoed in errors, or persisted.
* HubSpot has no test mode: a token writes to a real portal. Use a developer
  test account.
* Reads retry on 429/5xx; writes retry on 429 only (note creation is not
  idempotent, so a 5xx is surfaced instead of replayed).
* CRM-case intake is out of scope for v1 (private apps cannot sign webhooks).
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.providers.world import Contact, NoteRecord, ProviderError

logger = logging.getLogger("fixpoint.hubspot")

READ_RETRY_STATUS = {429, 500, 502, 503, 504}
WRITE_RETRY_STATUS = {429}
DEFAULT_PROPERTIES = ["email", "firstname", "lastname", "hubspot_owner_id"]
PAGE_SIZE = 100
MAX_PAGES = 20
NOTE_TO_CONTACT_TYPE_ID = 202


class HubSpotLive:
    """HubSpot CRM REST client scoped to one private app token."""

    def __init__(
        self,
        token: str,
        *,
        status_property: str = "fixpoint_status",
        timeout: float = 10.0,
        max_retries: int = 2,
        base_url: str = "https://api.hubapi.com",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not token:
            raise ValueError("HubSpotLive requires a private-app token")
        self.token = token
        self.status_property = status_property
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.base_url = base_url.rstrip("/")
        self.transport = transport  # injectable for tests
        self._seen: dict[str, Contact] = {}
        self._notes: dict[str, list[NoteRecord]] = {}

    @classmethod
    def from_settings(cls, settings: Any) -> HubSpotLive:
        if not settings.hubspot_token:
            raise ValueError("FIXPOINT_HUBSPOT_TOKEN is required for FIXPOINT_CRM_BACKEND=hubspot")
        return cls(
            settings.hubspot_token,
            status_property=settings.hubspot_status_property,
            timeout=settings.hubspot_timeout_seconds,
            max_retries=settings.hubspot_max_retries,
        )

    # ------------------------------------------------------------------ HTTP
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _client_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(self.timeout, connect=min(3.0, self.timeout))

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        is_write = method in {"POST", "PATCH", "PUT", "DELETE"}
        retry_status = WRITE_RETRY_STATUS if is_write else READ_RETRY_STATUS
        attempts = self.max_retries + 1 if method == "GET" or is_write else 1

        for attempt in range(attempts):
            try:
                with httpx.Client(transport=self.transport, timeout=self._client_timeout()) as client:
                    response = client.request(
                        method,
                        f"{self.base_url}{path}",
                        params=params,
                        json=json_body,
                        headers=self._headers(),
                    )
            except httpx.HTTPError as error:
                if attempt < attempts - 1:
                    time.sleep(0.2 * (2**attempt))
                    continue
                raise ProviderError(
                    "hubspot", 0, f"transport_error: {type(error).__name__}"
                ) from error

            if response.status_code in retry_status and attempt < attempts - 1:
                delay = self._retry_delay(response, attempt)
                logger.warning(
                    "hubspot %s %s -> %s; retrying in %.1fs", method, path, response.status_code, delay
                )
                time.sleep(delay)
                continue
            if response.status_code >= 400:
                raise ProviderError("hubspot", response.status_code, self._error_message(response))
            if not response.content:
                return {}
            try:
                body = response.json()
            except ValueError as error:
                raise ProviderError("hubspot", response.status_code, "malformed_response") from error
            if not isinstance(body, dict):
                raise ProviderError("hubspot", response.status_code, "malformed_response")
            return body

        raise ProviderError("hubspot", 0, "transport_error: exhausted")  # pragma: no cover

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        raw = response.headers.get("retry-after", "")
        try:
            return max(0.0, float(raw))
        except ValueError:
            return 0.2 * (2**attempt)

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            body = {}
        message = str(body.get("message") or response.reason_phrase or "hubspot_error")
        parts = [message]
        category = body.get("category")
        if category:
            parts.append(f"category={category}")
        correlation = body.get("correlationId")
        if correlation:
            parts.append(f"correlationId={correlation}")
        return "; ".join(parts)[:240]

    # ------------------------------------------------------------- contacts
    def _properties(self) -> list[str]:
        properties = list(DEFAULT_PROPERTIES)
        if self.status_property and self.status_property not in properties:
            properties.append(self.status_property)
        return properties

    def _contact(self, row: dict[str, Any], tenant_id: str) -> Contact:
        props = row.get("properties") or {}
        first = str(props.get("firstname") or "").strip()
        last = str(props.get("lastname") or "").strip()
        contact = Contact(
            id=str(row.get("id", "")),
            email=str(props.get("email") or ""),
            name=" ".join(part for part in (first, last) if part),
            tenant_id=tenant_id,
            status=str(props.get(self.status_property) or ""),
            notes=[note.body for note in self._notes.get(str(row.get("id", "")), [])],
            owner=str(props.get("hubspot_owner_id") or "unassigned"),
        )
        self._seen[contact.id] = contact
        return contact

    def find_contacts(
        self, tenant_id: str, email: str | None = None, name: str | None = None
    ) -> list[Contact]:
        """Return every matching contact; never silently pick the first."""
        filters = []
        if email:
            filters.append({"propertyName": "email", "operator": "EQ", "value": email})
        results: list[Contact] = []
        cursor: str | None = None
        for _ in range(MAX_PAGES):
            body: dict[str, Any] = {
                "filterGroups": [{"filters": filters}] if filters else [],
                "properties": self._properties(),
                "limit": PAGE_SIZE,
            }
            if name and not email:
                body["query"] = name
            if cursor:
                body["after"] = cursor
            data = self._request("POST", "/crm/v3/objects/contacts/search", json_body=body)
            rows = data.get("results") or []
            results.extend(self._contact(row, tenant_id) for row in rows)
            cursor = ((data.get("paging") or {}).get("next") or {}).get("after")
            if not cursor or not rows:
                break
        return results

    def get_contact(self, tenant_id: str, contact_id: str) -> Contact | None:
        """Genuinely fresh read; used by the verifier."""
        try:
            row = self._request(
                "GET",
                f"/crm/v3/objects/contacts/{contact_id}",
                params={"properties": ",".join(self._properties())},
            )
        except ProviderError as error:
            if error.status == 404:
                return None
            raise
        return self._contact(row, tenant_id)

    # ---------------------------------------------------------------- notes
    def add_note(self, tenant_id: str, contact_id: str, body: str) -> Contact:
        payload = {
            "properties": {
                "hs_note_body": body,
                "hs_timestamp": int(time.time() * 1000),
            },
            "associations": [
                {
                    "to": {"id": contact_id},
                    "types": [
                        {
                            "associationCategory": "HUBSPOT_DEFINED",
                            "associationTypeId": NOTE_TO_CONTACT_TYPE_ID,
                        }
                    ],
                }
            ],
        }
        data = self._request("POST", "/crm/v3/objects/notes", json_body=payload)
        note_id = str(data.get("id", ""))
        note = NoteRecord(
            id=note_id,
            contact_id=contact_id,
            body=body,
            tenant_id=tenant_id,
            created=int(time.time()),
        )
        self._notes.setdefault(contact_id, []).append(note)
        contact = self._seen.get(contact_id)
        if contact is None:
            contact = Contact(id=contact_id, email="", name="", tenant_id=tenant_id)
            self._seen[contact_id] = contact
        contact.notes = [record.body for record in self._notes[contact_id]]
        return contact

    def list_notes(self, tenant_id: str, contact_id: str) -> list[NoteRecord]:
        """Fresh read: association lookup, then a batch read of the notes."""
        associations = self._request(
            "GET", f"/crm/v4/objects/contacts/{contact_id}/associations/notes"
        )
        note_ids = [
            str(row.get("toObjectId") or row.get("id") or "")
            for row in associations.get("results", [])
        ]
        note_ids = [note_id for note_id in note_ids if note_id]
        if not note_ids:
            return []
        data = self._request(
            "POST",
            "/crm/v3/objects/notes/batch/read",
            json_body={
                "inputs": [{"id": note_id} for note_id in note_ids],
                "properties": ["hs_note_body", "hs_timestamp"],
            },
        )
        notes = [
            NoteRecord(
                id=str(row.get("id", "")),
                contact_id=contact_id,
                body=str((row.get("properties") or {}).get("hs_note_body") or ""),
                tenant_id=tenant_id,
                created=row.get("createdAt"),
            )
            for row in data.get("results", [])
        ]
        self._notes[contact_id] = notes
        contact = self._seen.get(contact_id)
        if contact is not None:
            contact.notes = [note.body for note in notes]
        return notes

    # --------------------------------------------------------------- status
    def update_status(self, tenant_id: str, contact_id: str, status: str) -> Contact:
        self._request(
            "PATCH",
            f"/crm/v3/objects/contacts/{contact_id}",
            json_body={"properties": {self.status_property: status}},
        )
        contact = self._seen.get(contact_id)
        if contact is None:
            contact = Contact(id=contact_id, email="", name="", tenant_id=tenant_id)
            self._seen[contact_id] = contact
        contact.status = status
        return contact

    # ------------------------------------------------------------ snapshots
    @property
    def contacts(self) -> dict[str, Contact]:
        return self._seen

    def snapshot(self) -> dict[str, Any]:
        return {
            "contacts": {
                cid: {"status": c.status, "notes": len(c.notes), "owner": c.owner}
                for cid, c in self._seen.items()
            }
        }
