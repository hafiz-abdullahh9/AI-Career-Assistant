"""
Redis connection pool — shared async client.

Provides:
  - A singleton redis.asyncio client reused across the process.
  - FastAPI dependency `get_redis` for per-request access.
  - A standalone async context manager for use inside Celery tasks.
  - A health check function used by the /health endpoint.
"""
import asyncio
import weakref
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Module-level singletons mapped by event loop to prevent "Event loop is closed" errors
_redis_clients = weakref.WeakKeyDictionary()

# Global fallback client when running outside a loop context
_fallback_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    """Return the Redis client scoped to the current event loop, creating it on first call."""
    global _fallback_redis_client
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        if loop not in _redis_clients:
            settings = get_settings()
            _redis_clients[loop] = aioredis.from_url(
                settings.redis_url,
                max_connections=settings.redis_max_connections,
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info("redis.client_created_for_loop", url=settings.redis_url, loop_id=id(loop))
        return _redis_clients[loop]
    else:
        if _fallback_redis_client is None:
            settings = get_settings()
            _fallback_redis_client = aioredis.from_url(
                settings.redis_url,
                max_connections=settings.redis_max_connections,
                encoding="utf-8",
                decode_responses=True,
            )
            logger.info("redis.fallback_client_created", url=settings.redis_url)
        return _fallback_redis_client


async def close_redis_client() -> None:
    """Close the Redis connection pool. Call on app shutdown."""
    global _fallback_redis_client
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop in _redis_clients:
        client = _redis_clients.pop(loop)
        await client.aclose()
        logger.info("redis.client_closed_for_loop", loop_id=id(loop))
    else:
        if _fallback_redis_client is not None:
            await _fallback_redis_client.aclose()
            _fallback_redis_client = None
            logger.info("redis.fallback_client_closed")


async def get_redis() -> AsyncGenerator[Redis, None]:
    """
    FastAPI dependency that yields the shared Redis client.

    The same client is reused across requests (connection pool handles concurrency).

    Usage in route:
        @router.get("/")
        async def my_route(redis: Redis = Depends(get_redis)):
            ...
    """
    yield get_redis_client()


@asynccontextmanager
async def redis_client_ctx() -> AsyncGenerator[Redis, None]:
    """
    Async context manager for use inside Celery tasks (where DI is unavailable).

    Usage:
        async with redis_client_ctx() as redis:
            await redis.incr("some_key")
    """
    yield get_redis_client()


async def check_redis_connection() -> bool:
    """
    Verify Redis is reachable.
    Used by the /health endpoint.
    """
    try:
        client = get_redis_client()
        await client.ping()
        return True
    except Exception as exc:
        logger.error("redis.health_check_failed", error=str(exc))
        return False


# ── Key Builders ──────────────────────────────────────────────────────────────
# Centralize all Redis key patterns here so they're easy to find and change.

def rate_limit_key(user_id: str, date_str: str) -> str:
    """Daily application counter: rate:daily:{user_id}:{YYYYMMDD}"""
    return f"rate:daily:{user_id}:{date_str}"


def dedup_key(user_id: str, job_id: str) -> str:
    """Applied flag: dedup:applied:{user_id}:{job_id}"""
    return f"dedup:applied:{user_id}:{job_id}"


def task_lock_key(application_id: str) -> str:
    """Celery task dedup: task:lock:{application_id}"""
    return f"task:lock:{application_id}"
