import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from core.config import settings

# Async Redis Connection Management
redis_pool = aioredis.ConnectionPool.from_url(
    settings.REDIS_URL, 
    decode_responses=True
)

def get_redis_client() -> aioredis.Redis:
    """Returns a client connection from the shared Redis connection pool."""
    return aioredis.Redis(connection_pool=redis_pool)

# Async SQLAlchemy Engine & Session Configuration
async_engine = create_async_engine(
    settings.DATABASE_URL, 
    echo=False, 
    future=True
)

async_session_maker = sessionmaker(
    bind=async_engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

Base = declarative_base()

async def get_db_session() -> AsyncSession:
    """Dependency generator for obtaining async database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
