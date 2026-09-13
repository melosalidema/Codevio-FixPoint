"""Selects the provider backend.

``twin`` (default) is the in-process deterministic twin used by tests, evals and
offline demos. ``arga`` routes reads/writes through Arga digital twins over HTTP
when the per-service URLs are configured; any failure falls back to the in-process
twin so the agent never becomes unavailable because an external sandbox is down.

Stripe can be selected independently with ``FIXPOINT_STRIPE_BACKEND``
(``twin`` | ``arga`` | ``stripe``), in which case a :class:`CompositeBackend`
keeps the base backend for Gmail/Slack/CRM/Drive and swaps only Stripe.
"""

from __future__ import annotations

from typing import Any

from app.providers.arga import ArgaBackend, ArgaClient, StripeArga
from app.providers.composite import CompositeBackend
from app.providers.stripe_live import StripeLive
from app.providers.world import World


def _build_base(settings: Any, seed: dict[str, Any] | None) -> Any:
    if getattr(settings, "arga_configured", False):
        try:
            return ArgaBackend.from_settings(settings)
        except Exception:  # noqa: BLE001 - fall back rather than fail the run
            return World(seed)
    return World(seed)


def _build_stripe(settings: Any, seed: dict[str, Any] | None, choice: str) -> Any | None:
    if choice == "stripe":
        # A missing key or live key without acknowledgement fails loudly; an
        # explicit live request must never silently degrade to a twin.
        return StripeLive.from_settings(settings)
    if choice == "arga":
        stripe_url = getattr(settings, "arga_stripe_url", "")
        if not stripe_url:
            return None
        token = getattr(settings, "arga_stripe_token", "")
        return StripeArga(ArgaClient(stripe_url, token))
    if choice == "twin":
        return World(seed).stripe
    return None


def build_backend(settings: Any, seed: dict[str, Any] | None = None) -> Any:
    base = _build_base(settings, seed)
    base_kind = "arga" if isinstance(base, ArgaBackend) else "twin"

    choice = (getattr(settings, "stripe_backend", "") or base_kind).lower()
    if choice == base_kind:
        return base

    stripe = _build_stripe(settings, seed, choice)
    if stripe is None:
        return base
    return CompositeBackend(base, stripe)
