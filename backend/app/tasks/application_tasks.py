"""
Celery tasks — the async execution layer.

MVP PHASE: All tasks use FAKE/STUB automation.
  - No real emails are sent.
  - No real browser automation runs.
  - The pipeline (queue → process → status update → confirm) is real.

This is intentional. The goal of Phase A is to validate the full
async pipeline is wired correctly before adding real automation.

Adding real automation later = replace the _fake_* functions below
with real implementations without changing task signatures or routing.
"""
import asyncio
import random
import time
import uuid
from datetime import UTC, datetime

import structlog
from celery import Task
from celery.utils.log import get_task_logger

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.redis import redis_client_ctx
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.schemas import ApplicationStatus, TaskPayload
from app.models.orm import Application
from app.services.application_service import ApplicationService
from app.tasks.celery_app import celery_app
from app.email.services.email_service import EmailService
from app.core.exceptions import (
    RetryableEmailError,
    PermanentEmailError,
    TransientAutomationError,
    PermanentAutomationError,
    DuplicateApplicationError,
    RateLimitExceededError
)
from app.orchestration.coordinators.execution_coordinator import ExecutionCoordinator
from app.orchestration.policies.execution_policies import RetryPolicy

# Task-scoped logger (goes to Celery's log output)
task_logger = get_task_logger(__name__)

# Structured logger (goes through structlog pipeline)
logger = structlog.get_logger(__name__)

settings = get_settings()


# ── Helper: run async code inside a sync Celery task ──────────────────────────

def run_async(coro):
    """
    Execute an async coroutine from within a synchronous Celery task.

    We create a fresh event loop per task rather than sharing one,
    which avoids subtle concurrency bugs across concurrent workers.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            from app.core.database import close_engine
            from app.core.redis import close_redis_client

            async def cleanup():
                await close_engine()
                await close_redis_client()

            loop.run_until_complete(cleanup())
        except Exception as e:
            task_logger.warning(f"[TASK] Failed to cleanup loop resources: {e}")
        finally:
            loop.close()


# ── Stub: fake application processing ─────────────────────────────────────────

async def _fake_process_email(payload: TaskPayload) -> dict:
    """
    Simulate email sending without actually sending anything.

    Sleeps briefly to simulate network latency, then returns a fake
    confirmation. Replace with real GmailAPIClient / SMTPClient in Phase B.
    """
    logger.info(
        "stub.email_sending",
        application_id=payload.application_id,
        company="[STUB] Simulating email send...",
    )
    await asyncio.sleep(random.uniform(1.5, 3.0))   # Simulate send latency

    return {
        "success": True,
        "method": "email",
        "confirmation_id": f"EMAIL-STUB-{uuid.uuid4().hex[:8].upper()}",
        "message": "[STUB] Email application simulated — no real email sent",
    }


async def _fake_process_webform(payload: TaskPayload) -> dict:
    """
    Simulate web form submission without launching a browser.

    Sleeps longer to simulate browser startup + form interaction.
    Replace with real Selenium engine in Phase C.
    """
    logger.info(
        "stub.webform_filling",
        application_id=payload.application_id,
        message="[STUB] Simulating web form automation...",
    )
    await asyncio.sleep(random.uniform(3.0, 6.0))   # Simulate browser session

    return {
        "success": True,
        "method": "web_form",
        "confirmation_id": f"FORM-STUB-{uuid.uuid4().hex[:8].upper()}",
        "message": "[STUB] Web form submission simulated — no browser launched",
    }


async def _execute_application(payload: TaskPayload) -> dict:
    """
    Route to the correct stub based on application method.

    Will route to real implementations once Phase B/C modules are ready.
    """
    if payload.method in ("email",):
        return await _fake_process_email(payload)
    elif payload.method in ("web_form", "linkedin_easy_apply", "ats_portal"):
        return await _fake_process_webform(payload)
    else:
        return {
            "success": False,
            "method": payload.method,
            "confirmation_id": None,
            "message": f"Unknown application method: {payload.method}",
        }


async def _execute_application_real(payload: TaskPayload, application: Application, db: AsyncSession, redis: Any) -> dict:
    """
    Executes form automation service using real Selenium or fallback to stub
    based on domain allowlist and settings.
    """
    url = application.application_url
    if not url:
        return {"success": False, "message": "No application URL provided."}

    is_sandbox = url.lower().startswith("file://")
    settings = get_settings()

    if is_sandbox or settings.enable_real_web_automation:
        from app.integrations.services.integration_service import IntegrationService

        service = IntegrationService(db=db, redis=redis)
        outcome = await service.execute_integration(
            application=application,
            session_id=f"sess_{payload.application_id[:8]}",
            task_id=payload.application_id
        )

        return {
            "success": outcome.success,
            "method": "web_form",
            "confirmation_id": outcome.confirmation_id,
            "message": outcome.message
        }
    else:
        # Fall back to fake/stub browser automation
        return await _fake_process_webform(payload)


# ── Core async processing logic ────────────────────────────────────────────────

async def _process_application_async(payload: TaskPayload) -> None:
    """
    Full async pipeline:
      1. Pre-evaluate safety controls and policies.
      2. Handle pause and approvals state.
      3. Acquire concurrency locks/slots.
      4. Execute email or form automation.
      5. Release concurrency locks.
    """
    app_id = payload.application_id

    # Bind structured context for all log lines in this coroutine
    structlog.contextvars.bind_contextvars(
        application_id=app_id,
        user_id=payload.user_id,
        method=payload.method,
    )

    logger.info("task.processing_started", attempt=payload.attempt)

    async with get_db_session() as db, redis_client_ctx() as redis:
        service = ApplicationService(db=db, redis=redis)
        email_service = EmailService(db=db)
        coordinator = ExecutionCoordinator(db=db, redis=redis)

        # ── Step 1: Pre-evaluate safety controls ──
        application = await service.get_application(app_id)
        user_tier = application.metadata_.get("user_tier", "standard") if application.metadata_ else "standard"
        
        try:
            eval_res = await coordinator.pre_evaluate(
                user_id=payload.user_id,
                job_id=payload.job_id,
                company_name=application.company_name,
                role_title=application.role_title,
                url=application.application_url,
                method=payload.method,
                manual_approval_required=application.manual_approval_required,
                priority=payload.priority,
                user_tier=user_tier
            )
        except Exception as exc:
            logger.error("governance.policy_blocked", error=str(exc))
            new_status = ApplicationStatus.FAILED
            if isinstance(exc, DuplicateApplicationError):
                new_status = ApplicationStatus.DUPLICATE
            elif isinstance(exc, RateLimitExceededError):
                new_status = ApplicationStatus.LIMIT_EXCEEDED

            await service.transition_status(
                application_id=app_id,
                new_status=new_status,
                reason=f"Blocked by execution policies: {exc}"
            )
            raise PermanentAutomationError(str(exc))

        # Handle paused state/retry
        if eval_res["status"] == "paused":
            reason = eval_res["reason"]
            delay = eval_res.get("retry_after_sec", 60.0)
            logger.info("governance.execution_paused", reason=reason, delay=delay)
            transient_exc = TransientAutomationError(reason)
            transient_exc.countdown = delay
            raise transient_exc

        # Handle pending approval trigger
        if eval_res["status"] == "pending_approval":
            reason = eval_res["reason"]
            logger.info("governance.pending_approval_triggered", reason=reason)
            await coordinator.handle_approval_trigger(application, reason)
            return

        # ── Step 2: Concurrency slot acquisition ──
        acquired = await coordinator.acquire_execution_slots(payload.user_id, payload.job_id, payload.method)
        if not acquired:
            logger.info("governance.concurrency_busy", message="Concurrency slots full or locked. Deferring task.")
            transient_exc = TransientAutomationError("Concurrency slots busy.")
            transient_exc.countdown = 30.0  # Retry in 30 seconds
            raise transient_exc

        # ── Step 3: Transition status ──────────────────────────────────────
        try:
            if payload.method == "email":
                await service.transition_status(
                    application_id=app_id,
                    new_status=ApplicationStatus.EMAIL_SENDING,
                    reason="Starting email delivery pipeline",
                )
            else:
                await service.transition_status(
                    application_id=app_id,
                    new_status=ApplicationStatus.PROCESSING,
                    reason="Celery task started",
                )
        except Exception as exc:
            logger.error("task.transition_failed", error=str(exc))
            await coordinator.release_execution_slots(payload.user_id, payload.job_id, payload.method)
            raise

        # ── Step 4: Execute automation ────────────────────
        start_time = time.monotonic()
        try:
            if payload.method == "email":
                candidate_name = application.metadata_.get("candidate_name") or "John Doe"
                custom_message = application.metadata_.get("cover_letter", {}).get("content_text")
                
                res = await email_service.send_application_email(
                    application=application,
                    candidate_name=candidate_name,
                    custom_message=custom_message
                )

                elapsed = round(time.monotonic() - start_time, 2)
                logger.info("task.email_complete", elapsed_seconds=elapsed, result=res)

                await service.transition_status(
                    application_id=app_id,
                    new_status=ApplicationStatus.EMAIL_SENT,
                    reason=f"Email sent successfully via {res.provider}",
                    context={"elapsed_seconds": elapsed, "message_id": res.message_id},
                )

                if res.message_id:
                    await service.set_confirmation(
                        application_id=app_id,
                        confirmation_id=res.message_id,
                    )

                # Record execution governance states
                await coordinator.record_successful_execution(
                    user_id=payload.user_id,
                    platform="email",
                    company_name=application.company_name,
                    role_title=application.role_title,
                    url=application.application_url
                )
            else:
                result = await _execute_application_real(payload, application, db, redis)
                elapsed = round(time.monotonic() - start_time, 2)
                logger.info("task.automation_complete", elapsed_seconds=elapsed, result=result)

                if result["success"]:
                    await service.transition_status(
                        application_id=app_id,
                        new_status=ApplicationStatus.APPLIED,
                        reason=result["message"],
                        context={"elapsed_seconds": elapsed},
                    )

                    if result.get("confirmation_id"):
                        await service.set_confirmation(
                            application_id=app_id,
                            confirmation_id=result["confirmation_id"],
                        )

                    from urllib.parse import urlparse
                    parsed = urlparse(application.application_url)
                    netloc = parsed.netloc.lower()
                    if netloc.startswith("www."):
                        netloc = netloc[4:]
                    platform = netloc.split(".")[0] if "." in netloc else netloc

                    # Record execution governance states
                    await coordinator.record_successful_execution(
                        user_id=payload.user_id,
                        platform=platform,
                        company_name=application.company_name,
                        role_title=application.role_title,
                        url=application.application_url
                    )
                else:
                    await service.transition_status(
                        application_id=app_id,
                        new_status=ApplicationStatus.FAILED,
                        reason=result["message"],
                    )
                    raise PermanentAutomationError(result["message"])

        except Exception as exc:
            logger.error("task.execution_failed", error=str(exc))
            if not isinstance(exc, PermanentAutomationError) and not isinstance(exc, PermanentEmailError):
                if payload.method == "email":
                    await _mark_email_retryable_failed(app_id, str(exc))
                else:
                    await _mark_webform_retryable_failed(app_id, str(exc))
                raise
            else:
                if payload.method == "email":
                    await _mark_email_permanently_failed(app_id, str(exc))
                else:
                    await _mark_permanently_failed(app_id, str(exc))
                raise
        finally:
            await coordinator.release_execution_slots(payload.user_id, payload.job_id, payload.method)

    structlog.contextvars.clear_contextvars()


async def _mark_webform_retryable_failed(application_id: str, error: str) -> None:
    async with get_db_session() as db, redis_client_ctx() as redis:
        service = ApplicationService(db=db, redis=redis)
        try:
            await service.increment_retry_count(application_id)
            # Step 1: Transition PROCESSING -> ASSET_ERROR
            await service.transition_status(
                application_id=application_id,
                new_status=ApplicationStatus.ASSET_ERROR,
                reason=f"Web form automation failed temporarily: {error}",
            )
            # Step 2: Transition ASSET_ERROR -> QUEUED
            await service.transition_status(
                application_id=application_id,
                new_status=ApplicationStatus.QUEUED,
                reason="Requeued for retry attempt",
            )
        except Exception as exc:
            logger.error("task.mark_retryable_failed_error", error=str(exc))


# ── Celery task definitions ────────────────────────────────────────────────────

@celery_app.task(
    name="app.tasks.application_tasks.process_application",
    bind=True,
    max_retries=3,
    default_retry_delay=60,        # Initial delay before first retry
    acks_late=True,
    reject_on_worker_lost=True,
    queue="normal",
)
def process_application(self: Task, payload_dict: dict) -> dict:
    """
    Main application processing task.

    Accepts a JSON-serializable dict (TaskPayload) and runs the full
    application pipeline asynchronously inside a sync Celery task.
    """
    payload = TaskPayload(**payload_dict)

    task_logger.info(
        f"[TASK] Processing application {payload.application_id} "
        f"via {payload.method} (attempt {payload.attempt}/{self.max_retries + 1})"
    )

    try:
        run_async(_process_application_async(payload))
        return {"status": "completed", "application_id": payload.application_id}

    except Exception as exc:
        is_email = payload.method == "email"
        task_logger.warning(
            f"[TASK] Application {payload.application_id} failed: {exc}. "
            f"Retry {self.request.retries}/{self.max_retries}"
        )

        is_permanent = isinstance(exc, (PermanentEmailError, PermanentAutomationError))
        if not is_permanent and not isinstance(exc, (RetryableEmailError, TransientAutomationError)) and is_email:
            is_permanent = True

        if self.request.retries < self.max_retries:
            if is_permanent:
                task_logger.error(
                    f"[TASK] Application {payload.application_id} permanently failed: {exc}"
                )
                if is_email:
                    run_async(_mark_email_permanently_failed(payload.application_id, str(exc)))
                else:
                    run_async(_mark_permanently_failed(payload.application_id, str(exc)))
                return {"status": "failed", "application_id": payload.application_id, "error": str(exc)}

            if is_email:
                run_async(_mark_email_retryable_failed(payload.application_id, str(exc)))
            else:
                run_async(_mark_webform_retryable_failed(payload.application_id, str(exc)))

            # Read custom countdown from the exception if available
            delay = getattr(exc, "countdown", None)
            if delay is None:
                delay = RetryPolicy.calculate_backoff(attempt=self.request.retries + 1, base_delay=60.0)

            raise self.retry(exc=exc, countdown=delay)

        # Max retries exhausted → final failure
        task_logger.error(
            f"[TASK] Application {payload.application_id} permanently failed "
            f"after {self.max_retries} retries: {exc}"
        )
        if is_email:
            run_async(_mark_email_permanently_failed(payload.application_id, f"Max retries exhausted: {exc}"))
        else:
            run_async(_mark_permanently_failed(payload.application_id, str(exc)))
        return {"status": "failed", "application_id": payload.application_id, "error": str(exc)}


@celery_app.task(
    name="app.tasks.application_tasks.send_application_email_task",
    bind=True,
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
    queue="normal",
)
def send_application_email_task(self: Task, application_id: str) -> dict:
    """
    Dedicated Celery task to send an email for a job application.
    """
    task_logger.info(f"[TASK] send_application_email_task started for {application_id}")
    try:
        run_async(_send_application_email_async(self, application_id))
        return {"status": "completed", "application_id": application_id}
    except Exception as exc:
        task_logger.warning(
            f"[TASK] send_application_email_task failed for {application_id}: {exc}. "
            f"Retry {self.request.retries}/{self.max_retries}"
        )

        is_permanent = isinstance(exc, PermanentEmailError)
        if not is_permanent and not isinstance(exc, RetryableEmailError):
            is_permanent = True

        if self.request.retries < self.max_retries:
            if is_permanent:
                task_logger.error(f"[TASK] send_application_email_task permanent failure: {exc}")
                run_async(_mark_email_permanently_failed(application_id, str(exc)))
                return {"status": "failed", "application_id": application_id, "error": str(exc)}

            run_async(_mark_email_retryable_failed(application_id, str(exc)))
            delay = 60 * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=delay)

        # Max retries exhausted
        task_logger.error(f"[TASK] send_application_email_task permanently failed: {exc}")
        run_async(_mark_email_permanently_failed(application_id, f"Max retries exhausted: {exc}"))
        return {"status": "failed", "application_id": application_id, "error": str(exc)}


async def _send_application_email_async(self: Task, application_id: str) -> None:
    # Bind structured context
    structlog.contextvars.bind_contextvars(
        application_id=application_id,
        task_id=self.request.id,
    )

    logger.info("email.task_started")

    async with get_db_session() as db, redis_client_ctx() as redis:
        service = ApplicationService(db=db, redis=redis)
        email_service = EmailService(db=db)

        application = await service.get_application(application_id)

        # Validate state
        current_status = ApplicationStatus(application.status)
        if current_status not in (
            ApplicationStatus.QUEUED,
            ApplicationStatus.EMAIL_QUEUED,
            ApplicationStatus.EMAIL_FAILED,
            ApplicationStatus.EMAIL_SENDING,
        ):
            logger.error("email.invalid_state", status=application.status)
            raise PermanentEmailError(f"Application is in an invalid status for sending: {application.status}")

        await service.transition_status(
            application_id=application_id,
            new_status=ApplicationStatus.EMAIL_SENDING,
            reason="Sending application email via SMTP/Gmail",
            context={"task_id": self.request.id}
        )

        candidate_name = application.metadata_.get("candidate_name") or "John Doe"
        custom_message = application.metadata_.get("cover_letter", {}).get("content_text")

        res = await email_service.send_application_email(
            application=application,
            candidate_name=candidate_name,
            custom_message=custom_message
        )

        await service.transition_status(
            application_id=application_id,
            new_status=ApplicationStatus.EMAIL_SENT,
            reason=f"Email sent successfully via {res.provider}",
            context={"message_id": res.message_id, "latency_ms": res.latency_ms}
        )

        if res.message_id:
            await service.set_confirmation(
                application_id=application_id,
                confirmation_id=res.message_id
            )

        await service.mark_daily_counter(str(application.user_id))
        await service.mark_dedup_cache(str(application.user_id), str(application.job_id))

        logger.info("email.task_success", provider=res.provider, message_id=res.message_id)

    structlog.contextvars.clear_contextvars()


async def _mark_email_permanently_failed(application_id: str, error: str) -> None:
    async with get_db_session() as db, redis_client_ctx() as redis:
        service = ApplicationService(db=db, redis=redis)
        try:
            await service.transition_status(
                application_id=application_id,
                new_status=ApplicationStatus.FAILED,
                reason=f"Email send failed: {error}",
            )
        except Exception as exc:
            logger.error("task.mark_failed_error", error=str(exc))


async def _mark_email_retryable_failed(application_id: str, error: str) -> None:
    async with get_db_session() as db, redis_client_ctx() as redis:
        service = ApplicationService(db=db, redis=redis)
        try:
            await service.increment_retry_count(application_id)
            await service.transition_status(
                application_id=application_id,
                new_status=ApplicationStatus.EMAIL_FAILED,
                reason=f"Email send failed temporarily (will retry): {error}",
            )
        except Exception as exc:
            logger.error("task.mark_retryable_failed_error", error=str(exc))


async def _mark_permanently_failed(application_id: str, error: str) -> None:
    """Mark an application as permanently failed after max retries."""
    async with get_db_session() as db, redis_client_ctx() as redis:
        service = ApplicationService(db=db, redis=redis)
        try:
            await service.transition_status(
                application_id=application_id,
                new_status=ApplicationStatus.FAILED,
                reason=f"Max retries exhausted: {error}",
            )
        except Exception as exc:
            logger.error("task.mark_failed_error", error=str(exc))


@celery_app.task(
    name="app.tasks.application_tasks.cleanup_stale_applications",
    queue="low",
)
def cleanup_stale_applications() -> dict:
    """
    Periodic task (Celery Beat, every 30 minutes).

    In Phase A: finds applications stuck in PROCESSING for > 15 minutes
    and marks them as FAILED. Guards against worker crashes that
    leave applications orphaned in PROCESSING state.
    """
    task_logger.info("[BEAT] Running stale application cleanup")

    async def _cleanup():
        from datetime import timedelta
        from sqlalchemy import select
        from app.models.orm import Application

        cutoff = datetime.now(UTC) - timedelta(minutes=15)

        async with get_db_session() as db, redis_client_ctx() as redis:
            stmt = select(Application).where(
                Application.status == ApplicationStatus.PROCESSING.value,
                Application.updated_at < cutoff,
                Application.deleted_at.is_(None),
            )
            result = await db.execute(stmt)
            stale = result.scalars().all()

            service = ApplicationService(db=db, redis=redis)
            cleaned = 0
            for app in stale:
                try:
                    await service.transition_status(
                        application_id=str(app.application_id),
                        new_status=ApplicationStatus.FAILED,
                        reason="Cleaned up: stuck in PROCESSING for >15 minutes",
                    )
                    cleaned += 1
                    logger.warning(
                        "task.cleanup.stale_recovered",
                        application_id=str(app.application_id),
                    )
                except Exception as exc:
                    logger.error(
                        "task.cleanup.error",
                        application_id=str(app.application_id),
                        error=str(exc),
                    )

            return cleaned

    cleaned_count = run_async(_cleanup())
    task_logger.info(f"[BEAT] Cleanup complete. Recovered {cleaned_count} stale applications.")
    return {"cleaned": cleaned_count}
