"""Selects the provider backend.

``twin`` (default) is the in-process deterministic twin used by tests, evals and
offline demos. ``arga`` routes reads/writes through Arga digital twins over HTTP
when the per-service URLs are configured; any failure falls back to the in-process
twin so the agent never becomes unavailable because an external sandbox is down.
"""

from __future__ import annotations

from typing import Any

from app.providers.arga import ArgaBackend
from app.providers.world import World


def build_backend(settings: Any, seed: dict[str, Any] | None = None) -> Any:
    if getattr(settings, "arga_configured", False):
        try:
            return ArgaBackend.from_settings(settings)
        except Exception:  # noqa: BLE001 - fall back rather than fail the run
            return World(seed)
    return World(seed)
