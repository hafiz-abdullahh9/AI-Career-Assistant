"""
Structured logging configuration using structlog.

Every log line is a JSON object with:
  - timestamp    ISO-8601
  - level        INFO / WARNING / ERROR / DEBUG
  - event        Human-readable message
  - logger       Module that emitted the log
  - trace_id     Request-scoped trace ID (injected by middleware)
  - app_id       Application ID (injected per-task when available)
  - user_id      User ID (injected per-task when available)

Compatible with Datadog log ingestion (JSON format with standard fields).
"""
import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

from app.core.config import get_settings


def _add_app_context(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Inject app-level metadata into every log record."""
    settings = get_settings()
    event_dict.setdefault("app", settings.app_name)
    event_dict.setdefault("version", settings.app_version)
    event_dict.setdefault("env", settings.app_env)
    return event_dict


def _drop_color_message_key(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Remove uvicorn's color_message key (redundant in JSON logs)."""
    event_dict.pop("color_message", None)
    return event_dict


def configure_logging() -> None:
    """
    Configure structlog and stdlib logging.

    Call this exactly once at application startup (in main.py lifespan).
    """
    settings = get_settings()

    # --- Shared processors for both structlog and stdlib ---
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,       # Picks up trace_id, user_id, etc.
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_app_context,
        _drop_color_message_key,
        structlog.processors.StackInfoRenderer(),
    ]

    # --- Development: pretty console output ---
    # --- Production: JSON output for log aggregators ---
    if settings.is_development:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # --- Configure stdlib logging to route through structlog ---
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(settings.log_level)

    # Silence noisy third-party loggers in production
    for noisy_logger in ("sqlalchemy.engine", "asyncpg", "celery.app.trace"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger bound to the given module name.

    Usage:
        from app.core.logging import get_logger
        logger = get_logger(__name__)
        logger.info("application.submitted", app_id=app_id, user_id=user_id)
    """
    return structlog.get_logger(name)
