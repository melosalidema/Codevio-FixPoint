from __future__ import annotations

from fastapi import APIRouter

from app.deps import AppSettings
from app.schemas import ConfigResponse, EnvelopeOut

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/config", response_model=ConfigResponse)
async def config(settings: AppSettings) -> ConfigResponse:
    """Public runtime configuration the console needs to render correctly.

    The sealed envelope is exposed read-only so users can see the exact
    numbers the gateway enforces.
    """
    envelope = settings.envelope
    llm_active = settings.llm_enabled and settings.llm_configured
    return ConfigResponse(
        demo_mode=settings.demo_mode,
        env=settings.env,
        version=settings.version,
        default_tenant_id=settings.default_tenant_id,
        llm_enabled=llm_active,
        llm_model=settings.llm_model if llm_active else "",
        provider_backend=settings.provider_backend,
        envelope=EnvelopeOut(**envelope.model_dump(exclude={"forbidden_ops"})),
    )
