from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest

from app.providers.hubspot_live import HubSpotLive
from app.providers.world import ProviderError

TOKEN = "pat-test-token-not-a-secret"


def _client(handler: Any, *, max_retries: int = 2, status_property: str = "fixpoint_status") -> HubSpotLive:
    return HubSpotLive(
        TOKEN,
        status_property=status_property,
        max_retries=max_retries,
        transport=httpx.MockTransport(handler),
    )


def _contact_row(contact_id: str = "101", email: str = "jane@acme.com") -> dict[str, Any]:
    return {
        "id": contact_id,
        "properties": {
            "email": email,
            "firstname": "Jane",
            "lastname": "Doe",
            "hubspot_owner_id": "77",
            "fixpoint_status": "open",
        },
    }


def _silence_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.providers.hubspot_live.time.sleep", lambda _seconds: None)


# ------------------------------------------------------------------ search
def test_search_returns_every_match_with_filters():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/crm/v3/objects/contacts/search"
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        body = json.loads(request.content)
        assert body["filterGroups"] == [
            {"filters": [{"propertyName": "email", "operator": "EQ", "value": "jane@acme.com"}]}
        ]
        assert body["limit"] == 100
        assert "email" in body["properties"]
        return httpx.Response(200, json={"results": [_contact_row("101"), _contact_row("102")]})

    contacts = _client(handler).find_contacts("t_123", email="jane@acme.com")
    assert [c.id for c in contacts] == ["101", "102"]
    assert contacts[0].email == "jane@acme.com"
    assert contacts[0].name == "Jane Doe"
    assert contacts[0].status == "open"
    assert contacts[0].owner == "77"
    assert contacts[0].tenant_id == "t_123"


def test_search_zero_contacts():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    assert _client(handler).find_contacts("t_123", email="nobody@acme.com") == []


def test_search_paginates():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        body = json.loads(request.content)
        if body.get("after") == "cursor-1":
            return httpx.Response(200, json={"results": [_contact_row("102")]})
        assert "after" not in body
        return httpx.Response(
            200,
            json={"results": [_contact_row("101")], "paging": {"next": {"after": "cursor-1"}}},
        )

    contacts = _client(handler).find_contacts("t_123", email="jane@acme.com")
    assert [c.id for c in contacts] == ["101", "102"]
    assert calls["n"] == 2


def test_search_by_name_uses_query():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["filterGroups"] == []
        assert body["query"] == "Jane"
        return httpx.Response(200, json={"results": [_contact_row()]})

    contacts = _client(handler).find_contacts("t_123", name="Jane")
    assert len(contacts) == 1


# ---------------------------------------------------------------- contact
def test_get_contact_is_a_fresh_read():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert request.url.params["properties"]
        return httpx.Response(200, json=_contact_row("101"))

    client = _client(handler)
    contact = client.get_contact("t_123", "101")
    assert contact is not None and contact.id == "101"
    assert calls == ["/crm/v3/objects/contacts/101"]
    assert client.snapshot()["contacts"]["101"]["status"] == "open"


def test_get_contact_missing_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Contact not found"})

    assert _client(handler).get_contact("t_123", "missing") is None


# ------------------------------------------------------------------ notes
def test_add_note_payload_association_and_record():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/crm/v3/objects/notes"
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "note_1"})

    client = _client(handler)
    contact = client.add_note("t_123", "101", "Fixpoint run run_1: remedy executed.")
    body = captured["body"]
    assert body["properties"]["hs_note_body"] == "Fixpoint run run_1: remedy executed."
    assert isinstance(body["properties"]["hs_timestamp"], int)
    association = body["associations"][0]
    assert association["to"] == {"id": "101"}
    assert association["types"] == [
        {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}
    ]
    assert contact.id == "101"
    assert contact.notes == ["Fixpoint run run_1: remedy executed."]


def test_update_status_patches_configured_property():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        assert request.url.path == "/crm/v3/objects/contacts/101"
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_contact_row("101"))

    contact = _client(handler, status_property="fixpoint_status").update_status(
        "t_123", "101", "refunded"
    )
    assert captured["body"] == {"properties": {"fixpoint_status": "refunded"}}
    assert contact.status == "refunded"


def test_list_notes_uses_associations_then_batch_read():
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/crm/v4/objects/contacts/101/associations/notes":
            return httpx.Response(200, json={"results": [{"toObjectId": 901}, {"toObjectId": 902}]})
        assert request.url.path == "/crm/v3/objects/notes/batch/read"
        body = json.loads(request.content)
        assert body["inputs"] == [{"id": "901"}, {"id": "902"}]
        return httpx.Response(
            200,
            json={
                "results": [
                    {"id": "901", "properties": {"hs_note_body": "Fixpoint run run_1: remedy executed."}},
                    {"id": "902", "properties": {"hs_note_body": "unrelated note"}},
                ]
            },
        )

    notes = _client(handler).list_notes("t_123", "101")
    assert [n.id for n in notes] == ["901", "902"]
    assert notes[0].contact_id == "101"
    assert "run run_1" in notes[0].body
    assert calls == [
        ("GET", "/crm/v4/objects/contacts/101/associations/notes"),
        ("POST", "/crm/v3/objects/notes/batch/read"),
    ]


def test_list_notes_empty_associations_short_circuits():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/crm/v4/objects/contacts/101/associations/notes"
        return httpx.Response(200, json={"results": []})

    assert _client(handler).list_notes("t_123", "101") == []


# ----------------------------------------------------------------- errors
@pytest.mark.parametrize("status", [401, 403, 404, 500, 503])
def test_error_mapping(status):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={"message": "nope", "category": "VALIDATION_ERROR", "correlationId": "corr-1"},
        )

    with pytest.raises(ProviderError) as excinfo:
        # list_notes surfaces 404 (get_contact intentionally maps it to None).
        _client(handler, max_retries=0).list_notes("t_123", "101")
    assert excinfo.value.status == status
    assert "correlationId=corr-1" in str(excinfo.value)


# ------------------------------------------------------------------ retry
def test_rate_limit_honors_retry_after(monkeypatch):
    _silence_backoff(monkeypatch)
    sleeps: list[float] = []
    monkeypatch.setattr("app.providers.hubspot_live.time.sleep", sleeps.append)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"message": "rate limited"}, headers={"retry-after": "2"})
        return httpx.Response(200, json=_contact_row("101"))

    contact = _client(handler).get_contact("t_123", "101")
    assert contact is not None
    assert calls["n"] == 2
    assert sleeps == [2.0]


def test_reads_retry_on_5xx(monkeypatch):
    _silence_backoff(monkeypatch)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"message": "try later"})
        return httpx.Response(200, json=_contact_row("101"))

    contact = _client(handler, max_retries=2).get_contact("t_123", "101")
    assert contact is not None and calls["n"] == 3


def test_note_creation_is_not_retried_on_5xx(monkeypatch):
    _silence_backoff(monkeypatch)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, json={"message": "boom"})

    with pytest.raises(ProviderError):
        _client(handler, max_retries=3).add_note("t_123", "101", "note")
    # Note creation is not idempotent; the client must not replay it.
    assert calls["n"] == 1


def test_writes_retry_on_429(monkeypatch):
    _silence_backoff(monkeypatch)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"message": "rate limited"})
        return httpx.Response(201, json={"id": "note_1"})

    contact = _client(handler).add_note("t_123", "101", "note")
    assert contact.id == "101"
    assert calls["n"] == 2


# --------------------------------------------------------------- security
def test_token_never_logged_or_echoed(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "forbidden", "correlationId": "corr-2"})

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ProviderError) as excinfo:
            _client(handler, max_retries=0).get_contact("t_123", "101")

    assert TOKEN not in caplog.text
    assert TOKEN not in str(excinfo.value)
    assert "corr-2" in str(excinfo.value)
