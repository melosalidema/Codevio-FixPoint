from __future__ import annotations

import pytest

from core.schemas import Envelope, GatewayState, RunContext
from twins.world import World

CAPS = ["stripe.read", "stripe.refund", "email.draft", "slack.post", "crm.write", "drive.read"]


@pytest.fixture()
def ctx() -> RunContext:
    return RunContext(
        run_id="run_test",
        tenant_id="t_123",
        actor_user_id="u_88",
        trigger="email",
        capabilities=list(CAPS),
        envelope=Envelope(),
    )


@pytest.fixture()
def state() -> GatewayState:
    return GatewayState(
        allowed_charges={"ch_100", "ch_101"},
        allowed_destinations={"ch_100", "ch_101", "cus_acme"},
    )


@pytest.fixture()
def world() -> World:
    return World(
        {
            "customers": [{"id": "cus_acme", "email": "jane@acme.com", "name": "Jane Doe", "tenant_id": "t_123"}],
            "charges": [
                {"id": "ch_100", "customer_id": "cus_acme", "amount_cents": 4200, "tenant_id": "t_123"},
                {"id": "ch_101", "customer_id": "cus_acme", "amount_cents": 4200, "tenant_id": "t_123"},
            ],
            "contacts": [{"id": "con_1", "email": "jane@acme.com", "name": "Jane Doe", "tenant_id": "t_123"}],
        }
    )
