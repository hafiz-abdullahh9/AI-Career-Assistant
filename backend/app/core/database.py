"""
Async PostgreSQL database connection using SQLAlchemy 2.0.

Design:
  - Single async engine shared across the process lifetime.
  - Session factory yields a scoped async session per request/task.
  - FastAPI dependency `get_db` provides a transactional session per request.
  - Celery tasks use `get_db_session()` async context manager directly.
"""
import asyncio
import weakref
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Module-level singletons mapped by event loop to prevent "Event loop is closed" errors
_engines = weakref.WeakKeyDictionary()
_session_factories = weakref.WeakKeyDictionary()

# Global fallback singletons when running outside a loop context
_fallback_engine: AsyncEngine | None = None
_fallback_session_factory: async_sessionmaker[AsyncSession] | None = None


class Base(DeclarativeBase):
    """
    SQLAlchemy declarative base.

    All ORM models inherit from this class. Defined here so migrations
    can auto-discover them via `Base.metadata`.
    """
    pass


def get_engine() -> AsyncEngine:
    """Return the async engine scoped to the current event loop, creating it on first call."""
    global _fallback_engine
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        if loop not in _engines:
            settings = get_settings()
            _engines[loop] = create_async_engine(
                settings.database_url,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_timeout=settings.database_pool_timeout,
                pool_pre_ping=True,      # Detect stale connections
                echo=settings.debug,     # Log SQL in debug mode only
            )
            logger.info("database.engine_created_for_loop", pool_size=settings.database_pool_size, loop_id=id(loop))
        return _engines[loop]
    else:
        if _fallback_engine is None:
            settings = get_settings()
            _fallback_engine = create_async_engine(
                settings.database_url,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_timeout=settings.database_pool_timeout,
                pool_pre_ping=True,
                echo=settings.debug,
            )
            logger.info("database.fallback_engine_created")
        return _fallback_engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the session factory scoped to the current event loop."""
    global _fallback_session_factory
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        if loop not in _session_factories:
            _session_factories[loop] = async_sessionmaker(
                bind=get_engine(),
                class_=AsyncSession,
                expire_on_commit=False,   # Avoid lazy-load issues in async context
                autoflush=False,
                autocommit=False,
            )
        return _session_factories[loop]
    else:
        if _fallback_session_factory is None:
            _fallback_session_factory = async_sessionmaker(
                bind=get_engine(),
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
                autocommit=False,
            )
        return _fallback_session_factory


async def close_engine() -> None:
    """Dispose the engine and all pooled connections. Call on app shutdown."""
    global _fallback_engine
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop in _engines:
        engine = _engines.pop(loop)
        await engine.dispose()
        _session_factories.pop(loop, None)
        logger.info("database.engine_closed_for_loop", loop_id=id(loop))
    else:
        if _fallback_engine is not None:
            await _fallback_engine.dispose()
            _fallback_engine = None
            logger.info("database.fallback_engine_closed")


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager yielding a database session.

    Automatically commits on success, rolls back on exception.

    Usage (in Celery tasks or services):
        async with get_db_session() as session:
            result = await session.execute(...)
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a database session per request.

    Usage in route:
        @router.get("/")
        async def my_route(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with get_db_session() as session:
        yield session


async def check_database_connection() -> bool:
    """
    Verify the database is reachable.
    Used by the /health endpoint.
    """
    try:
        from sqlalchemy import text
        async with get_db_session() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("database.health_check_failed", error=str(exc))
        return False
