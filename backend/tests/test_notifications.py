from __future__ import annotations

import asyncio

import pytest

from app.config import get_settings
from app.services import notifications


def _enable_formspree(monkeypatch) -> None:
    monkeypatch.setenv("FIXPOINT_NOTIFY_FORMSPREE_ENABLED", "true")
    monkeypatch.setenv("FIXPOINT_NOTIFY_FORMSPREE_FORM_ID", "testform")
    get_settings.cache_clear()


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    async def __call__(self, fields: dict[str, str]) -> None:
        self.calls.append(fields)


def test_decision_fields_approved_by_human():
    fields = notifications.decision_fields(
        decision="approved",
        outcome="completed_after_approval",
        run_id="run_1",
        request_text="refund jane@acme.com order ORD-7K2MX $42.00",
        facts={"order_id": "ORD-7K2MX", "customer_email": "jane@acme.com"},
        amount_cents=4200,
        actor="u_99",
        role="team_lead",
    )
    assert fields["event"] == "refund_approved"
    assert fields["email"] == "jane@acme.com"
    assert fields["order_id"] == "ORD-7K2MX"
    assert fields["amount_display"] == "$42.00"
    assert fields["subject"] == "Refund approved · $42.00 · order ORD-7K2MX"
    assert fields["decided_by"] == "u_99"
    assert fields["role"] == "team_lead"
    assert fields["automatic"] == "false"


def test_decision_fields_automatic_and_denied():
    automatic = notifications.decision_fields(
        decision="approved",
        outcome="completed",
        run_id="run_2",
        request_text="refund",
        facts={},
        amount_cents=2000,
        automatic=True,
    )
    assert automatic["decided_by"] == "Fixpoint agent (automatic)"
    assert automatic["automatic"] == "true"
    assert automatic["subject"] == "Refund approved · $20.00"

    denied = notifications.decision_fields(
        decision="denied",
        outcome="denied_by_human",
        run_id="run_3",
        request_text="refund",
        facts={"customer_email": "jane@acme.com"},
        amount_cents=4200,
        actor="u_99",
    )
    assert denied["event"] == "refund_denied"
    assert denied["subject"] == "Refund denied · $42.00"


def test_notify_is_noop_when_disabled(monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr(notifications, "_post_to_formspree", recorder)

    notifications.notify_decision(
        decision="denied",
        outcome="denied_by_human",
        run_id="run_4",
        request_text="refund",
        facts={},
        amount_cents=1000,
    )

    async def _drain() -> None:
        await asyncio.sleep(0)

    asyncio.run(_drain())
    assert recorder.calls == []


def test_notify_schedules_when_enabled(monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr(notifications, "_post_to_formspree", recorder)
    _enable_formspree(monkeypatch)

    async def _run_and_wait() -> None:
        notifications.notify_decision(
            decision="approved",
            outcome="completed",
            run_id="run_5",
            request_text="refund",
            facts={},
            amount_cents=2000,
            automatic=True,
        )
        await asyncio.sleep(0.05)

    asyncio.run(_run_and_wait())
    assert len(recorder.calls) == 1
    assert recorder.calls[0]["event"] == "refund_approved"


@pytest.mark.asyncio
async def test_autonomous_run_notifies_approval(client, monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr(notifications, "_post_to_formspree", recorder)
    _enable_formspree(monkeypatch)

    response = await client.post(
        "/api/runs",
        json={
            "request_text": "I was double charged, please refund for jane@acme.com order ORD-AUTO1",
            "amount_cents": 2000,
        },
    )
    assert response.json()["status"] == "completed"
    await asyncio.sleep(0.05)

    events = [call["event"] for call in recorder.calls]
    assert events == ["refund_approved"]
    assert recorder.calls[0]["order_id"] == "ORD-AUTO1"
    assert recorder.calls[0]["amount_display"] == "$20.00"
    assert recorder.calls[0]["automatic"] == "true"


@pytest.mark.asyncio
async def test_human_decision_notifies_approval_and_denial(client, monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr(notifications, "_post_to_formspree", recorder)
    _enable_formspree(monkeypatch)

    created = await client.post(
        "/api/runs",
        json={
            "request_text": "I was double charged, please refund for jane@acme.com order ORD-HUMAN1",
            "amount_cents": 4200,
        },
    )
    run_id = created.json()["run_id"]
    assert created.json()["status"] == "awaiting_approval"

    approved = await client.post(
        f"/api/runs/{run_id}/approve",
        json={"approver_user_id": "u_99", "role": "team_lead"},
    )
    assert approved.json()["status"] == "completed"

    denied_run = await client.post(
        "/api/runs",
        json={
            "request_text": "I was double charged, please refund for jane@acme.com order ORD-HUMAN2",
            "amount_cents": 4200,
        },
    )
    denied_id = denied_run.json()["run_id"]
    denied = await client.post(f"/api/runs/{denied_id}/deny", json={"approver_user_id": "u_99"})
    assert denied.json()["status"] == "denied"

    await asyncio.sleep(0.05)
    events = [call["event"] for call in recorder.calls]
    assert events == ["refund_approved", "refund_denied"]
    assert recorder.calls[0]["decided_by"] == "u_99"
    assert recorder.calls[0]["role"] == "team_lead"
    assert recorder.calls[1]["order_id"] == "ORD-HUMAN2"
