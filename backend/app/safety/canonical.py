from __future__ import annotations

import hashlib
import json
from typing import Any

from app.safety.models import ProposedAction, RunContext


def canonical_json(value: Any) -> str:
    """Stable JSON encoding used for every hash in the system."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def action_hash(action: ProposedAction) -> str:
    """Hash binding an approval to one exact tool call and its parameters."""
    material = {"tool": action.tool, "params": action.params}
    return sha256_hex(canonical_json(material))


def idempotency_key(run_id: str, tool: str, params: dict[str, Any]) -> str:
    """Deterministic key so retries of the same mutation collapse to one."""
    charge = params.get("charge_id") or params.get("order_id") or params.get("id") or ""
    amount = params.get("amount_cents", "")
    return sha256_hex(f"{run_id}|{tool}|{charge}|{amount}")


def tenant_of(params: dict[str, Any]) -> str | None:
    """Read a tenant claimed by a proposal. Used only to reject mismatches."""
    for key in ("tenant_id", "account", "merchant"):
        if key in params:
            return str(params[key])
    return None


def context_fingerprint(ctx: RunContext) -> str:
    """Fingerprint of the sealed context, for audit and debugging."""
    material = {
        "tenant_id": ctx.tenant_id,
        "actor_user_id": ctx.actor_user_id,
        "capabilities": sorted(ctx.capabilities),
    }
    return sha256_hex(canonical_json(material))
