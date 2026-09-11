from __future__ import annotations

import hashlib
import json
from typing import Any

from core.schemas import ProposedAction, RunContext


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def action_hash(action: ProposedAction) -> str:
    material = {"tool": action.tool, "params": action.params}
    return sha256_hex(canonical_json(material))


def idempotency_key(run_id: str, tool: str, params: dict[str, Any]) -> str:
    charge = params.get("charge_id") or params.get("order_id") or params.get("id") or ""
    amount = params.get("amount_cents", "")
    return sha256_hex(f"{run_id}|{tool}|{charge}|{amount}")


def tenant_of(params: dict[str, Any]) -> str | None:
    for key in ("tenant_id", "account", "merchant"):
        if key in params:
            return str(params[key])
    return None


def context_fingerprint(ctx: RunContext) -> str:
    material = {
        "tenant_id": ctx.tenant_id,
        "actor_user_id": ctx.actor_user_id,
        "capabilities": sorted(ctx.capabilities),
    }
    return sha256_hex(canonical_json(material))
