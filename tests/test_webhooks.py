from __future__ import annotations

import time

from core import webhooks


def test_valid_signature():
    now = int(time.time())
    payload = '{"event":"charge.succeeded"}'
    sig = webhooks.signature(payload, now)
    ok, reason = webhooks.verify(payload, now, sig, set(), "nonce-1", now=now)
    assert ok and reason == "ok"


def test_forged_signature_rejected():
    now = int(time.time())
    ok, reason = webhooks.verify("{}", now, "deadbeef", set(), "nonce-1", now=now)
    assert not ok and reason == "bad_signature"


def test_replay_rejected():
    now = int(time.time())
    payload = "{}"
    sig = webhooks.signature(payload, now)
    seen: set[str] = set()
    first, _ = webhooks.verify(payload, now, sig, seen, "nonce-1", now=now)
    second, reason = webhooks.verify(payload, now, sig, seen, "nonce-1", now=now)
    assert first and not second and reason == "replay"


def test_stale_timestamp_rejected():
    now = int(time.time())
    payload = "{}"
    sig = webhooks.signature(payload, now)
    ok, reason = webhooks.verify(payload, now, sig, set(), "nonce-1", now=now + 10_000)
    assert not ok and reason == "timestamp_out_of_window"
