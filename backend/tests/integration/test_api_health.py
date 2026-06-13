"""
API Integration Tests — Health & Readiness Endpoints

Tests the /health and /ready endpoints at the HTTP level.
All infrastructure (DB, Redis) is mocked via the test client fixtures in conftest.py.
"""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient

# All tests in this file exercise the full HTTP routing + service stack.
# Infrastructure (DB, Redis) is mocked; routing, validation, and handlers are real.
pytestmark = pytest.mark.integration


class TestHealthEndpoint:
    """GET /api/v1/health — liveness probe."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client: AsyncClient):
        response = await client.get("/api/v1/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_returns_alive_status(self, client: AsyncClient):
        response = await client.get("/api/v1/health")
        data = response.json()
        assert data["status"] == "alive"

    @pytest.mark.asyncio
    async def test_health_returns_app_metadata(self, client: AsyncClient):
        from app.core.config import get_settings
        settings = get_settings()
        response = await client.get("/api/v1/health")
        data = response.json()
        assert data["version"] == settings.app_version
        assert data["app"] == settings.app_name
        assert "env" in data

    @pytest.mark.asyncio
    async def test_health_is_fast(self, client: AsyncClient):
        """Health endpoint must respond in <500ms (no DB/Redis calls)."""
        import time
        start = time.monotonic()
        await client.get("/api/v1/health")
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"Health endpoint too slow: {elapsed:.3f}s"

    @pytest.mark.asyncio
    async def test_health_response_has_content_type_json(self, client: AsyncClient):
        response = await client.get("/api/v1/health")
        assert "application/json" in response.headers["content-type"]


class TestReadyEndpoint:
    """GET /api/v1/ready — readiness probe with dependency checks."""

    @pytest.mark.asyncio
    async def test_ready_returns_200_when_all_dependencies_healthy(
        self, client: AsyncClient
    ):
        with patch("app.api.v1.health.check_database_connection", return_value=True), \
             patch("app.api.v1.health.check_redis_connection", return_value=True):
            response = await client.get("/api/v1/ready")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_ready_returns_503_when_database_down(self, client: AsyncClient):
        with patch("app.api.v1.health.check_database_connection", return_value=False), \
             patch("app.api.v1.health.check_redis_connection", return_value=True):
            response = await client.get("/api/v1/ready")
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_ready_returns_503_when_redis_down(self, client: AsyncClient):
        with patch("app.api.v1.health.check_database_connection", return_value=True), \
             patch("app.api.v1.health.check_redis_connection", return_value=False):
            response = await client.get("/api/v1/ready")
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_ready_returns_503_when_both_down(self, client: AsyncClient):
        with patch("app.api.v1.health.check_database_connection", return_value=False), \
             patch("app.api.v1.health.check_redis_connection", return_value=False):
            response = await client.get("/api/v1/ready")
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_ready_body_shows_component_status(self, client: AsyncClient):
        with patch("app.api.v1.health.check_database_connection", return_value=True), \
             patch("app.api.v1.health.check_redis_connection", return_value=True):
            response = await client.get("/api/v1/ready")
        data = response.json()
        assert "components" in data
        assert "database" in data["components"]
        assert "redis" in data["components"]

    @pytest.mark.asyncio
    async def test_ready_database_component_shows_down(self, client: AsyncClient):
        with patch("app.api.v1.health.check_database_connection", return_value=False), \
             patch("app.api.v1.health.check_redis_connection", return_value=True):
            response = await client.get("/api/v1/ready")
        data = response.json()
        assert data["components"]["database"]["status"] == "down"
        assert data["components"]["redis"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_ready_shows_latency_metrics(self, client: AsyncClient):
        with patch("app.api.v1.health.check_database_connection", return_value=True), \
             patch("app.api.v1.health.check_redis_connection", return_value=True):
            response = await client.get("/api/v1/ready")
        data = response.json()
        # Latency must be a non-negative number
        db_latency = data["components"]["database"].get("latency_ms")
        assert db_latency is not None
        assert db_latency >= 0

    @pytest.mark.asyncio
    async def test_ready_has_timestamp(self, client: AsyncClient):
        with patch("app.api.v1.health.check_database_connection", return_value=True), \
             patch("app.api.v1.health.check_redis_connection", return_value=True):
            response = await client.get("/api/v1/ready")
        data = response.json()
        assert "timestamp" in data
