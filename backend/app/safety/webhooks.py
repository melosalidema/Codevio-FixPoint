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


# ---- Stripe webhook signatures ------------------------------------------------
#
# Stripe uses ``Stripe-Signature: t=<unix>,v1=<hex>`` and signs the string
# ``<t>.<raw_body>`` with the endpoint's signing secret. Fixpoint must verify
# the raw body exactly as received; re-serialized JSON would change the bytes.

STRIPE_DEFAULT_TTL_SECONDS = 300


def stripe_signature(payload: str, timestamp: int, secret: str) -> str:
    base = f"{timestamp}.{payload}"
    return hmac.new(secret.encode("utf-8"), base.encode("utf-8"), "sha256").hexdigest()


def verify_stripe(
    payload: str,
    header: str,
    secret: str,
    ttl: int = STRIPE_DEFAULT_TTL_SECONDS,
    now: int | None = None,
) -> tuple[bool, str]:
    """Verify a Stripe webhook signature against the raw body.

    Returns ``(ok, reason)``. Reasons: ``missing_signature``, ``missing_secret``,
    ``malformed_signature``, ``timestamp_out_of_window``, ``bad_signature``.
    """
    if not header:
        return False, "missing_signature"
    if not secret:
        return False, "missing_secret"

    timestamp_raw: str | None = None
    signatures: list[str] = []
    for item in header.split(","):
        key, _, value = item.strip().partition("=")
        if key == "t":
            timestamp_raw = value
        elif key == "v1":
            signatures.append(value)
    if timestamp_raw is None or not signatures:
        return False, "malformed_signature"
    try:
        timestamp = int(timestamp_raw)
    except ValueError:
        return False, "malformed_signature"

    current = int(time.time()) if now is None else now
    if abs(current - timestamp) > ttl:
        return False, "timestamp_out_of_window"

    expected = stripe_signature(payload, timestamp, secret)
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        return False, "bad_signature"
    return True, "ok"
