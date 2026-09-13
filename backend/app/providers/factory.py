"""Selects the provider backend.

``twin`` (default) is the in-process deterministic twin used by tests, evals and
offline demos. ``arga`` routes reads/writes through Arga digital twins over HTTP
when the per-service URLs are configured; any failure falls back to the in-process
twin so the agent never becomes unavailable because an external sandbox is down.

Stripe and CRM can each be selected independently:

* ``FIXPOINT_STRIPE_BACKEND``: ``twin`` | ``arga`` | ``stripe``
* ``FIXPOINT_CRM_BACKEND``:    ``twin`` | ``arga`` | ``hubspot``

An empty override follows ``FIXPOINT_PROVIDER_BACKEND``. When either differs
from the base, a :class:`CompositeBackend` keeps the base backend for the other
apps and swaps only the selected service.
"""

from __future__ import annotations

from typing import Any

from app.providers.arga import ArgaBackend, ArgaClient, CrmArga, StripeArga
from app.providers.composite import CompositeBackend
from app.providers.hubspot_live import HubSpotLive
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


def _build_crm(settings: Any, seed: dict[str, Any] | None, choice: str) -> Any | None:
    if choice == "hubspot":
        # A missing token must fail loudly rather than silently use a twin.
        return HubSpotLive.from_settings(settings)
    if choice == "arga":
        hubspot_url = getattr(settings, "arga_hubspot_url", "")
        if not hubspot_url:
            return None
        token = getattr(settings, "arga_hubspot_token", "")
        return CrmArga(ArgaClient(hubspot_url, token))
    if choice == "twin":
        return World(seed).crm
    return None


def _resolve_choice(settings: Any, attr: str, base_kind: str) -> str:
    return (getattr(settings, attr, "") or base_kind).lower()


def build_backend(settings: Any, seed: dict[str, Any] | None = None) -> Any:
    base = _build_base(settings, seed)
    base_kind = "arga" if isinstance(base, ArgaBackend) else "twin"

    stripe_choice = _resolve_choice(settings, "stripe_backend", base_kind)
    crm_choice = _resolve_choice(settings, "crm_backend", base_kind)

    stripe = (
        _build_stripe(settings, seed, stripe_choice) if stripe_choice != base_kind else None
    )
    crm = _build_crm(settings, seed, crm_choice) if crm_choice != base_kind else None

    if stripe is None and crm is None:
        return base
    return CompositeBackend(base, stripe=stripe, crm=crm)
