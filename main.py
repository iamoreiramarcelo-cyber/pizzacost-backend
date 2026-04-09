import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.exceptions import AppException, app_exception_handler
from app.middleware.cors import configure_cors
from app.middleware.rate_limit import limiter
from app.middleware.security_headers import configure_security_headers

logger = logging.getLogger("pizzacost")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup and shutdown events."""
    settings = get_settings()
    log_level = logging.DEBUG if not settings.is_production else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger.info("PizzaCost Pro API starting up (env=%s)", settings.ENVIRONMENT)
    yield
    logger.info("PizzaCost Pro API shutting down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="PizzaCost Pro API",
        description="Backend API for PizzaCost Pro - Pizza cost calculation platform",
        version="1.0.0",
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url="/api/redoc" if not settings.is_production else None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
        redirect_slashes=True,
    )

    # --- Rate Limiting ---
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # --- CORS ---
    configure_cors(app, settings)

    # --- Security Headers ---
    configure_security_headers(app)

    # --- Exception Handlers ---
    app.add_exception_handler(AppException, app_exception_handler)

    # --- Health Check ---
    @app.get("/health", tags=["Health"])
    async def health_check() -> dict:
        return {"status": "healthy", "service": "pizzacost-pro-api"}

    # --- Route Imports & Registration ---
    from app.routes import (
        auth,
        insumos,
        tamanhos,
        bordas,
        pizzas,
        combos,
        dashboard,
        me,
        subscriptions,
        webhooks,
        asaas,
        admin_users,
        admin_emails,
        admin_reports,
        admin_settings,
        admin_lgpd,
    )

    # Each router already has its own prefix and tags defined internally
    app.include_router(auth.router)
    app.include_router(insumos.router)
    app.include_router(tamanhos.router)
    app.include_router(bordas.router)
    app.include_router(pizzas.router)
    app.include_router(combos.router)
    app.include_router(dashboard.router)
    app.include_router(me.router)
    app.include_router(subscriptions.router)
    app.include_router(webhooks.router)
    app.include_router(asaas.router)
    app.include_router(admin_users.router)
    app.include_router(admin_emails.router)
    app.include_router(admin_reports.router)
    app.include_router(admin_settings.router)
    app.include_router(admin_lgpd.router)

    return app


app = create_app()
