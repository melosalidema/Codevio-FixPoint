"""Seed Stripe test-mode data for the Fixpoint demo.

Creates (idempotently) the demo customer ``jane@acme.com``, two identical charges
for the double-charge scenario, and optionally an active subscription. The
resulting state supports the ``$42 refund`` demo end to end.

Safety:

* refuses live keys (``sk_live_...``) unconditionally — seeding is test-only;
* reuses objects tagged ``metadata.fixpoint_seed=demo`` instead of duplicating;
* never prints the API key.

Usage:
    python -m scripts.stripe_seed
    python -m scripts.stripe_seed --amount-cents 4200 --with-subscription
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import httpx

from app.config import get_settings

STRIPE_BASE = "https://api.stripe.com"
SEED_TAG = "demo"
DEMO_EMAIL = "jane@acme.com"
DEMO_NAME = "Jane Doe"


class SeedError(RuntimeError):
    pass


class SeedClient:
    """Minimal Stripe test-mode client for seeding (writes are create-only)."""

    def __init__(self, api_key: str, timeout: float = 15.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self, idempotency_key: str = "") -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(
                method,
                f"{STRIPE_BASE}{path}",
                data=data,
                params=params,
                headers=self._headers(idempotency_key),
            )
        if response.status_code >= 400:
            try:
                detail = response.json().get("error", {}).get("message", response.text[:200])
            except ValueError:
                detail = response.text[:200]
            raise SeedError(f"Stripe {method} {path} failed ({response.status_code}): {detail}")
        return response.json() if response.content else {}


def _find_customer(client: SeedClient) -> dict[str, Any] | None:
    body = client.request("GET", "/v1/customers", params={"email": DEMO_EMAIL, "limit": 100})
    customers = [row for row in body.get("data", []) if not row.get("deleted")]
    if not customers:
        return None
    if len(customers) > 1:
        print(f"Warning: {len(customers)} customers match {DEMO_EMAIL}; reusing the first.")
    return customers[0]


def _ensure_customer(client: SeedClient) -> dict[str, Any]:
    existing = _find_customer(client)
    if existing is not None:
        print(f"Reusing customer {existing['id']} ({DEMO_EMAIL}).")
        return existing
    customer = client.request(
        "POST",
        "/v1/customers",
        data={
            "email": DEMO_EMAIL,
            "name": DEMO_NAME,
            f"metadata[{SEED_TAG}]": "true",
        },
        idempotency_key="fixpoint-seed-customer",
    )
    print(f"Created customer {customer['id']} ({DEMO_EMAIL}).")
    return customer


def _seed_charges(client: SeedClient, customer_id: str, amount_cents: int) -> list[str]:
    body = client.request(
        "GET",
        "/v1/charges",
        params={"customer": customer_id, "limit": 100},
    )
    charges = [
        row
        for row in body.get("data", [])
        if (row.get("metadata") or {}).get(SEED_TAG) == "true"
        and int(row.get("amount", 0)) == amount_cents
    ]
    charge_ids = [str(row["id"]) for row in charges]
    created: list[str] = []
    index = len(charge_ids)
    while len(charge_ids) + len(created) < 2:
        index += 1
        intent = client.request(
            "POST",
            "/v1/payment_intents",
            data={
                "amount": amount_cents,
                "currency": "usd",
                "customer": customer_id,
                "payment_method": "pm_card_visa",
                "confirm": "true",
                "payment_method_types[0]": "card",
                "description": f"Fixpoint demo charge {index}",
                f"metadata[{SEED_TAG}]": "true",
            },
            idempotency_key=f"fixpoint-seed-charge-{customer_id}-{index}-{amount_cents}-card",
        )
        charge_id = str(intent.get("latest_charge") or "")
        if not charge_id:
            raise SeedError(f"PaymentIntent {intent.get('id')} produced no charge")
        created.append(charge_id)
    if created:
        print(f"Created charges: {', '.join(created)}")
    if charge_ids:
        print(f"Reused charges: {', '.join(charge_ids)}")
    return charge_ids + created


def _seed_subscription(client: SeedClient, customer_id: str) -> str:
    products = client.request(
        "GET",
        "/v1/products",
        params={"limit": 100},
    )
    product = next(
        (row for row in products.get("data", []) if (row.get("metadata") or {}).get(SEED_TAG) == "true"),
        None,
    )
    if product is None:
        product = client.request(
            "POST",
            "/v1/products",
            data={"name": "Fixpoint Demo Plan", f"metadata[{SEED_TAG}]": "true"},
            idempotency_key="fixpoint-seed-product",
        )
        print(f"Created product {product['id']}.")

    prices = client.request("GET", "/v1/prices", params={"product": product["id"], "limit": 100})
    price = next(
        (row for row in prices.get("data", []) if (row.get("metadata") or {}).get(SEED_TAG) == "true"),
        None,
    )
    if price is None:
        price = client.request(
            "POST",
            "/v1/prices",
            data={
                "product": product["id"],
                "unit_amount": 999,
                "currency": "usd",
                "recurring[interval]": "month",
                f"metadata[{SEED_TAG}]": "true",
            },
            idempotency_key="fixpoint-seed-price",
        )
        print(f"Created price {price['id']}.")

    subscriptions = client.request(
        "GET",
        "/v1/subscriptions",
        params={"customer": customer_id, "status": "all", "limit": 100},
    )
    active = next(
        (
            row
            for row in subscriptions.get("data", [])
            if row.get("status") in {"active", "trialing", "past_due"}
            and (row.get("metadata") or {}).get(SEED_TAG) == "true"
        ),
        None,
    )
    if active is not None:
        print(f"Reusing subscription {active['id']} ({active.get('status')}).")
        return str(active["id"])

    client.request(
        "POST",
        "/v1/payment_methods/pm_card_visa/attach",
        data={"customer": customer_id},
    )
    subscription = client.request(
        "POST",
        "/v1/subscriptions",
        data={
            "customer": customer_id,
            "items[0][price]": price["id"],
            "payment_behavior": "error_if_incomplete",
            "default_payment_method": "pm_card_visa",
            f"metadata[{SEED_TAG}]": "true",
        },
        idempotency_key=f"fixpoint-seed-subscription-{customer_id}-{price['id']}",
    )
    print(f"Created subscription {subscription['id']} ({subscription.get('status')}).")
    return str(subscription["id"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed Stripe test-mode data for Fixpoint")
    parser.add_argument("--amount-cents", type=int, default=4200, help="charge amount (default 4200)")
    parser.add_argument("--with-subscription", action="store_true", help="also seed a subscription")
    parser.add_argument("--api-key", default="", help="Stripe test key (defaults to FIXPOINT_STRIPE_API_KEY)")
    args = parser.parse_args(argv)

    api_key = args.api_key or os.environ.get("FIXPOINT_STRIPE_API_KEY", "") or get_settings().stripe_api_key
    if not api_key:
        print("Error: no Stripe key. Set FIXPOINT_STRIPE_API_KEY or pass --api-key.", file=sys.stderr)
        return 1
    if api_key.startswith("sk_live_"):
        print("Error: refusing to seed with a live Stripe key.", file=sys.stderr)
        return 1

    client = SeedClient(api_key)
    try:
        customer = _ensure_customer(client)
        charge_ids = _seed_charges(client, customer["id"], args.amount_cents)
        subscription_id = "skipped"
        if args.with_subscription:
            subscription_id = _seed_subscription(client, customer["id"])
    except SeedError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    dollars = args.amount_cents / 100
    print("\nSeed complete.")
    print(f"  customer:     {customer['id']} ({DEMO_EMAIL})")
    print(f"  charges:      {', '.join(charge_ids)}")
    print(f"  subscription: {subscription_id}")
    print("\nSuggested Fixpoint run text:")
    print(f'  "I was double charged, please refund the duplicate charge for {DEMO_EMAIL}"')
    print(f"  amount_cents={args.amount_cents} (${dollars:,.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
