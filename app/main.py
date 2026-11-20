"""Application factory and composition root.

``create_app()`` with no arguments builds the PRODUCTION application: the real ``Phase15Adapter`` over the locked
Phase 1-5 code (or ``UnavailableAdapter`` if that cannot be built). It never selects a fake. Tests inject their own
adapter via ``create_app(adapter=...)``; a test double is rejected when ``environment == "production"``.

Run:  uvicorn app.main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from app import __version__
from app.api.routes import (
    autonomy,
    business,
    explainability,
    health,
    intelligence,
    model_lifecycle,
    prediction,
    retention,
    segmentation,
)
from app.api.routes import revenue_intelligence as revenue_intelligence_routes  # PHASE12
from app.api.routes.experience import register_experience
from app.core.config import API_PREFIX, ConfigurationError, Settings
from app.core.errors import install_error_handlers
from app.services.adapters.factory import build_adapter
from app.services.adapters.interface import Phase15Port
from app.services.autonomy_service import build_autonomy_service
from app.services.container import build_services
from app.services.retention_service import build_retention_service

logger = logging.getLogger("trichurn.api")

DESCRIPTION = (
    "TriChurn customer intelligence API over the locked Phase 1-5 implementation. Probabilities come from the Phase 2 "
    "model; SHAP (Phase 3) explains the MODEL, not causes; business figures (Phase 4) are estimates under configured "
    "assumptions; segments (Phase 5) are descriptive. Nothing is retrained or refitted per request.")


def create_app(adapter: Phase15Port | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    adapter = adapter if adapter is not None else build_adapter(settings)
    if getattr(adapter, "is_test_double", False) and settings.environment == "production":
        raise ConfigurationError("A test adapter cannot be used when environment is 'production'.")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.environment == "production":
            from scripts.runtime_asset_manager import RuntimeAssetError, prepare_runtime_assets
            try:
                await run_in_threadpool(prepare_runtime_assets, settings)
            except RuntimeAssetError as exc:
                logger.error("Runtime asset preparation failed: %s", exc)
                raise

        try:
            await run_in_threadpool(adapter.warm_up)
        except Exception as exc:  # noqa: BLE001
            logger.error("Warm-up failed (%s)", type(exc).__name__, exc_info=exc)
            if settings.environment == "production":
                raise

        if settings.environment == "production":
            report = await run_in_threadpool(adapter.readiness)
            if not report.ready:
                failed_checks = ", ".join(
                    f"{check.name}={check.detail}" for check in report.checks if not check.ok
                ) or "no_checks_reported"
                logger.error("Production startup readiness failed: %s", failed_checks)
                raise RuntimeError("Production startup readiness checks failed.")

        yield

    app = FastAPI(
        title="TriChurn API", version=__version__, description=DESCRIPTION, lifespan=lifespan,
        docs_url="/docs" if settings.enable_docs else None, redoc_url=None,
        openapi_url="/openapi.json" if settings.enable_docs else None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins or ()),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.services = build_services(adapter)
    app.state.retention = build_retention_service(settings, adapter)
    app.state.autonomy = build_autonomy_service(settings, app.state.retention)
    install_error_handlers(app)
    for module in (
        health,
        prediction,
        explainability,
        business,
        segmentation,
        intelligence,
        model_lifecycle,
        retention,
        autonomy,
    ):
        app.include_router(module.router, prefix=API_PREFIX)
    app.include_router(revenue_intelligence_routes.router, prefix=API_PREFIX)  # PHASE12
    register_experience(app, settings)
    return app


app = create_app()
