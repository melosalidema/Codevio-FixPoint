"""Live Stripe provider (test mode expected).

Synchronous ``httpx`` client matching the existing synchronous engine and Arga
implementations. It implements the same surface the in-process twin
(:class:`app.providers.world.StripeTwin`) and the Arga twin expose, so the
adapter set, engine, planner and verifier are unchanged:

* resolve customers by email (auto-paginated; ambiguity is the engine's job)
* list/get charges (``amount`` -> ``amount_cents``, ``amount_refunded`` ->
  ``refunded_cents``)
* list refunds for one charge (the verifier's fresh read)
* list subscriptions (evidence only)
* execute a refund with the gateway's persisted idempotency key

Safety notes:

* The API key is never logged, nor are Authorization/Idempotency-Key headers or
  any secret. Only Stripe's ``request-id`` is logged for diagnostics.
* POSTs are never retried here; the engine already retries a transient refund
  failure once with the same persisted key.
* GETs are retried with bounded backoff on 408/429/5xx and transport errors.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.providers.world import Charge, Customer, ProviderError, RefundRecord

logger = logging.getLogger("fixpoint.stripe")

TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}
MAX_PAGES = 20
PAGE_SIZE = 100


def stripe_reason(reason: str) -> str:
    """Map Fixpoint's reason text onto Stripe's allowed ``reason`` enum."""
    lowered = (reason or "").lower()
    if "duplicate" in lowered:
        return "duplicate"
    if lowered in {"fraudulent", "requested_by_customer"}:
        return lowered
    if lowered:
        return "requested_by_customer"
    return ""


class StripeLive:
    """Stripe REST client with test-mode-safe defaults."""

    supports_failure_injection = False

    def __init__(
        self,
        api_key: str,
        *,
        api_version: str = "",
        timeout: float = 10.0,
        max_retries: int = 2,
        base_url: str = "https://api.stripe.com",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("StripeLive requires an API key")
        self.api_key = api_key
        self.api_version = api_version
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.base_url = base_url.rstrip("/")
        self.transport = transport  # injectable for tests
        self._seen: dict[str, Charge] = {}

    @classmethod
    def from_settings(cls, settings: Any) -> StripeLive:
        if not settings.stripe_api_key:
            raise ValueError("FIXPOINT_STRIPE_API_KEY is required for FIXPOINT_STRIPE_BACKEND=stripe")
        return cls(
            settings.stripe_api_key,
            api_version=settings.stripe_api_version,
            timeout=settings.stripe_timeout_seconds,
            max_retries=settings.stripe_max_retries,
        )

    # ------------------------------------------------------------------ HTTP
    def _headers(self, idempotency_key: str = "") -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        if self.api_version:
            headers["Stripe-Version"] = self.api_version
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _client_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(self.timeout, connect=min(3.0, self.timeout))

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        # Only idempotent GETs are retried; a refund POST is left to the engine,
        # which retries with the same persisted key by design.
        attempts = self.max_retries + 1 if method == "GET" else 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                with httpx.Client(transport=self.transport, timeout=self._client_timeout()) as client:
                    response = client.request(
                        method,
                        f"{self.base_url}{path}",
                        params=params,
                        data=data,
                        headers=self._headers(idempotency_key),
                    )
            except httpx.HTTPError as error:
                last_error = error
                if attempt < attempts - 1:
                    time.sleep(0.2 * (2**attempt))
                    continue
                raise ProviderError(
                    "stripe", 0, f"transport_error: {type(error).__name__}"
                ) from error

            request_id = response.headers.get("request-id", "")
            if response.status_code in TRANSIENT_STATUS and attempt < attempts - 1:
                time.sleep(0.2 * (2**attempt))
                continue
            if response.status_code >= 400:
                raise ProviderError(
                    "stripe", response.status_code, self._error_message(response, request_id)
                )
            if request_id:
                logger.info(
                    "stripe %s %s -> %s request_id=%s", method, path, response.status_code, request_id
                )
            if not response.content:
                return {}
            try:
                body = response.json()
            except ValueError as error:
                raise ProviderError("stripe", response.status_code, "malformed_response") from error
            if not isinstance(body, dict):
                raise ProviderError("stripe", response.status_code, "malformed_response")
            return body

        raise ProviderError(  # pragma: no cover - loop always returns or raises
            "stripe", 0, f"transport_error: {type(last_error).__name__}"
        )

    @staticmethod
    def _error_message(response: httpx.Response, request_id: str) -> str:
        message = "stripe_error"
        try:
            body = response.json()
            error = body.get("error", {}) if isinstance(body, dict) else {}
            message = str(error.get("message") or response.reason_phrase or message)
            code = error.get("code")
            if code:
                message = f"{code}: {message}"
        except ValueError:
            pass
        suffix = f" request_id={request_id}" if request_id else ""
        return f"{message[:200]}{suffix}"

    def _paginate(self, path: str, *, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(MAX_PAGES):
            query = dict(params or {})
            query["limit"] = PAGE_SIZE
            if cursor:
                query["starting_after"] = cursor
            body = self._request("GET", path, params=query)
            data = body.get("data") or []
            if not isinstance(data, list):
                raise ProviderError("stripe", 200, "malformed_response")
            results.extend(data)
            if not body.get("has_more") or not data:
                break
            cursor = str(data[-1].get("id") or "")
            if not cursor:
                break
        return results

    # ------------------------------------------------------------- customers
    def list_customers(
        self, tenant_id: str, email: str | None = None, name: str | None = None
    ) -> list[Customer]:
        if not email:
            # Stripe's customer list cannot search by name; without an email the
            # deterministic planner treats the identity as unresolved.
            return []
        rows = self._paginate("/v1/customers", params={"email": email})
        return [
            Customer(
                id=str(row.get("id", "")),
                email=str(row.get("email") or ""),
                name=str(row.get("name") or ""),
                tenant_id=tenant_id,
            )
            for row in rows
            if not row.get("deleted")
        ]

    def get_customer(self, tenant_id: str, customer_id: str) -> Customer | None:
        try:
            row = self._request("GET", f"/v1/customers/{customer_id}")
        except ProviderError as error:
            if error.status == 404:
                return None
            raise
        if row.get("deleted"):
            return None
        return Customer(
            id=str(row.get("id", customer_id)),
            email=str(row.get("email") or ""),
            name=str(row.get("name") or ""),
            tenant_id=tenant_id,
        )

    # --------------------------------------------------------------- charges
    def list_charges(self, tenant_id: str, customer_id: str | None = None) -> list[Charge]:
        params = {"customer": customer_id} if customer_id else None
        return [self._charge(row, tenant_id) for row in self._paginate("/v1/charges", params=params)]

    def get_charge(self, tenant_id: str, charge_id: str) -> Charge | None:
        """Fresh HTTP read; used by the verifier so no stale cache is trusted."""
        try:
            row = self._request("GET", f"/v1/charges/{charge_id}")
        except ProviderError as error:
            if error.status == 404:
                return None
            raise
        return self._charge(row, tenant_id)

    def _charge(self, row: dict[str, Any], tenant_id: str) -> Charge:
        charge = Charge(
            id=str(row.get("id", "")),
            customer_id=str(row.get("customer") or ""),
            amount_cents=int(row.get("amount", 0) or 0),
            tenant_id=tenant_id,
            status=str(row.get("status") or "succeeded"),
            refunded_cents=int(row.get("amount_refunded", 0) or 0),
            currency=str(row.get("currency") or "usd"),
            created=row.get("created"),
            metadata=dict(row.get("metadata") or {}),
        )
        self._seen[charge.id] = charge
        return charge

    # --------------------------------------------------------------- refunds
    def list_refunds(self, tenant_id: str, charge_id: str) -> list[RefundRecord]:
        rows = self._paginate("/v1/refunds", params={"charge": charge_id})
        return [self._refund(row, tenant_id, charge_id) for row in rows]

    @staticmethod
    def _refund(row: dict[str, Any], tenant_id: str, charge_id: str) -> RefundRecord:
        return RefundRecord(
            id=str(row.get("id", "")),
            charge_id=str(row.get("charge") or charge_id),
            amount_cents=int(row.get("amount", 0) or 0),
            tenant_id=tenant_id,
            status=str(row.get("status") or "succeeded"),
            currency=str(row.get("currency") or "usd"),
            reason=str(row.get("reason") or ""),
            created=row.get("created"),
            metadata=dict(row.get("metadata") or {}),
        )

    def refund(
        self,
        tenant_id: str,
        charge_id: str,
        amount_cents: int,
        idempotency_key: str,
        *,
        run_id: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        """Refund one pinned charge. Only the engine retries this call."""
        data: dict[str, Any] = {"charge": charge_id, "amount": str(amount_cents)}
        stripe_reason_value = stripe_reason(reason)
        if stripe_reason_value:
            data["reason"] = stripe_reason_value
        if run_id:
            data["metadata[run_id]"] = run_id
        body = self._request("POST", "/v1/refunds", data=data, idempotency_key=idempotency_key)
        return {
            "id": str(body.get("id", "")),
            "charge_id": str(body.get("charge") or charge_id),
            "amount_cents": int(body.get("amount", amount_cents) or amount_cents),
            "duplicate": False,
        }

    # --------------------------------------------------------- subscriptions
    def list_subscriptions(self, tenant_id: str, customer_id: str) -> list[dict[str, Any]]:
        rows = self._paginate("/v1/subscriptions", params={"customer": customer_id, "status": "all"})
        return [
            {
                "id": str(row.get("id", "")),
                "customer_id": customer_id,
                "status": str(row.get("status") or ""),
                "currency": str(row.get("currency") or "usd"),
                "created": row.get("created"),
                "items": row.get("items", {}),
                "metadata": dict(row.get("metadata") or {}),
            }
            for row in rows
        ]

    # ------------------------------------------------------------ snapshots
    @property
    def charges(self) -> dict[str, Charge]:
        """Charges observed during this run (fresh reads update the entry)."""
        return self._seen

    def snapshot(self) -> dict[str, Any]:
        return {
            "charges": {
                cid: {
                    "status": charge.status,
                    "refunded_cents": charge.refunded_cents,
                    "amount_cents": charge.amount_cents,
                }
                for cid, charge in self._seen.items()
            }
        }
