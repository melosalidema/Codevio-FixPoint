from __future__ import annotations

from app.safety.approval import issue_token, verify_token
from app.safety.canonical import action_hash
from app.safety.models import ProposedAction


def test_sign_and_verify(ctx):
    action = ProposedAction(tool="stripe.refund", params={"charge_id": "ch_100", "amount_cents": 4200})
    token = issue_token(ctx, action_hash(action), "team_lead", 4200, ttl_seconds=600)
    ok, reason = verify_token(token)
    assert ok and reason == "ok"


def test_tampered_token_fails(ctx):
    action = ProposedAction(tool="stripe.refund", params={"charge_id": "ch_100", "amount_cents": 4200})
    token = issue_token(ctx, action_hash(action), "team_lead", 4200, ttl_seconds=600)
    tampered = token.model_copy(update={"amount_cents": 999999})
    ok, reason = verify_token(tampered)
    assert not ok and reason == "bad_signature"


def test_expired_token(ctx):
    action = ProposedAction(tool="stripe.refund", params={"charge_id": "ch_100", "amount_cents": 4200})
    token = issue_token(ctx, action_hash(action), "team_lead", 4200, ttl_seconds=600)
    ok, reason = verify_token(token, now=token.expiry + 1)
    assert not ok and reason == "expired"


def test_missing_signature(ctx):
    action = ProposedAction(tool="stripe.refund", params={"charge_id": "ch_100", "amount_cents": 4200})
    token = issue_token(ctx, action_hash(action), "team_lead", 4200)
    unsigned = token.model_copy(update={"signature": ""})
    ok, reason = verify_token(unsigned)
    assert not ok and reason == "missing_signature"
