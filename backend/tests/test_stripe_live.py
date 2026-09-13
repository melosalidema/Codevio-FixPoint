from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from app.agent.engine import RunSession
from app.config import Settings
from app.providers.arga import ArgaBackend, ArgaClient, StripeArga
from app.providers.composite import CompositeBackend
from app.providers.factory import build_backend
from app.providers.stripe_live import StripeLive, stripe_reason
from app.providers.world import ProviderError, RefundRecord, StripeTwin, World
from app.safety.verifier import Intent, verify

SEED: dict[str, Any] = {
    "customers": [{"id": "cus_acme", "email": "jane@acme.com", "name": "Jane Doe", "tenant_id": "t_123"}],
    "charges": [{"id": "ch_100", "customer_id": "cus_acme", "amount_cents": 4200, "tenant_id": "t_123"}],
    "contacts": [{"id": "con_1", "email": "jane@acme.com", "name": "Jane Doe", "tenant_id": "t_123"}],
    "documents": [],
}


def _client(handler: Any, *, max_retries: int = 2) -> StripeLive:
    return StripeLive(
        "sk_test_123",
        api_version="2024-06-20",
        max_retries=max_retries,
        transport=httpx.MockTransport(handler),
    )


def _silence_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.providers.stripe_live.time.sleep", lambda _seconds: None)


# --------------------------------------------------------------- customers
def test_customer_resolution_single_and_request_params():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/customers"
        assert request.url.params["email"] == "jane+refund@acme.com"
        assert request.url.params["limit"] == "100"
        assert request.headers["authorization"] == "Bearer sk_test_123"
        assert request.headers["stripe-version"] == "2024-06-20"
        return httpx.Response(
            200,
            json={
                "data": [{"id": "cus_1", "email": "jane+refund@acme.com", "name": "Jane Doe"}],
                "has_more": False,
            },
        )

    customers = _client(handler).list_customers("t_123", email="jane+refund@acme.com")
    assert len(customers) == 1
    assert customers[0].id == "cus_1" and customers[0].tenant_id == "t_123"


def test_customer_resolution_zero_and_ambiguity():
    def empty(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [], "has_more": False})

    assert _client(empty).list_customers("t_123", email="nobody@acme.com") == []

    def ambiguous(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "cus_1", "email": "jane@acme.com", "name": "Jane Doe"},
                    {"id": "cus_2", "email": "jane@acme.com", "name": "Jane D."},
                ],
                "has_more": False,
            },
        )

    # The provider returns both; the engine is responsible for escalating.
    customers = _client(ambiguous).list_customers("t_123", email="jane@acme.com")
    assert [c.id for c in customers] == ["cus_1", "cus_2"]


def test_customer_resolution_paginates():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("starting_after") == "cus_1":
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "cus_2", "email": "jane@acme.com", "name": "Second"}],
                    "has_more": False,
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [{"id": "cus_1", "email": "jane@acme.com", "name": "First"}],
                "has_more": True,
            },
        )

    customers = _client(handler).list_customers("t_123", email="jane@acme.com")
    assert [c.id for c in customers] == ["cus_1", "cus_2"]


def test_get_customer_missing_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "No such customer"}})

    assert _client(handler).get_customer("t_123", "cus_missing") is None


# ----------------------------------------------------------------- charges
def test_list_charges_maps_amounts_and_filters_customer():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/charges"
        assert request.url.params["customer"] == "cus_1"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "ch_1",
                        "customer": "cus_1",
                        "amount": 4200,
                        "amount_refunded": 1000,
                        "status": "partially_refunded",
                        "currency": "usd",
                        "created": 1700,
                        "metadata": {"fixpoint_seed": "true"},
                    }
                ],
                "has_more": False,
            },
        )

    charges = _client(handler).list_charges("t_123", "cus_1")
    assert len(charges) == 1
    charge = charges[0]
    assert charge.amount_cents == 4200
    assert charge.refunded_cents == 1000
    assert charge.currency == "usd"
    assert charge.created == 1700
    assert charge.metadata == {"fixpoint_seed": "true"}


def test_get_charge_is_a_fresh_read_and_updates_snapshot():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(
            200,
            json={"id": "ch_1", "customer": "cus_1", "amount": 4200, "amount_refunded": 4200},
        )

    client = _client(handler)
    charge = client.get_charge("t_123", "ch_1")
    assert charge is not None and charge.refunded_cents == 4200
    assert calls == ["/v1/charges/ch_1"]
    assert client.snapshot()["charges"]["ch_1"]["refunded_cents"] == 4200


def test_get_charge_missing_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "No such charge"}})

    assert _client(handler).get_charge("t_123", "ch_missing") is None


# ----------------------------------------------------------------- refunds
def test_list_refunds_maps_records():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/refunds"
        assert request.url.params["charge"] == "ch_1"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "re_1",
                        "charge": "ch_1",
                        "amount": 4200,
                        "currency": "usd",
                        "status": "succeeded",
                        "reason": "requested_by_customer",
                        "created": 1701,
                        "metadata": {"run_id": "run_1"},
                    }
                ],
                "has_more": False,
            },
        )

    refunds = _client(handler).list_refunds("t_123", "ch_1")
    assert len(refunds) == 1
    refund = refunds[0]
    assert (refund.id, refund.charge_id, refund.amount_cents, refund.status) == (
        "re_1",
        "ch_1",
        4200,
        "succeeded",
    )
    assert refund.metadata == {"run_id": "run_1"}


def test_refund_form_encoding_idempotency_and_metadata():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/refunds"
        captured["form"] = parse_qs(request.content.decode())
        captured["idempotency"] = request.headers.get("idempotency-key")
        return httpx.Response(200, json={"id": "re_1", "charge": "ch_1", "amount": 4200})

    result = _client(handler).refund(
        "t_123", "ch_1", 4200, "key-1", run_id="run_1", reason="duplicate charge"
    )
    assert result == {"id": "re_1", "charge_id": "ch_1", "amount_cents": 4200, "duplicate": False}
    assert captured["form"]["charge"] == ["ch_1"]
    assert captured["form"]["amount"] == ["4200"]
    assert captured["form"]["reason"] == ["duplicate"]
    assert captured["form"]["metadata[run_id]"] == ["run_1"]
    assert captured["idempotency"] == "key-1"


def test_stripe_reason_mapping():
    assert stripe_reason("duplicate charge") == "duplicate"
    assert stripe_reason("policy_exception") == "requested_by_customer"
    assert stripe_reason("fraudulent") == "fraudulent"
    assert stripe_reason("") == ""


# ------------------------------------------------------------------ errors
def test_error_mapping_includes_request_id_without_secrets():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            402,
            json={"error": {"code": "card_declined", "message": "Your card was declined."}},
            headers={"request-id": "req_123"},
        )

    with pytest.raises(ProviderError) as excinfo:
        _client(handler).get_charge("t_123", "ch_1")
    assert excinfo.value.status == 402
    message = str(excinfo.value)
    assert "card_declined" in message
    assert "request_id=req_123" in message
    assert "sk_test_123" not in message


def test_malformed_response_is_mapped():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json", headers={"content-type": "application/json"})

    with pytest.raises(ProviderError) as excinfo:
        _client(handler).get_charge("t_123", "ch_1")
    assert "malformed_response" in str(excinfo.value)


# ------------------------------------------------------------------- retry
def test_get_retries_transient_failures(monkeypatch):
    _silence_backoff(monkeypatch)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"error": {"message": "try later"}})
        return httpx.Response(200, json={"id": "ch_1", "amount": 100, "amount_refunded": 0})

    charge = _client(handler, max_retries=2).get_charge("t_123", "ch_1")
    assert charge is not None
    assert calls["n"] == 3


def test_refund_post_is_not_retried_by_the_client(monkeypatch):
    _silence_backoff(monkeypatch)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, json={"error": {"message": "boom"}})

    with pytest.raises(ProviderError):
        _client(handler, max_retries=3).refund("t_123", "ch_1", 4200, "key-1")
    # The engine owns refund retries; the client must not add its own loop.
    assert calls["n"] == 1


# --------------------------------------------------------------- security
def test_secrets_never_appear_in_logs(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/refunds":
            return httpx.Response(200, json={"id": "re_1", "charge": "ch_1", "amount": 4200})
        return httpx.Response(200, json={"id": "ch_1", "amount": 4200, "amount_refunded": 0})

    with caplog.at_level(logging.DEBUG):
        client = _client(handler)
        client.get_charge("t_123", "ch_1")
        client.refund("t_123", "ch_1", 4200, "super-secret-idempotency-key")

    assert "sk_test_123" not in caplog.text
    assert "super-secret-idempotency-key" not in caplog.text


def test_live_key_rejected_unless_acknowledged(monkeypatch):
    monkeypatch.setenv("FIXPOINT_STRIPE_API_KEY", "sk_live_abc123")
    monkeypatch.delenv("FIXPOINT_STRIPE_ALLOW_LIVE", raising=False)
    with pytest.raises(ValueError):
        Settings()

    monkeypatch.setenv("FIXPOINT_STRIPE_ALLOW_LIVE", "true")
    settings = Settings()
    assert settings.stripe_api_key.startswith("sk_live_")


# ----------------------------------------------------------- subscriptions
def test_list_subscriptions_evidence():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/subscriptions"
        assert request.url.params["customer"] == "cus_1"
        assert request.url.params["status"] == "all"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "sub_1",
                        "status": "active",
                        "currency": "usd",
                        "created": 1700,
                        "items": {"data": []},
                        "metadata": {},
                    }
                ],
                "has_more": False,
            },
        )

    subscriptions = _client(handler).list_subscriptions("t_123", "cus_1")
    assert subscriptions == [
        {
            "id": "sub_1",
            "customer_id": "cus_1",
            "status": "active",
            "currency": "usd",
            "created": 1700,
            "items": {"data": []},
            "metadata": {},
        }
    ]


# ------------------------------------------------- composite + factory
def test_factory_builds_composite_with_live_stripe():
    settings = SimpleNamespace(
        arga_configured=False,
        provider_backend="twin",
        stripe_backend="stripe",
        stripe_api_key="sk_test_123",
        stripe_api_version="2024-06-20",
        stripe_timeout_seconds=5.0,
        stripe_max_retries=1,
    )
    backend = build_backend(settings, SEED)
    assert isinstance(backend, CompositeBackend)
    assert isinstance(backend.stripe, StripeLive)
    # The base (twin) surface is preserved for the other apps.
    assert backend.crm is not None
    assert backend.charges["ch_100"].amount_cents == 4200


def test_factory_composite_twin_stripe_over_arga(monkeypatch):
    def client() -> ArgaClient:
        return ArgaClient("https://arga.example")

    fake = ArgaBackend(stripe=client(), gmail=client(), slack=client(), hubspot=client(), drive=client())
    monkeypatch.setattr(ArgaBackend, "from_settings", classmethod(lambda cls, _s: fake))
    settings = SimpleNamespace(arga_configured=True, provider_backend="arga", stripe_backend="twin")
    backend = build_backend(settings, SEED)
    assert isinstance(backend, CompositeBackend)
    assert isinstance(backend.stripe, StripeTwin)


def test_factory_default_is_still_the_plain_twin():
    settings = SimpleNamespace(arga_configured=False, provider_backend="twin", stripe_backend="")
    assert isinstance(build_backend(settings, SEED), World)


def test_composite_snapshot_merges_stripe_state():
    world = World(SEED)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": "ch_live", "customer": "cus_1", "amount": 4200, "amount_refunded": 4200},
        )

    composite = CompositeBackend(world, _client(handler))
    assert composite.stripe.get_charge("t_123", "ch_live") is not None
    snapshot = composite.snapshot()
    assert snapshot["charges"]["ch_live"]["refunded_cents"] == 4200
    assert "ch_100" in snapshot["charges"]


# -------------------------------------------------------------- verifier
def test_verifier_requires_exactly_one_refund(ctx, monkeypatch):
    world = World(SEED)
    intent = Intent(expected_refund_charge="ch_100", expected_refund_cents=4200, expect_sync=False)

    # Zero refunds fails even if the charge is untouched.
    result = verify(world, ctx, intent, ["stripe.refund"])
    checks = {check.name: check for check in result.checks}
    assert not result.passed
    assert not checks["exactly_one_refund"].passed

    # Exactly one correct refund passes.
    world.stripe.refund("t_123", "ch_100", 4200, "key-1")
    result = verify(world, ctx, intent, ["stripe.refund"])
    checks = {check.name: check for check in result.checks}
    assert result.passed, checks
    assert checks["exactly_one_refund"].passed

    # Two refunds totalling the expected amount must fail.
    world.charges["ch_100"].refunded_cents = 4200
    world.stripe.refunds = [
        RefundRecord(id="re_a", charge_id="ch_100", amount_cents=2000, tenant_id="t_123"),
        RefundRecord(id="re_b", charge_id="ch_100", amount_cents=2200, tenant_id="t_123"),
    ]
    result = verify(world, ctx, intent, ["stripe.refund"])
    checks = {check.name: check for check in result.checks}
    assert checks["required_outcome"].passed
    assert not checks["exactly_one_refund"].passed


def test_verifier_fails_on_amount_mismatch():
    world = World(SEED)
    world.stripe.refund("t_123", "ch_100", 4000, "key-1")
    ctx = SimpleNamespace(run_id="run_test", tenant_id="t_123")
    intent = Intent(expected_refund_charge="ch_100", expected_refund_cents=4200, expect_sync=False)
    result = verify(world, ctx, intent, ["stripe.refund"])
    checks = {check.name: check for check in result.checks}
    assert not checks["required_outcome"].passed
    assert not checks["exactly_one_refund"].passed


def test_verifier_uses_fresh_live_read(ctx):
    """Live Stripe is re-read over HTTP; a stale twin cache cannot pass."""
    world = World(SEED)
    assert world.charges["ch_100"].refunded_cents == 0

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/refunds":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "re_1",
                            "charge": "ch_100",
                            "amount": 4200,
                            "status": "succeeded",
                        }
                    ],
                    "has_more": False,
                },
            )
        return httpx.Response(
            200,
            json={"id": "ch_100", "customer": "cus_acme", "amount": 4200, "amount_refunded": 4200},
        )

    composite = CompositeBackend(world, _client(handler))
    intent = Intent(expected_refund_charge="ch_100", expected_refund_cents=4200, expect_sync=False)
    result = verify(composite, ctx, intent, ["stripe.refund"])
    assert result.passed, {check.name: check.detail for check in result.checks}
    # Verification did not mutate the deterministic twin's state.
    assert world.charges["ch_100"].refunded_cents == 0


# ---------------------------------------------------- engine retry + ledger
def test_engine_retries_transient_refund_with_same_key(ctx):
    world = World(SEED)
    world.stripe.fail_refund_remaining = 1
    session = RunSession(world, ctx, "please refund $20.00 for jane@acme.com")
    session.run()
    assert session.report is not None
    assert session.report.outcome == "completed"
    assert len(world.stripe.refunds) == 1
    assert world.stripe.refunds[0].amount_cents == 2000
    assert session.report.verified is True


def test_arga_refund_ledger_parity():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/refunds":
            if request.method == "POST":
                return httpx.Response(200, json={"id": "re_1", "status": "succeeded"})
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "re_1",
                            "charge": "ch_1",
                            "amount": 4200,
                            "status": "succeeded",
                        }
                    ]
                },
            )
        return httpx.Response(404, json={})

    client = ArgaClient("https://arga.example", token="t")
    client.transport = httpx.MockTransport(handler)
    stripe = StripeArga(client)
    stripe.refund("t_123", "ch_1", 4200, "key-1", run_id="run_1")
    refunds = stripe.list_refunds("t_123", "ch_1")
    assert len(refunds) == 1 and refunds[0].amount_cents == 4200
    assert stripe.refunds[0].metadata == {"run_id": "run_1"}
