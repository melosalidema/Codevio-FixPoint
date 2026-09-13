from __future__ import annotations

import json
import time

import pytest

from app.config import get_settings
from app.models import WebhookEvent
from app.repository import record_webhook_event
from app.safety import webhooks

SECRET = "whsec_test"


def _enable_stripe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIXPOINT_STRIPE_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()


def _signed(
    payload: dict,
    *,
    timestamp: int | None = None,
    secret: str = SECRET,
    tamper: bool = False,
) -> tuple[str, dict[str, str]]:
    body = json.dumps(payload)
    ts = int(time.time()) if timestamp is None else timestamp
    signature = webhooks.stripe_signature(body, ts, secret)
    if tamper:
        signature = "0" * len(signature)
    return body, {"stripe-signature": f"t={ts},v1={signature}", "content-type": "application/json"}


def _event(
    event_id: str = "evt_1",
    event_type: str = "refund.created",
    obj: dict | None = None,
) -> dict:
    if obj is None:
        obj = {
            "id": "re_1",
            "object": "refund",
            "charge": "ch_100",
            "amount": 4200,
            "status": "succeeded",
            "metadata": {},
        }
    return {"id": event_id, "type": event_type, "data": {"object": obj}}


async def _create_paused_run(client) -> dict:
    created = await client.post(
        "/api/runs",
        json={
            "request_text": "I was double charged, please refund for jane@acme.com",
            "amount_cents": 4200,
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "awaiting_approval"
    return body


async def test_valid_signature_links_event_to_run(client, monkeypatch):
    _enable_stripe(monkeypatch)
    run = await _create_paused_run(client)
    payload = _event(
        obj={
            "id": "re_1",
            "object": "refund",
            "charge": "ch_100",
            "amount": 4200,
            "status": "succeeded",
            "metadata": {"run_id": run["run_id"]},
        }
    )
    body, headers = _signed(payload)

    response = await client.post("/api/webhooks/stripe", content=body, headers=headers)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "linked"
    assert result["run_id"] == run["run_id"]
    assert result["event_type"] == "refund.created"


async def test_missing_signature_rejected(client, monkeypatch):
    _enable_stripe(monkeypatch)
    body, _ = _signed(_event())
    response = await client.post("/api/webhooks/stripe", content=body)
    assert response.status_code == 401
    assert "missing_signature" in response.json()["detail"]


async def test_invalid_signature_rejected(client, monkeypatch):
    _enable_stripe(monkeypatch)
    body, headers = _signed(_event(), tamper=True)
    response = await client.post("/api/webhooks/stripe", content=body, headers=headers)
    assert response.status_code == 401
    assert "bad_signature" in response.json()["detail"]


async def test_stale_signature_rejected(client, monkeypatch):
    _enable_stripe(monkeypatch)
    body, headers = _signed(_event(), timestamp=int(time.time()) - 1000)
    response = await client.post("/api/webhooks/stripe", content=body, headers=headers)
    assert response.status_code == 401
    assert "timestamp_out_of_window" in response.json()["detail"]


async def test_malformed_signature_rejected(client, monkeypatch):
    _enable_stripe(monkeypatch)
    body, _ = _signed(_event())
    response = await client.post(
        "/api/webhooks/stripe", content=body, headers={"stripe-signature": "nonsense"}
    )
    assert response.status_code == 401
    assert "malformed_signature" in response.json()["detail"]


async def test_missing_secret_is_a_configuration_error(client, monkeypatch):
    monkeypatch.setenv("FIXPOINT_STRIPE_WEBHOOK_SECRET", "")
    get_settings.cache_clear()
    body, headers = _signed(_event())
    response = await client.post("/api/webhooks/stripe", content=body, headers=headers)
    assert response.status_code == 503
    assert "missing_secret" in response.json()["detail"]


async def test_duplicate_event_is_replay_safe(client, monkeypatch):
    _enable_stripe(monkeypatch)
    body, headers = _signed(_event(event_id="evt_dup"))
    first = await client.post("/api/webhooks/stripe", content=body, headers=headers)
    assert first.status_code == 200
    second = await client.post("/api/webhooks/stripe", content=body, headers=headers)
    assert second.status_code == 200
    assert second.json()["duplicate"] is True


@pytest.mark.parametrize(
    "event_type",
    [
        "charge.refunded",
        "refund.created",
        "refund.updated",
        "refund.failed",
        "charge.dispute.created",
    ],
)
async def test_supported_event_types_are_recorded(client, monkeypatch, event_type):
    _enable_stripe(monkeypatch)
    body, headers = _signed(_event(event_id=f"evt_{event_type}", event_type=event_type))
    response = await client.post("/api/webhooks/stripe", content=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "unlinked"


async def test_missing_run_id_is_recorded_unlinked(client, monkeypatch):
    _enable_stripe(monkeypatch)
    body, headers = _signed(_event(event_id="evt_unlinked"))
    response = await client.post("/api/webhooks/stripe", content=body, headers=headers)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "unlinked"
    assert result["run_id"] is None
    assert result["detail"] == "no_run_id"


async def test_unknown_run_is_flagged(client, monkeypatch):
    _enable_stripe(monkeypatch)
    payload = _event(
        event_id="evt_unknown_run",
        obj={
            "id": "re_2",
            "object": "refund",
            "charge": "ch_100",
            "amount": 4200,
            "status": "succeeded",
            "metadata": {"run_id": "run_does_not_exist"},
        },
    )
    body, headers = _signed(payload)
    response = await client.post("/api/webhooks/stripe", content=body, headers=headers)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "mismatch"
    assert result["detail"] == "run_not_found"


async def test_charge_and_amount_mismatch_are_flagged(client, monkeypatch):
    _enable_stripe(monkeypatch)
    run = await _create_paused_run(client)

    wrong_charge = _event(
        event_id="evt_wrong_charge",
        obj={
            "id": "re_3",
            "object": "refund",
            "charge": "ch_999",
            "amount": 4200,
            "status": "succeeded",
            "metadata": {"run_id": run["run_id"]},
        },
    )
    body, headers = _signed(wrong_charge)
    response = await client.post("/api/webhooks/stripe", content=body, headers=headers)
    assert response.json()["status"] == "mismatch"
    assert response.json()["detail"] == "charge_mismatch"

    wrong_amount = _event(
        event_id="evt_wrong_amount",
        obj={
            "id": "re_4",
            "object": "refund",
            "charge": "ch_100",
            "amount": 9999,
            "status": "succeeded",
            "metadata": {"run_id": run["run_id"]},
        },
    )
    body, headers = _signed(wrong_amount)
    response = await client.post("/api/webhooks/stripe", content=body, headers=headers)
    assert response.json()["status"] == "mismatch"
    assert response.json()["detail"] == "amount_mismatch"


async def test_charge_refunded_uses_refunded_total(client, monkeypatch):
    _enable_stripe(monkeypatch)
    run = await _create_paused_run(client)
    payload = _event(
        event_id="evt_charge_refunded",
        event_type="charge.refunded",
        obj={
            "id": "ch_100",
            "object": "charge",
            "amount": 8400,
            "amount_refunded": 4200,
            "metadata": {"run_id": run["run_id"]},
        },
    )
    body, headers = _signed(payload)
    response = await client.post("/api/webhooks/stripe", content=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "linked"


async def test_link_fields_persisted(db_session):
    await record_webhook_event(
        db_session,
        "stripe",
        "evt_persist",
        event_type="refund.created",
        run_id="run_1",
        status="linked",
        detail="",
    )
    await db_session.commit()
    row = await db_session.get(WebhookEvent, ("stripe", "evt_persist"))
    assert row is not None
    assert row.status == "linked"
    assert row.run_id == "run_1"
    assert row.event_type == "refund.created"
