"""Composite provider backend: individual services can differ from the rest.

``build_backend`` normally returns a single backend. Live Stripe and/or live
HubSpot often need to run while Gmail/Slack/Drive stay on the deterministic
twins or Arga, so this wrapper delegates everything to the base backend and
overrides only the services explicitly selected:

* ``stripe`` overrides Stripe (defaults to the base Stripe)
* ``crm`` overrides CRM (defaults to the base CRM)

The public surface matches the base backends (``stripe``, ``crm``, ``gmail``,
``slack_api``, ``drive``, ``charges``, ``contacts``, ``drafts``, ``slack``,
``snapshot``) so the adapter set, engine and verifier are unchanged.
"""

from __future__ import annotations

from typing import Any


class CompositeBackend:
    """Base backend plus optional Stripe and CRM overrides."""

    def __init__(self, base: Any, stripe: Any | None = None, crm: Any | None = None) -> None:
        self._base = base
        self.stripe = stripe if stripe is not None else base.stripe
        self._crm_override = crm

    # ------------------------------------------------------- provider surface
    @property
    def crm(self) -> Any:
        return self._crm_override if self._crm_override is not None else self._base.crm

    @property
    def gmail(self) -> Any:
        return self._base.gmail

    @property
    def slack_api(self) -> Any:
        return self._base.slack_api

    @property
    def drive(self) -> Any:
        return self._base.drive

    # ------------------------------------------------------------ state views
    @property
    def charges(self) -> dict[str, Any]:
        """Base charges merged with the charges Stripe has observed."""
        merged = dict(getattr(self._base, "charges", {}) or {})
        stripe_charges = getattr(self.stripe, "charges", {}) or {}
        merged.update(stripe_charges)
        return merged

    @property
    def contacts(self) -> dict[str, Any]:
        """Base contacts merged with the contacts the CRM override observed."""
        merged = dict(getattr(self._base, "contacts", {}) or {})
        if self._crm_override is not None:
            merged.update(getattr(self._crm_override, "contacts", {}) or {})
        return merged

    @property
    def drafts(self) -> list[Any]:
        return getattr(self._base, "drafts", [])

    @property
    def slack(self) -> list[Any]:
        return getattr(self._base, "slack", [])

    def snapshot(self) -> dict[str, Any]:
        base_snapshot = self._base.snapshot() if hasattr(self._base, "snapshot") else {}
        base_snapshot = dict(base_snapshot or {})
        merged = dict(base_snapshot)

        stripe_snapshot = self.stripe.snapshot() if hasattr(self.stripe, "snapshot") else {}
        merged["charges"] = {
            **(base_snapshot.get("charges") or {}),
            **((stripe_snapshot or {}).get("charges") or {}),
        }

        if self._crm_override is not None and hasattr(self._crm_override, "snapshot"):
            crm_snapshot = self._crm_override.snapshot() or {}
            merged["contacts"] = {
                **(base_snapshot.get("contacts") or {}),
                **(crm_snapshot.get("contacts") or {}),
            }
        return merged

    def __getattr__(self, name: str) -> Any:
        # Only called for attributes not defined above; delegate to the base.
        return getattr(self._base, name)
