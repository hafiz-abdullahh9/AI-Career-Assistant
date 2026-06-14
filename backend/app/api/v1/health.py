"""
Health check and readiness endpoints.

GET /health  — basic liveness probe (is the process up?)
GET /ready   — readiness probe (can it serve traffic? are dependencies up?)

Used by Docker healthcheck, Kubernetes liveness/readiness probes, and
monitoring dashboards to determine service health at a glance.
"""
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.database import check_database_connection
from app.core.redis import check_redis_connection
from app.models.schemas import ComponentHealth, HealthResponse

router = APIRouter(tags=["Health"])
settings = get_settings()


@router.get(
    "/health",
    response_model=None,
    summary="Liveness probe",
    description="Returns 200 if the process is running. No dependency checks.",
)
async def health_check() -> JSONResponse:
    """
    Liveness probe — always returns 200 if the process is alive.

    Use this for: Docker HEALTHCHECK, K8s livenessProbe.
    Do NOT add dependency checks here — that would cause the container
    to restart when downstream dependencies are temporarily unavailable.
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "alive",
            "app": settings.app_name,
            "version": settings.app_version,
            "env": settings.app_env,
        },
    )


@router.get(
    "/ready",
    response_model=HealthResponse,
    summary="Readiness probe",
    description="Checks all dependencies (DB, Redis). Returns 200 if ready, 503 if not.",
)
async def readiness_check() -> JSONResponse:
    """
    Readiness probe — verifies all required dependencies are reachable.

    Use this for: K8s readinessProbe, load balancer health checks.
    Returns 200 only when the service can handle real traffic.
    """
    components: dict[str, ComponentHealth] = {}

    # ── Check PostgreSQL ────────────────────────────────────────
    t0 = time.monotonic()
    db_ok = await check_database_connection()
    db_latency = round((time.monotonic() - t0) * 1000, 2)
    components["database"] = ComponentHealth(
        status="ok" if db_ok else "down",
        latency_ms=db_latency,
        detail="PostgreSQL reachable" if db_ok else "PostgreSQL unreachable",
    )

    # ── Check Redis ─────────────────────────────────────────────
    t0 = time.monotonic()
    redis_ok = await check_redis_connection()
    redis_latency = round((time.monotonic() - t0) * 1000, 2)
    components["redis"] = ComponentHealth(
        status="ok" if redis_ok else "down",
        latency_ms=redis_latency,
        detail="Redis reachable" if redis_ok else "Redis unreachable",
    )

    # ── Determine overall status ────────────────────────────────
    all_ok = db_ok and redis_ok
    overall = "healthy" if all_ok else "unhealthy"

    response = HealthResponse(
        status=overall,
        version=settings.app_version,
        environment=settings.app_env,
        components=components,
    )

    return JSONResponse(
        status_code=200 if all_ok else 503,
        content=response.model_dump(mode="json"),
    )
