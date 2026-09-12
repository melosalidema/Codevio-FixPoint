from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.safety.models import Envelope


class Settings(BaseSettings):
    """Environment-driven configuration.

    Every value can be provided through environment variables. Railway injects
    ``PORT`` and ``DATABASE_URL``; everything else uses the ``FIXPOINT_``
    prefix. Secrets have safe development defaults so the app runs locally
    without any setup, but production deployments must override them.
    """

    model_config = SettingsConfigDict(
        env_prefix="FIXPOINT_",
        # Support both ``backend/.env`` (running from backend/) and the repo
        # root ``.env`` (running from the repository root).
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Fixpoint"
    version: str = "0.2.0"
    env: str = "development"
    # Demo mode enables the audit-tamper endpoint used in the live demo.
    demo_mode: bool = True

    # Railway provides DATABASE_URL (postgres://...). Locally we default to a
    # zero-setup SQLite file so the project runs with no external services.
    database_url: str = Field(
        default="sqlite+aiosqlite:///./fixpoint.db",
        validation_alias=AliasChoices("DATABASE_URL", "FIXPOINT_DATABASE_URL"),
    )

    # HMAC keys. NEVER ship the defaults to production.
    signing_key: str = "dev-only-change-me"
    webhook_secret: str = "dev-webhook-secret"

    # Comma-separated origins allowed to call the API cross-origin
    # (used by the Vite dev server; production serves the SPA from the API).
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Directory holding the built SPA. Empty means "do not serve a frontend".
    static_dir: str = ""

    # Sealed safety envelope. These numbers are authoritative server-side and
    # are never editable by the model or the client.
    max_refund_cents: int = 250_000
    approval_threshold_cents: int = 10_000
    auto_approve_cents: int = 2_500
    team_lead_cents: int = 25_000
    dual_approval_cents: int = 250_000
    max_actions_per_run: int = 20

    # Stand-ins for the authenticated session. In production these are set by
    # the auth layer; the model can never influence them.
    default_tenant_id: str = "t_123"
    default_actor_user_id: str = "u_88"

    @field_validator("database_url", mode="after")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        """Convert platform-style URLs into SQLAlchemy async driver URLs."""
        if value.startswith("postgres://"):
            return "postgresql+asyncpg://" + value[len("postgres://") :]
        if value.startswith("postgresql://") and "+asyncpg" not in value:
            return "postgresql+asyncpg://" + value[len("postgresql://") :]
        if value.startswith("sqlite://") and "+aiosqlite" not in value:
            return "sqlite+aiosqlite://" + value[len("sqlite://") :]
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def envelope(self) -> Envelope:
        """The sealed envelope every run is bound to."""
        return Envelope(
            max_refund_cents=self.max_refund_cents,
            approval_threshold_cents=self.approval_threshold_cents,
            auto_approve_cents=self.auto_approve_cents,
            team_lead_cents=self.team_lead_cents,
            dual_approval_cents=self.dual_approval_cents,
            max_actions_per_run=self.max_actions_per_run,
        )

    @property
    def uses_default_secrets(self) -> bool:
        return self.signing_key == "dev-only-change-me" or self.webhook_secret == "dev-webhook-secret"


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (one instance per process)."""
    return Settings()
