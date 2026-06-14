"""
FastAPI application entry point.

Responsibilities:
  1. Configure logging (before anything else).
  2. Create the FastAPI app with metadata.
  3. Register all middleware.
  4. Register the global exception handler.
  5. Register all routers.
  6. Manage startup/shutdown lifecycle (DB pool, Redis pool).

Nothing else belongs here. Keep main.py thin.
"""
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import v1_router
from app.core.config import get_settings
from app.core.database import close_engine, get_engine
from app.core.exceptions import AppBaseError
from app.core.logging import configure_logging, get_logger
from app.core.redis import close_redis_client, get_redis_client
from app.middleware.request_id import RequestIDMiddleware

# Configure structured logging before any other imports log anything
configure_logging()
logger = get_logger(__name__)

settings = get_settings()


# ── Application Lifespan ───────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown lifecycle manager.

    Startup:
      - Pre-warm DB connection pool (fail fast if DB is unreachable).
      - Pre-warm Redis connection.

    Shutdown:
      - Gracefully close all DB connections.
      - Close Redis connection pool.
    """
    # ── STARTUP ──────────────────────────────────────────────────────────────
    logger.info(
        "application.startup",
        name=settings.app_name,
        version=settings.app_version,
        env=settings.app_env,
    )

    # Pre-warm DB connection pool
    try:
        engine = get_engine()
        logger.info("database.pool_initialized")
    except Exception as exc:
        logger.error("database.pool_init_failed", error=str(exc))
        raise

    # Pre-warm Redis client
    try:
        redis = get_redis_client()
        await redis.ping()
        logger.info("redis.connection_verified")
    except Exception as exc:
        logger.error("redis.connection_failed", error=str(exc))
        if settings.app_env == "production":
            raise
        logger.warning("redis.connection_failed_non_fatal", message="Proceeding without Redis (non-production environment)")

    logger.info("application.ready")

    # Hand off to the application
    yield

    # ── SHUTDOWN ─────────────────────────────────────────────────────────────
    logger.info("application.shutdown_started")
    await close_engine()
    await close_redis_client()
    logger.info("application.shutdown_complete")


# ── FastAPI App Factory ────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns a fully configured app instance.
    Called once at module level — not per-request.
    """
    app = FastAPI(
        title="Application Automation Agent",
        description=(
            "Member 4 — AI Career Assistant Multi-Agent System 2026.\n\n"
            "Handles job application submission via email and web form automation, "
            "application tracking, and confirmation capture."
        ),
        version=settings.app_version,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Middleware (order matters — applied bottom-up) ─────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,  # Set CORS_ORIGINS env var in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestIDMiddleware)

    # ── Global exception handler ───────────────────────────────────────────
    @app.exception_handler(AppBaseError)
    async def app_error_handler(request: Request, exc: AppBaseError) -> JSONResponse:
        """
        Convert all AppBaseError subclasses into a consistent JSON error envelope.

        This is the ONLY place we translate exceptions to HTTP responses.
        Route handlers should never catch AppBaseError — let it bubble up here.
        """
        logger.warning(
            "request.error",
            error_code=exc.error_code,
            message=exc.message,
            status_code=exc.status_code,
            path=str(request.url),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": exc.error_code,
                    "message": exc.message,
                    "details": exc.details,
                },
                "meta": {
                    "request_id": getattr(request.state, "trace_id", "unknown"),
                },
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all for unexpected exceptions — never expose internals."""
        logger.error(
            "request.unhandled_error",
            error=str(exc),
            path=str(request.url),
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred. Please try again.",
                    "details": {},
                },
                "meta": {
                    "request_id": getattr(request.state, "trace_id", "unknown"),
                },
            },
        )

    # ── Routers ────────────────────────────────────────────────────────────
    app.include_router(v1_router, prefix=settings.api_prefix)

    # ── Root redirect ──────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "health": "/api/v1/health",
        }

    return app


# ── Module-level app instance (used by uvicorn) ────────────────────────────────
app = create_app()
