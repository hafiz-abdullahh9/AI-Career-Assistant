"""
Core configuration — loaded once at startup from environment variables.

Uses pydantic-settings so every variable is typed, validated, and documented.
No hardcoded values. No secrets in source code.

Production guard:
  In APP_ENV=production, the validator rejects any 'change-me' placeholder
  secrets and refuses to start. This prevents accidental deployment with
  insecure defaults.
"""
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All application configuration.

    Values are read (in priority order) from:
      1. Environment variables
      2. .env file
      3. Default values defined here
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Silently ignore unknown env vars
    )

    # ── Application ────────────────────────────────────────────
    app_env: Literal["development", "staging", "production"] = "development"
    app_name: str = "application-automation-agent"
    app_version: str = "0.1.0"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ── API ────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8004
    api_prefix: str = "/api/v1"
    # Comma-separated allowed CORS origins; defaults to wildcard (dev only)
    # Set to "https://your-frontend.example.com" in production
    cors_origins: str = "*"

    # ── Database ───────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://postgres:admin@localhost:5432/automation_db"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout: int = 30

    # ── Redis ──────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 20

    # ── Celery ─────────────────────────────────────────────────
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    celery_task_serializer: str = "json"
    celery_result_serializer: str = "json"

    # ── Rate Limiting ──────────────────────────────────────────
    daily_application_limit_default: int = 50
    daily_application_limit_pro: int = 100

    # ── Security ───────────────────────────────────────────────
    jwt_secret_key: str = "change-me-to-a-real-secret-key-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60
    internal_service_secret: str = "change-me-to-a-real-internal-secret"

    # ── Orchestrator ───────────────────────────────────────────
    orchestrator_webhook_url: str = "http://localhost:8000/api/v1/webhooks/automation-result"
    orchestrator_webhook_secret: str = "change-me"

    # ── SMTP Configuration ─────────────────────────────────────
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_email: str = "sender@example.com"
    smtp_password: str = "password"
    smtp_tls: bool = False

    # ── Feature Flags (MVP: all real automation disabled) ──────
    enable_real_email_sending: bool = False
    enable_real_web_automation: bool = False
    enable_captcha_solving: bool = False
    enable_manual_approval: bool = False

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith("postgresql"):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection string")
        if v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """
        In production, refuse to start with any placeholder secrets.

        Placeholder values (containing 'change-me' or being the literal string
        'password') indicate the operator forgot to inject real secrets.
        Failing loudly here is far safer than silently running insecure.
        """
        if self.app_env != "production":
            return self

        _PLACEHOLDER_PATTERNS = ("change-me", "changeme", "change_me")

        checks: list[tuple[str, str]] = [
            ("JWT_SECRET_KEY", self.jwt_secret_key),
            ("INTERNAL_SERVICE_SECRET", self.internal_service_secret),
            ("ORCHESTRATOR_WEBHOOK_SECRET", self.orchestrator_webhook_secret),
        ]
        problems: list[str] = []
        for name, value in checks:
            if any(pattern in value.lower() for pattern in _PLACEHOLDER_PATTERNS):
                problems.append(f"{name} is still set to a placeholder value")

        if self.jwt_secret_key == self.internal_service_secret:
            problems.append(
                "JWT_SECRET_KEY and INTERNAL_SERVICE_SECRET must be distinct values"
            )

        if problems:
            raise ValueError(
                "Production startup refused — insecure configuration detected:\n"
                + "\n".join(f"  • {p}" for p in problems)
                + "\n\nSee .env.production.example for required values."
            )
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS_ORIGINS into a list for FastAPI middleware."""
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return cached Settings singleton.

    Using lru_cache means the .env file is read exactly once per process.
    In tests, call get_settings.cache_clear() to reset between test cases.
    """
    return Settings()
