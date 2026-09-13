from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.database import get_db
from app.main import create_app
from app.models import Base
from app.providers.world import World
from app.safety.models import Envelope, GatewayState, RunContext

CAPS = ["stripe.read", "stripe.refund", "email.draft", "slack.post", "crm.write", "drive.read"]


@pytest.fixture(autouse=True)
def _disable_outbound_notifications(monkeypatch):
    """Tests must never POST decision notifications to Formspree.

    Settings are cached process-wide, so clear the cache around every test to
    keep a developer's local ``.env`` from enabling real network delivery.
    """
    monkeypatch.setenv("FIXPOINT_NOTIFY_FORMSPREE_ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --------------------------------------------------------------------- unit
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
            "customers": [
                {"id": "cus_acme", "email": "jane@acme.com", "name": "Jane Doe", "tenant_id": "t_123"}
            ],
            "charges": [
                {"id": "ch_100", "customer_id": "cus_acme", "amount_cents": 4200, "tenant_id": "t_123"},
                {"id": "ch_101", "customer_id": "cus_acme", "amount_cents": 4200, "tenant_id": "t_123"},
            ],
            "contacts": [{"id": "con_1", "email": "jane@acme.com", "name": "Jane Doe", "tenant_id": "t_123"}],
        }
    )


# ----------------------------------------------------------------- API/DB
@pytest_asyncio.fixture()
async def db_engine():
    """Isolated in-memory database per test, shared across connections."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture()
async def db_session(db_engine) -> AsyncSession:
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture()
async def client(db_engine) -> AsyncClient:
    """ASGI client wired to the isolated test database."""
    app = create_app()
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
