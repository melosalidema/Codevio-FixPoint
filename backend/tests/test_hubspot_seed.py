from __future__ import annotations

import json
from typing import Any

import httpx

from app.providers.hubspot_live import HubSpotLive
from scripts import hubspot_seed

TOKEN = "pat-super-secret-token"


class SeedPortal:
    """Minimal stateful HubSpot portal for seeder tests."""

    def __init__(self) -> None:
        self.contacts: dict[str, dict[str, Any]] = {}
        self.next_id = 200
        self.properties: dict[str, dict[str, Any]] = {}
        self.creates = 0

    def add_contact(self, email: str, firstname: str = "Jane", lastname: str = "Doe") -> str:
        contact_id = str(self.next_id)
        self.next_id += 1
        self.contacts[contact_id] = {
            "id": contact_id,
            "properties": {"email": email, "firstname": firstname, "lastname": lastname},
        }
        return contact_id

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/crm/v3/objects/contacts/search":
            body = json.loads(request.content)
            email = body["filterGroups"][0]["filters"][0]["value"]
            matches = [
                row for row in self.contacts.values() if row["properties"]["email"] == email
            ]
            return httpx.Response(200, json={"results": matches})
        if request.method == "POST" and path == "/crm/v3/objects/contacts":
            body = json.loads(request.content)
            contact_id = str(self.next_id)
            self.next_id += 1
            self.contacts[contact_id] = {"id": contact_id, "properties": dict(body["properties"])}
            self.creates += 1
            return httpx.Response(201, json=self.contacts[contact_id])
        if request.method == "GET" and path.startswith("/crm/v3/objects/contacts/"):
            contact_id = path.rsplit("/", 1)[-1]
            row = self.contacts.get(contact_id)
            if row is None:
                return httpx.Response(404, json={"message": "not found"})
            return httpx.Response(200, json=row)
        if request.method == "GET" and path.startswith("/crm/v3/properties/contacts/"):
            name = path.rsplit("/", 1)[-1]
            if name not in self.properties:
                return httpx.Response(404, json={"message": "property missing"})
            return httpx.Response(200, json=self.properties[name])
        if request.method == "POST" and path == "/crm/v3/properties/contacts":
            body = json.loads(request.content)
            self.properties[body["name"]] = body
            return httpx.Response(201, json=body)
        return httpx.Response(404, json={"message": f"unhandled {request.method} {path}"})

    def client(self) -> HubSpotLive:
        return HubSpotLive(TOKEN, transport=httpx.MockTransport(self.handler))


def test_seed_creates_missing_contact(capsys):
    portal = SeedPortal()
    assert hubspot_seed.main(["--yes"], client=portal.client()) == 0
    assert portal.creates == 1
    contact = next(iter(portal.contacts.values()))
    assert contact["properties"]["email"] == "jane@acme.com"
    output = capsys.readouterr().out
    assert "Suggested Fixpoint run text" in output
    assert "jane@acme.com" in output


def test_seed_reuses_existing_contact():
    portal = SeedPortal()
    existing = portal.add_contact("jane@acme.com")
    assert hubspot_seed.main(["--yes"], client=portal.client()) == 0
    assert portal.creates == 0
    assert set(portal.contacts) == {existing}


def test_seed_with_duplicate_creates_second_contact():
    portal = SeedPortal()
    portal.add_contact("jane@acme.com")
    assert hubspot_seed.main(["--yes", "--with-duplicate"], client=portal.client()) == 0
    assert len(portal.contacts) == 2

    # Idempotent: a second run must not add a third contact.
    assert hubspot_seed.main(["--yes", "--with-duplicate"], client=portal.client()) == 0
    assert len(portal.contacts) == 2


def test_seed_creates_status_property_once():
    portal = SeedPortal()
    assert hubspot_seed.main(["--yes", "--create-status-property"], client=portal.client()) == 0
    assert "fixpoint_status" in portal.properties

    assert hubspot_seed.main(["--yes", "--create-status-property"], client=portal.client()) == 0
    assert list(portal.properties) == ["fixpoint_status"]


def test_seed_refuses_without_confirmation(monkeypatch):
    portal = SeedPortal()
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert hubspot_seed.main([], client=portal.client()) == 1
    assert portal.creates == 0 and not portal.contacts


def test_seed_never_prints_the_token(capsys):
    portal = SeedPortal()
    hubspot_seed.main(["--yes"], client=portal.client())
    output = capsys.readouterr().out
    assert TOKEN not in output


def test_seed_handles_provider_errors(capsys):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "forbidden", "correlationId": "corr-9"})

    client = HubSpotLive(TOKEN, transport=httpx.MockTransport(handler))
    assert hubspot_seed.main(["--yes"], client=client) == 1
    assert "forbidden" in capsys.readouterr().err
