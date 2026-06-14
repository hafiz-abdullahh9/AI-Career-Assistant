"""
Root test configuration and shared fixtures.

Architecture:
  - All tests run WITHOUT real external services (no real DB, Redis, or Celery).
  - Infrastructure is mocked at the dependency-injection boundary.
  - The FastAPI app and service layer are tested with full fidelity.
  - Only the DB session and Redis client are replaced with async mocks.

Fixture hierarchy:
  mock_redis         → AsyncMock Redis client
  mock_db_session    → AsyncMock SQLAlchemy session
  test_app           → FastAPI app with no-op lifespan + overridden deps
  client             → httpx.AsyncClient bound to test_app
"""
import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.exceptions import AppBaseError
from app.middleware.request_id import RequestIDMiddleware


# ── Shared test data ───────────────────────────────────────────────────────────

TEST_USER_ID = "550e8400-e29b-41d4-a716-446655440000"
TEST_JOB_ID = "7f3e4e20-f56c-4b77-8f81-1234567890ab"
TEST_APP_ID = "9d3e4e20-f56c-4b77-8f81-abcdef012345"
TEST_RESUME_VERSION_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


# ── Request body factories ─────────────────────────────────────────────────────

def make_email_submission(**overrides) -> dict:
    """Build a valid email application submission payload."""
    base = {
        "user_id": TEST_USER_ID,
        "job_id": TEST_JOB_ID,
        "job_metadata": {
            "company_name": "Acme Corp",
            "role_title": "Senior Engineer",
            "application_method": "email",
            "contact_email": "jobs@acme.example.com",
            "platform": "email",
        },
        "resume": {
            "version_id": TEST_RESUME_VERSION_ID,
            "storage_url": "https://our-storage.example.com/resume.pdf",
            "filename": "Test_Resume.pdf",
        },
        "guardrails": {
            "manual_approval_required": False,
            "max_retries": 3,
            "priority": "normal",
        },
    }
    base.update(overrides)
    return base


def make_webform_submission(**overrides) -> dict:
    """Build a valid web form application submission payload."""
    base = {
        "user_id": TEST_USER_ID,
        "job_id": TEST_JOB_ID,
        "job_metadata": {
            "company_name": "TechCorp",
            "role_title": "Data Engineer",
            "application_method": "web_form",
            "application_url": "https://boards.greenhouse.io/techcorp/jobs/123",
            "platform": "greenhouse",
        },
        "resume": {
            "version_id": TEST_RESUME_VERSION_ID,
            "storage_url": "https://our-storage.example.com/resume.pdf",
            "filename": "Test_Resume.pdf",
        },
    }
    base.update(overrides)
    return base


# ── Infrastructure mocks ───────────────────────────────────────────────────────

@pytest.fixture
def mock_redis() -> AsyncMock:
    """
    Async mock Redis client.

    Preconfigured with sensible defaults for all operations used by the
    ApplicationService (get, exists, incr, expire, set, pipeline).
    """
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)      # No counter by default
    redis.exists = AsyncMock(return_value=0)      # Not a duplicate by default
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.set = AsyncMock(return_value=True)

    # Pipeline mock: pipe.incr().pipe.expire() then pipe.execute()
    pipe = AsyncMock()
    pipe.incr = MagicMock(return_value=pipe)
    pipe.expire = MagicMock(return_value=pipe)
    pipe.execute = AsyncMock(return_value=[1, True])
    redis.pipeline = MagicMock(return_value=pipe)

    return redis


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """
    Async mock SQLAlchemy session.

    Provides a minimal interface that service methods use:
    execute, scalar_one_or_none, flush, commit, rollback, add.
    """
    session = AsyncMock()
    session.add = MagicMock()          # Synchronous — just records the object
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    # Default: execute returns a result with no rows
    empty_result = MagicMock()
    empty_result.scalar_one_or_none = MagicMock(return_value=None)
    empty_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    empty_result.scalar_one = MagicMock(return_value=0)
    session.execute = AsyncMock(return_value=empty_result)

    return session


# ── Test application ───────────────────────────────────────────────────────────

@asynccontextmanager
async def _noop_lifespan(app: FastAPI):
    """
    No-op lifespan for testing.
    Skips all real DB and Redis connection initialization.
    """
    yield


def build_test_app(mock_db, mock_redis_client) -> FastAPI:
    """
    Build a test FastAPI application.

    Uses real routes, real service layer, real exception handlers —
    but with mocked DB session and Redis client injected via DI.
    """
    from app.api.v1.router import v1_router
    from app.core.database import get_db
    from app.core.redis import get_redis

    settings = get_settings()

    app = FastAPI(lifespan=_noop_lifespan, title="Test App")
    app.add_middleware(RequestIDMiddleware)
    app.include_router(v1_router, prefix=settings.api_prefix)

    # ── Register exception handlers (mirrors main.py) ──────────────────────
    @app.exception_handler(AppBaseError)
    async def app_error_handler(request: Request, exc: AppBaseError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": exc.error_code,
                    "message": exc.message,
                    "details": exc.details,
                },
                "meta": {"request_id": getattr(request.state, "trace_id", "test")},
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {"code": "INTERNAL_ERROR", "message": str(exc), "details": {}},
            },
        )

    # ── Override dependencies with mocks ───────────────────────────────────
    async def override_get_db():
        yield mock_db

    async def override_get_redis():
        yield mock_redis_client

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    return app


@pytest_asyncio.fixture
async def client(
    mock_db_session: AsyncMock,
    mock_redis: AsyncMock,
) -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP test client bound to the test FastAPI app.

    Provides full HTTP-level testing with mocked infrastructure.
    All business logic, validation, and routing is real.
    """
    app = build_test_app(mock_db_session, mock_redis)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture
def sync_client(mock_db_session: AsyncMock, mock_redis: AsyncMock) -> TestClient:
    """
    Synchronous TestClient for simpler tests that don't need async.
    """
    app = build_test_app(mock_db_session, mock_redis)
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc
