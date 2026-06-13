import os
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Initialize and load environment variables from .env
load_dotenv()

# Verify that the OpenAI API key is accessible before initializing core components
openai_key = os.getenv("OPENAI_API_KEY")
if not openai_key or "mock-key" in openai_key:
    import logging
    logging.getLogger("core.config").warning(
        "CRITICAL: OPENAI_API_KEY is missing or invalid in the environment variables! "
        "Agents SDK execution will degrade to mock fallbacks."
    )
else:
    import logging
    logging.getLogger("core.config").info("SUCCESS: OPENAI_API_KEY verified and loaded successfully.")

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
    LLM_PROVIDER: str = Field(
        default="gemini",
        description="Primary LLM provider standard: gemini or openai"
    )
    GEMINI_API_KEY: str = Field(
        default="mock-key-for-gemini",
        description="API key for Gemini client"
    )

settings = Settings(
    DATABASE_URL=os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/career_assistant"),
    REDIS_URL=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    OPENAI_API_KEY=os.getenv("OPENAI_API_KEY", "mock-key-for-orchestration"),
    ENCRYPTION_KEY=os.getenv("ENCRYPTION_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODkwYWJjZGU="),
    LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
    RATE_LIMIT_DAILY=int(os.getenv("RATE_LIMIT_DAILY", "50")),
    PROFILE_CONTEXT_TTL_SECONDS=int(os.getenv("PROFILE_CONTEXT_TTL_SECONDS", "86400")),
    LLM_PROVIDER=os.getenv("LLM_PROVIDER", "gemini"),
    GEMINI_API_KEY=os.getenv("GEMINI_API_KEY", "mock-key-for-gemini"),
)

