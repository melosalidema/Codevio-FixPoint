from __future__ import annotations

import hmac
import os
import time

DEFAULT_WEBHOOK_SECRET = "dev-webhook-secret"
DEFAULT_TTL_SECONDS = 300


def _secret() -> str:
    return os.environ.get("FIXPOINT_WEBHOOK_SECRET", DEFAULT_WEBHOOK_SECRET)


def signature(payload: str, timestamp: int, secret: str | None = None) -> str:
    """HMAC-SHA256 over ``<timestamp>.<raw payload>``."""
    base = f"{timestamp}.{payload}"
    return hmac.new((secret or _secret()).encode("utf-8"), base.encode("utf-8"), "sha256").hexdigest()


def verify(
    payload: str,
    timestamp: int,
    provided: str,
    seen_nonces: set[str],
    nonce: str,
    ttl: int = DEFAULT_TTL_SECONDS,
    now: int | None = None,
) -> tuple[bool, str]:
    """Verify a webhook signature, freshness, and replay state.

    ``seen_nonces`` is the caller's replay set. The API layer backs it with
    Postgres so replay protection survives restarts.
    """
    current = int(time.time()) if now is None else now
    if abs(current - timestamp) > ttl:
        return False, "timestamp_out_of_window"
    if nonce in seen_nonces:
        return False, "replay"
    expected = signature(payload, timestamp)
    if not hmac.compare_digest(expected, provided):
        return False, "bad_signature"
    seen_nonces.add(nonce)
    return True, "ok"
