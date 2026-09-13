from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import dispose_engine, init_models
from app.routers import config as config_router
from app.routers import evals, health, runs, scenarios, webhooks

logger = logging.getLogger("fixpoint")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.uses_default_secrets:
        logger.warning(
            "Using development defaults for FIXPOINT_SIGNING_KEY / FIXPOINT_WEBHOOK_SECRET. "
            "Set strong secrets before exposing this deployment."
        )
    await init_models()
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    # An explicit live provider selection without credentials must fail at
    # startup, not silently degrade to a twin while the operator believes the
    # real service is live.
    if settings.stripe_backend.lower() == "stripe" and not settings.stripe_api_key:
        raise RuntimeError("FIXPOINT_STRIPE_BACKEND=stripe requires FIXPOINT_STRIPE_API_KEY")
    if settings.crm_backend.lower() == "hubspot" and not settings.hubspot_token:
        raise RuntimeError("FIXPOINT_CRM_BACKEND=hubspot requires FIXPOINT_HUBSPOT_TOKEN")
    # Surface application logs (notifications, safety warnings) alongside
    # uvicorn's own output. No-op if the root logger already has handlers.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = FastAPI(
        title="Fixpoint Control Plane",
        version=settings.version,
        description=(
            "Multi-app agent with a deterministic safety envelope. The LLM proposes; "
            "deterministic code authorizes; humans approve money; an independent "
            "verifier re-reads real state before any claim of success."
        ),
        lifespan=lifespan,
    )

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(health.router)
    app.include_router(config_router.router)
    app.include_router(runs.router)
    app.include_router(scenarios.router)
    app.include_router(evals.router)
    app.include_router(webhooks.router)

    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "internal_error"})

    # Serve the built SPA when a static directory is configured (Docker image).
    static_dir = Path(settings.static_dir).expanduser() if settings.static_dir else None
    if static_dir and static_dir.is_dir():
        assets = static_dir / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        reserved = ("api/", "health", "docs", "redoc", "openapi.json")

        @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
        async def spa(full_path: str) -> FileResponse | JSONResponse:
            if full_path.startswith(reserved):
                return JSONResponse(status_code=404, content={"detail": "not found"})
            candidate = static_dir / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(static_dir / "index.html")

    return app


app = create_app()
