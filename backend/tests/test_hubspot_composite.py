from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.agent.engine import RunSession
from app.providers.arga import ArgaBackend, ArgaClient, CrmArga, StripeArga
from app.providers.composite import CompositeBackend
from app.providers.factory import build_backend
from app.providers.hubspot_live import HubSpotLive
from app.providers.stripe_live import StripeLive
from app.providers.world import StripeTwin, World
from app.safety.verifier import Intent, verify

TOKEN = "pat-test-token"
SEED: dict[str, Any] = {
    "customers": [{"id": "cus_acme", "email": "jane@acme.com", "name": "Jane Doe", "tenant_id": "t_123"}],
    "charges": [{"id": "ch_100", "customer_id": "cus_acme", "amount_cents": 4200, "tenant_id": "t_123"}],
    "contacts": [{"id": "con_1", "email": "jane@acme.com", "name": "Jane Doe", "tenant_id": "t_123"}],
    "documents": [],
}


def _contact_row(contact_id: str = "con_hs", status: str = "open") -> dict[str, Any]:
    return {
        "id": contact_id,
        "properties": {
            "email": "jane@acme.com",
            "firstname": "Jane",
            "lastname": "Doe",
            "fixpoint_status": status,
        },
    }


def _hubspot(handler: Any) -> HubSpotLive:
    return HubSpotLive(TOKEN, transport=httpx.MockTransport(handler))


def _stripe(handler: Any) -> StripeLive:
    return StripeLive("sk_test_123", transport=httpx.MockTransport(handler))


def _dummy_arga() -> ArgaBackend:
    def client() -> ArgaClient:
        return ArgaClient("https://arga.example")

    return ArgaBackend(stripe=client(), gmail=client(), slack=client(), hubspot=client(), drive=client())


# ------------------------------------------------------------- composite
def test_crm_override_routes_and_stripe_stays_on_base():
    world = World(SEED)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/crm/v3/objects/notes"
        return httpx.Response(201, json={"id": "note_hs"})

    backend = CompositeBackend(world, crm=_hubspot(handler))
    contact = backend.crm.add_note("t_123", "con_1", "Fixpoint run run_1: remedy executed.")

    assert contact.id == "con_1"
    assert isinstance(backend.stripe, StripeTwin)
    assert backend.charges["ch_100"].amount_cents == 4200
    assert backend.contacts["con_1"].notes == ["Fixpoint run run_1: remedy executed."]


def test_live_stripe_and_live_crm_run_simultaneously():
    world = World(SEED)

    def stripe_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": "ch_live", "customer": "cus_1", "amount": 4200, "amount_refunded": 4200},
        )

    def hubspot_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_contact_row())

    backend = CompositeBackend(world, stripe=_stripe(stripe_handler), crm=_hubspot(hubspot_handler))

    charge = backend.stripe.get_charge("t_123", "ch_live")
    contact = backend.crm.get_contact("t_123", "con_hs")
    assert charge is not None and charge.refunded_cents == 4200
    assert contact is not None and contact.id == "con_hs"

    snapshot = backend.snapshot()
    assert snapshot["charges"]["ch_live"]["refunded_cents"] == 4200
    assert snapshot["contacts"]["con_hs"]["status"] == "open"
    # Base state is preserved.
    assert "ch_100" in snapshot["charges"]
    assert "con_1" in snapshot["contacts"]


def test_crm_override_over_arga_keeps_base_stripe():
    base = _dummy_arga()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_contact_row())

    backend = CompositeBackend(base, crm=_hubspot(handler))
    assert isinstance(backend.stripe, StripeArga)
    assert backend.crm.get_contact("t_123", "con_hs") is not None


def test_contacts_merge_base_and_override():
    world = World(SEED)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_contact_row())

    backend = CompositeBackend(world, crm=_hubspot(handler))
    backend.crm.get_contact("t_123", "con_hs")
    assert set(backend.contacts) == {"con_1", "con_hs"}


# --------------------------------------------------------------- factory
def test_factory_hubspot_crm_with_twin_stripe():
    settings = SimpleNamespace(
        arga_configured=False,
        provider_backend="twin",
        stripe_backend="twin",
        crm_backend="hubspot",
        hubspot_token=TOKEN,
        hubspot_status_property="fixpoint_status",
        hubspot_timeout_seconds=5.0,
        hubspot_max_retries=1,
    )
    backend = build_backend(settings, SEED)
    assert isinstance(backend, CompositeBackend)
    assert isinstance(backend.crm, HubSpotLive)
    assert backend.stripe.__class__.__name__ == "StripeTwin"


def test_factory_stripe_live_and_crm_hubspot():
    settings = SimpleNamespace(
        arga_configured=False,
        provider_backend="twin",
        stripe_backend="stripe",
        stripe_api_key="sk_test_123",
        stripe_api_version="2024-06-20",
        stripe_timeout_seconds=5.0,
        stripe_max_retries=1,
        crm_backend="hubspot",
        hubspot_token=TOKEN,
        hubspot_status_property="fixpoint_status",
        hubspot_timeout_seconds=5.0,
        hubspot_max_retries=1,
    )
    backend = build_backend(settings, SEED)
    assert isinstance(backend, CompositeBackend)
    assert isinstance(backend.stripe, StripeLive)
    assert isinstance(backend.crm, HubSpotLive)


def test_factory_stripe_live_with_crm_twin():
    settings = SimpleNamespace(
        arga_configured=False,
        provider_backend="twin",
        stripe_backend="stripe",
        stripe_api_key="sk_test_123",
        stripe_api_version="2024-06-20",
        stripe_timeout_seconds=5.0,
        stripe_max_retries=1,
        crm_backend="twin",
    )
    backend = build_backend(settings, SEED)
    assert isinstance(backend, CompositeBackend)
    assert backend.crm.__class__.__name__ == "CrmTwin"


def test_factory_arga_base_with_hubspot_crm(monkeypatch):
    fake = _dummy_arga()
    monkeypatch.setattr(ArgaBackend, "from_settings", classmethod(lambda cls, _s: fake))
    settings = SimpleNamespace(
        arga_configured=True,
        provider_backend="arga",
        stripe_backend="",
        crm_backend="hubspot",
        hubspot_token=TOKEN,
        hubspot_status_property="fixpoint_status",
        hubspot_timeout_seconds=5.0,
        hubspot_max_retries=1,
    )
    backend = build_backend(settings, SEED)
    assert isinstance(backend, CompositeBackend)
    assert isinstance(backend.crm, HubSpotLive)
    assert isinstance(backend.stripe, StripeArga)


def test_factory_hubspot_without_token_fails_loudly():
    settings = SimpleNamespace(
        arga_configured=False,
        provider_backend="twin",
        stripe_backend="",
        crm_backend="hubspot",
        hubspot_token="",
        hubspot_status_property="fixpoint_status",
        hubspot_timeout_seconds=5.0,
        hubspot_max_retries=1,
    )
    with pytest.raises(ValueError):
        build_backend(settings, SEED)


# -------------------------------------------------------------- verifier
def test_crm_note_recorded_passes(ctx):
    world = World(SEED)
    world.crm.add_note("t_123", "con_1", "Fixpoint run run_test: remedy executed.")
    result = verify(world, ctx, Intent(expected_contact_id="con_1", expect_sync=False), ["stripe.refund"])
    checks = {check.name: check for check in result.checks}
    assert checks["crm_note_recorded"].passed
    assert result.passed


def test_crm_note_recorded_fails_when_missing(ctx):
    world = World(SEED)
    result = verify(world, ctx, Intent(expected_contact_id="con_1", expect_sync=False), ["stripe.refund"])
    checks = {check.name: check for check in result.checks}
    assert not checks["crm_note_recorded"].passed


def test_crm_note_recorded_fails_for_wrong_contact(ctx):
    world = World(SEED)
    world.crm.add_note("t_123", "con_1", "Fixpoint run run_test: remedy executed.")
    result = verify(world, ctx, Intent(expected_contact_id="con_other", expect_sync=False), ["stripe.refund"])
    checks = {check.name: check for check in result.checks}
    assert not checks["crm_note_recorded"].passed
    assert "crm read failed" in checks["crm_note_recorded"].detail


def test_crm_note_recorded_fails_when_read_fails(ctx, monkeypatch):
    world = World(SEED)

    def boom(_tenant: str, _contact_id: str) -> list[Any]:
        raise RuntimeError("hubspot down")

    monkeypatch.setattr(world.crm, "list_notes", boom)
    result = verify(world, ctx, Intent(expected_contact_id="con_1", expect_sync=False), ["stripe.refund"])
    checks = {check.name: check for check in result.checks}
    assert not checks["crm_note_recorded"].passed


def test_twin_list_notes_parity():
    world = World(SEED)
    world.crm.add_note("t_123", "con_1", "first")
    world.crm.add_note("t_123", "con_1", "second")
    notes = world.crm.list_notes("t_123", "con_1")
    assert [note.body for note in notes] == ["first", "second"]
    assert all(note.contact_id == "con_1" for note in notes)


def test_arga_list_notes_parity_and_association():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/crm/v3/objects/notes":
            captured["note"] = json.loads(request.content)
            return httpx.Response(201, json={"id": "note_1"})
        if request.url.path == "/crm/v4/objects/contacts/101/associations/notes":
            return httpx.Response(200, json={"results": [{"toObjectId": 901}]})
        assert request.url.path == "/crm/v3/objects/notes/batch/read"
        return httpx.Response(
            200,
            json={"results": [{"id": "901", "properties": {"hs_note_body": "Fixpoint run run_1: x"}}]},
        )

    client = ArgaClient("https://arga.example", token="t")
    client.transport = httpx.MockTransport(handler)
    crm = CrmArga(client)
    crm.add_note("t_123", "101", "Fixpoint run run_1: x")
    assert captured["note"]["associations"][0]["types"][0]["associationTypeId"] == 202

    notes = crm.list_notes("t_123", "101")
    assert len(notes) == 1 and "run run_1" in notes[0].body


# ---------------------------------------------------------------- engine
def test_engine_writes_note_and_grounds_the_claim(ctx):
    world = World(SEED)
    session = RunSession(world, ctx, "please refund $20.00 for jane@acme.com")
    session.run()
    assert session.report is not None
    assert session.report.outcome == "completed"
    assert session.report.verified is True
    checks = {check.name: check for check in session.verification.checks}
    assert checks["crm_note_recorded"].passed
    assert "crm note added" in session.report.grounded_claims
    assert f"run {ctx.run_id}" in world.contacts["con_1"].notes[0]


def test_engine_writes_status_when_configured(ctx):
    world = World(SEED)
    session = RunSession(
        world, ctx, "please refund $20.00 for jane@acme.com", crm_refund_status="refunded"
    )
    session.run()
    assert session.report is not None and session.report.outcome == "completed"
    assert world.contacts["con_1"].status == "refunded"


def test_engine_does_not_write_status_by_default(ctx):
    world = World(SEED)
    session = RunSession(world, ctx, "please refund $20.00 for jane@acme.com")
    session.run()
    assert world.contacts["con_1"].status == "open"
