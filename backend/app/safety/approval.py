from __future__ import annotations

import hmac
import os
import time
import uuid

from app.safety.canonical import canonical_json
from app.safety.models import ApprovalToken, RunContext

DEFAULT_SIGNING_KEY = "dev-only-change-me"
DEFAULT_TOKEN_TTL_SECONDS = 900


def _signing_key() -> str:
    """Signing key from the environment (settings use the same variable)."""
    return os.environ.get("FIXPOINT_SIGNING_KEY", DEFAULT_SIGNING_KEY)


def _token_material(token: ApprovalToken) -> str:
    """Exactly the fields covered by the signature.

    Anything a human approved must be inside this material, otherwise the
    approval could be replayed against a different amount or action.
    """
    return canonical_json(
        {
            "run_id": token.run_id,
            "tenant_id": token.tenant_id,
            "action_hash": token.action_hash,
            "approver_role_required": token.approver_role_required,
            "amount_cents": token.amount_cents,
            "expiry": token.expiry,
            "nonce": token.nonce,
            "single_use": token.single_use,
        }
    )


def sign_token(token: ApprovalToken, key: str | None = None) -> ApprovalToken:
    secret = (key or _signing_key()).encode("utf-8")
    digest = hmac.new(secret, _token_material(token).encode("utf-8"), "sha256").hexdigest()
    return token.model_copy(update={"signature": digest})


def issue_token(
    ctx: RunContext,
    action_hash: str,
    required_role: str,
    amount_cents: int,
    ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
    nonce: str | None = None,
) -> ApprovalToken:
    """Issue a signed approval token bound to one action hash."""
    token = ApprovalToken(
        run_id=ctx.run_id,
        tenant_id=ctx.tenant_id,
        action_hash=action_hash,
        approver_role_required=required_role,
        amount_cents=amount_cents,
        expiry=int(time.time()) + ttl_seconds,
        nonce=nonce or uuid.uuid4().hex,
    )
    return sign_token(token)


def verify_token(token: ApprovalToken, now: int | None = None, key: str | None = None) -> tuple[bool, str]:
    """Constant-time signature verification plus expiry check."""
    if not token.signature:
        return False, "missing_signature"
    secret = (key or _signing_key()).encode("utf-8")
    expected = hmac.new(secret, _token_material(token).encode("utf-8"), "sha256").hexdigest()
    if not hmac.compare_digest(expected, token.signature):
        return False, "bad_signature"
    current = int(time.time()) if now is None else now
    if token.expiry < current:
        return False, "expired"
    return True, "ok"
