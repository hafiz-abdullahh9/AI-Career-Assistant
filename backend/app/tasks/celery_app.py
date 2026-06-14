"""
Celery application factory.

Responsible for:
  - Creating the Celery app with Redis broker + backend.
  - Defining queues: high / normal / low.
  - Configuring serialization, retries, and task routing.
  - Registering Celery Beat schedule for periodic tasks.

Import this module wherever you need to enqueue tasks:
    from app.tasks.celery_app import celery_app
"""
import os

from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue

from app.core.config import get_settings

settings = get_settings()

# ── Celery app ─────────────────────────────────────────────────────────────────

celery_app = Celery(
    "automation_agent",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.application_tasks",
    ],
)

# ── Configuration ───────────────────────────────────────────────────────────────

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=3600,              # Task results kept for 1 hour

    # Reliability
    acks_late=True,                   # Acknowledge AFTER task completes (not before)
    reject_on_worker_lost=True,       # Re-queue if worker dies mid-task
    task_acks_on_failure_or_timeout=True,

    # Concurrency & prefetch
    worker_prefetch_multiplier=1,     # One task at a time per worker slot (fairness)

    # Time limits
    task_soft_time_limit=600,         # 10 minutes — SIGTERM (task can clean up)
    task_time_limit=660,              # 11 minutes — SIGKILL (hard kill)

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Logging
    worker_hijack_root_logger=False,  # Don't override our structlog setup
    worker_log_color=False,

    # Result backend
    result_backend_transport_options={
        "visibility_timeout": 3600,
    },
)

# ── Queues & routing ────────────────────────────────────────────────────────────

default_exchange = Exchange("default", type="direct")

celery_app.conf.task_queues = [
    Queue("high",   default_exchange, routing_key="high",   priority=10),
    Queue("normal", default_exchange, routing_key="normal", priority=5),
    Queue("low",    default_exchange, routing_key="low",    priority=1),
]

celery_app.conf.task_default_queue = "normal"
celery_app.conf.task_default_exchange = "default"
celery_app.conf.task_default_routing_key = "normal"

# Route specific tasks to specific queues
celery_app.conf.task_routes = {
    "app.tasks.application_tasks.process_application": {
        "queue": "normal",
    },
    "app.tasks.application_tasks.process_application_high": {
        "queue": "high",
    },
    "app.tasks.application_tasks.cleanup_stale_applications": {
        "queue": "low",
    },
}

# ── Beat schedule (periodic tasks) ─────────────────────────────────────────────

celery_app.conf.beat_schedule = {
    "cleanup-stale-applications": {
        "task": "app.tasks.application_tasks.cleanup_stale_applications",
        "schedule": crontab(minute="*/30"),  # Every 30 minutes
        "options": {"queue": "low"},
    },
}
