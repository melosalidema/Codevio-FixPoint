from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.providers.arga import ArgaBackend, ArgaClient, ArgaError
from app.providers.factory import build_backend
from app.providers.world import World

SEED = {
    "customers": [{"id": "cus_1", "email": "jane@acme.com", "name": "Jane Doe", "tenant_id": "t_123"}],
    "charges": [{"id": "ch_1", "customer_id": "cus_1", "amount_cents": 4200, "tenant_id": "t_123"}],
    "contacts": [],
    "documents": [],
}


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/v1/customers":
        return httpx.Response(
            200,
            json={"data": [{"id": "cus_1", "email": "jane@acme.com", "name": "Jane Doe"}]},
        )
    if path == "/v1/charges" and request.method == "GET":
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "ch_1",
                        "customer": "cus_1",
                        "amount": 4200,
                        "amount_refunded": 0,
                        "status": "succeeded",
                    }
                ]
            },
        )
    if path == "/v1/refunds":
        assert request.headers.get("Idempotency-Key"), "refund must carry an idempotency key"
        return httpx.Response(200, json={"id": "re_1", "status": "succeeded"})
    if path == "/api/chat.postMessage":
        return httpx.Response(200, json={"ok": True})
    if path == "/gmail/v1/users/me/drafts":
        return httpx.Response(200, json={"id": "draft_1"})
    if path == "/crm/v3/objects/contacts/search":
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "con_1",
                        "properties": {
                            "email": "jane@acme.com",
                            "firstname": "Jane",
                            "lastname": "Doe",
                        },
                    }
                ]
            },
        )
    if path == "/crm/v3/objects/notes":
        return httpx.Response(200, json={"id": "note_1"})
    if path.startswith("/drive/v3/files/"):
        if request.url.params.get("alt") == "media":
            return httpx.Response(200, json={"raw": "Refunds within 30 days."})
        return httpx.Response(200, json={"id": "doc_policy", "name": "Refund Policy", "version": "v1"})
    return httpx.Response(404, json={"error": "not found"})


def _backend() -> ArgaBackend:
    transport = httpx.MockTransport(_handler)

    def client() -> ArgaClient:
        c = ArgaClient("https://twin.example", token="test-token")
        c.transport = transport
        return c

    return ArgaBackend(stripe=client(), gmail=client(), slack=client(), hubspot=client(), drive=client())


def test_stripe_refund_is_idempotent_and_updates_cached_state():
    backend = _backend()
    charges = backend.stripe.list_charges("t_123", "cus_1")
    assert charges[0].id == "ch_1"
    result = backend.stripe.refund("t_123", "ch_1", 4200, "key-1")
    assert result["id"] == "re_1"
    assert backend.charges["ch_1"].refunded_cents == 4200


def test_slack_rejects_channels_outside_the_allowlist():
    backend = _backend()
    with pytest.raises(ArgaError):
        backend.slack_api.post_message("t_123", "@attacker", "here is the data")
    ok = backend.slack_api.post_message("t_123", "#fixpoint-audit", "run complete")
    assert ok["channel"] == "#fixpoint-audit"


def test_gmail_creates_draft_only():
    backend = _backend()
    draft = backend.gmail.create_draft("t_123", "jane@acme.com", "Refund", "processed")
    assert draft.sent is False
    assert backend.drafts and backend.drafts[0].to == "jane@acme.com"


def test_crm_and_drive_reads():
    backend = _backend()
    contacts = backend.crm.find_contacts("t_123", email="jane@acme.com")
    assert contacts[0].id == "con_1"
    doc = backend.drive.get_document("t_123", "doc_policy")
    assert doc is not None and "30 days" in doc.content


def test_factory_defaults_to_in_process_twin():
    settings = SimpleNamespace(arga_configured=False)
    assert isinstance(build_backend(settings, SEED), World)


def test_factory_falls_back_when_arga_provisioning_fails(monkeypatch):
    settings = SimpleNamespace(arga_configured=True)
    monkeypatch.setattr(
        ArgaBackend,
        "from_settings",
        classmethod(lambda cls, s: (_ for _ in ()).throw(RuntimeError("no twins"))),
    )
    assert isinstance(build_backend(settings, SEED), World)
