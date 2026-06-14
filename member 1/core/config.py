import os
from pydantic import BaseModel, Field

class Settings(BaseModel):
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/career_assistant",
        description="Durable PostgreSQL connection string for persistent states"
    )
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Transient Redis connection string for active session states and job queues"
    )
    OPENAI_API_KEY: str = Field(
        default="mock-key-for-orchestration",
        description="API key for OpenAI Agents SDK orchestrator and specialist models"
    )
    ENCRYPTION_KEY: str = Field(
        default="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODkwYWJjZGU=", 
        description="Base64-encoded 32-byte key for AES-256 tokens encryption"
    )
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Log level output standard"
    )
    RATE_LIMIT_DAILY: int = Field(
        default=50,
        description="Tool level rate limit constraint per service provider"
    )
    PROFILE_CONTEXT_TTL_SECONDS: int = Field(
        default=86400,
        description="Redis Session TTL standard (24 Hours)"
    )

settings = Settings(
    DATABASE_URL=os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/career_assistant"),
    REDIS_URL=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    OPENAI_API_KEY=os.getenv("OPENAI_API_KEY", "mock-key-for-orchestration"),
    ENCRYPTION_KEY=os.getenv("ENCRYPTION_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODkwYWJjZGU="),
    LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
    RATE_LIMIT_DAILY=int(os.getenv("RATE_LIMIT_DAILY", "50")),
    PROFILE_CONTEXT_TTL_SECONDS=int(os.getenv("PROFILE_CONTEXT_TTL_SECONDS", "86400")),
)
