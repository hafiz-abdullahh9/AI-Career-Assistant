"""
Application Service — all business logic for the application lifecycle.

Rules enforced here (NOT in routes):
  1. Guardrails (rate limit, dedup, job verification)
  2. Application record creation and status management
  3. Status transition validation
  4. DB persistence of logs and history
  5. Celery task enqueueing

Routes call services. Services call repositories (DB) and infrastructure (Redis).
No SQLAlchemy queries in route handlers. No business rules in tasks.
"""
import uuid
from datetime import UTC, datetime, date

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    DuplicateApplicationError,
    InvalidStatusTransitionError,
    NotFoundError,
    RateLimitExceededError,
)
from app.core.redis import rate_limit_key, dedup_key, task_lock_key
from app.models.orm import Application, ApplicationLog, ApplicationStatusHistory
from app.models.schemas import (
    ApplicationMethod,
    ApplicationStatus,
    ApplicationSubmitRequest,
    VALID_TRANSITIONS,
)

logger = structlog.get_logger(__name__)


class ApplicationService:
    """
    Encapsulates all business logic for job application lifecycle management.

    Instantiated per-request (or per-task) with injected dependencies.
    """

    def __init__(self, db: AsyncSession, redis) -> None:
        self._db = db
        self._redis = redis
        self._settings = get_settings()

    # ── Guardrails ──────────────────────────────────────────────────────────────

    async def check_rate_limit(self, user_id: str) -> None:
        """
        Enforce the daily application limit for a user.

        Uses Redis INCR with a 48-hour TTL so limits automatically reset.
        Raises RateLimitExceededError if the limit is already reached.
        """
        today = date.today().strftime("%Y%m%d")
        key = rate_limit_key(user_id, today)

        current = await self._redis.get(key)
        limit = self._settings.daily_application_limit_default

        if current and int(current) >= limit:
            logger.warning(
                "guardrail.rate_limit_exceeded",
                user_id=user_id,
                current=int(current),
                limit=limit,
            )
            raise RateLimitExceededError(
                f"Daily application limit of {limit} reached. Resets tomorrow.",
                details={"current": int(current), "limit": limit},
            )

    async def check_duplicate(self, user_id: str, job_id: str) -> None:
        """
        Prevent double-applying to the same job.

        Two-layer check: Redis fast path + DB fallback for durability.
        """
        # Fast path: Redis dedup cache
        key = dedup_key(user_id, job_id)
        if await self._redis.exists(key):
            raise DuplicateApplicationError(
                f"Already applied to job {job_id}.",
                details={"job_id": job_id},
            )

        # DB fallback (covers cases where Redis was cleared)
        stmt = select(Application).where(
            Application.user_id == uuid.UUID(user_id),
            Application.job_id == uuid.UUID(job_id),
            Application.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            raise DuplicateApplicationError(
                f"Already applied to job {job_id} (status: {existing.status}).",
                details={"job_id": job_id, "existing_application_id": str(existing.application_id)},
            )

    async def create_application(
        self,
        request: ApplicationSubmitRequest,
    ) -> Application:
        """
        Persist a new application record in QUEUED state.

        This is the single point of truth for creating applications.
        All guardrails must have already been checked before calling this.
        """
        meta_payload = {
            "manual_approval_required": request.guardrails.manual_approval_required,
            "resume": {
                "version_id": str(request.resume.version_id),
                "storage_url": request.resume.storage_url,
                "filename": request.resume.filename,
            }
        }
        if request.cover_letter:
            meta_payload["cover_letter"] = {
                "version_id": str(request.cover_letter.version_id),
                "storage_url": request.cover_letter.storage_url,
                "content_text": request.cover_letter.content_text,
            }

        application = Application(
            user_id=request.user_id,
            job_id=request.job_id,
            company_name=request.job_metadata.company_name,
            role_title=request.job_metadata.role_title,
            platform=request.job_metadata.platform,
            application_url=request.job_metadata.application_url,
            contact_email=request.job_metadata.contact_email,
            method=request.job_metadata.application_method.value,
            status=ApplicationStatus.QUEUED.value,
            resume_version_id=request.resume.version_id,
            cover_letter_version_id=(
                request.cover_letter.version_id if request.cover_letter else None
            ),
            deadline=request.job_metadata.deadline,
            max_retries=request.guardrails.max_retries,
            metadata_=meta_payload,
        )
        self._db.add(application)
        await self._db.flush()  # Get the generated application_id

        # Log the initial state transition
        await self._append_status_history(
            application=application,
            from_status=None,
            to_status=ApplicationStatus.QUEUED,
            reason="Application received from orchestrator",
        )

        await self._append_log(
            application=application,
            level="INFO",
            event="application.created",
            message=f"Application queued for {application.company_name} — {application.role_title}",
            context={
                "method": application.method,
                "platform": application.platform,
            },
        )

        logger.info(
            "application.created",
            application_id=str(application.application_id),
            user_id=str(request.user_id),
            company=application.company_name,
            method=application.method,
        )
        return application

    # ── Status management ───────────────────────────────────────────────────────

    async def transition_status(
        self,
        application_id: str,
        new_status: ApplicationStatus,
        reason: str | None = None,
        changed_by: str = "system",
        context: dict | None = None,
    ) -> Application:
        """
        Transition an application to a new status.

        Validates the transition is allowed per VALID_TRANSITIONS.
        Logs the change to status_history and application_logs.
        """
        application = await self._get_application(application_id)

        current = ApplicationStatus(application.status)
        allowed = VALID_TRANSITIONS.get(current, set())

        if new_status not in allowed:
            raise InvalidStatusTransitionError(
                f"Cannot transition from '{current}' to '{new_status}'.",
                details={"from": current.value, "to": new_status.value, "allowed": [s.value for s in allowed]},
            )

        old_status = application.status
        application.status = new_status.value

        if new_status in (ApplicationStatus.APPLIED, ApplicationStatus.EMAIL_SENT):
            application.applied_at = datetime.now(UTC)

        await self._append_status_history(
            application=application,
            from_status=current,
            to_status=new_status,
            reason=reason,
            changed_by=changed_by,
        )

        await self._append_log(
            application=application,
            level="INFO",
            event="application.status_changed",
            message=f"Status changed: {old_status} → {new_status.value}",
            context={"reason": reason, "changed_by": changed_by, **(context or {})},
        )

        logger.info(
            "application.status_changed",
            application_id=application_id,
            from_status=old_status,
            to_status=new_status.value,
            reason=reason,
        )
        return application

    async def attach_task_id(self, application_id: str, task_id: str) -> None:
        """Record the Celery task ID on the application for observability."""
        application = await self._get_application(application_id)
        application.celery_task_id = task_id

    async def set_confirmation(self, application_id: str, confirmation_id: str) -> None:
        """Record the platform-issued confirmation/reference ID."""
        application = await self._get_application(application_id)
        application.confirmation_id = confirmation_id

        await self._append_log(
            application=application,
            level="INFO",
            event="application.confirmed",
            message=f"Confirmation captured: {confirmation_id}",
            context={"confirmation_id": confirmation_id},
        )

    async def increment_retry_count(self, application_id: str) -> Application:
        """Increment retry counter. Resets status to QUEUED for next attempt."""
        application = await self._get_application(application_id)
        application.retry_count += 1

        await self._append_log(
            application=application,
            level="WARNING",
            event="application.retry",
            message=f"Retry attempt {application.retry_count}/{application.max_retries}",
            context={"retry_count": application.retry_count},
        )
        return application

    async def mark_daily_counter(self, user_id: str) -> None:
        """
        Increment the user's daily application counter in Redis.

        Called AFTER a successful submission to count it against the daily limit.
        Uses pipeline for atomicity.
        """
        today = date.today().strftime("%Y%m%d")
        key = rate_limit_key(user_id, today)

        pipe = self._redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 48 * 3600)  # 48h TTL — clears automatically after tomorrow
        await pipe.execute()

    async def mark_dedup_cache(self, user_id: str, job_id: str) -> None:
        """
        Mark this (user, job) pair as applied in the dedup cache.
        TTL: 90 days — well beyond any application window.
        """
        key = dedup_key(user_id, job_id)
        await self._redis.set(key, "1", ex=90 * 24 * 3600)

    # ── Queries ─────────────────────────────────────────────────────────────────

    async def get_application(self, application_id: str) -> Application:
        """Public getter — raises NotFoundError if not found."""
        return await self._get_application(application_id)

    async def list_applications(
        self,
        user_id: str,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Application], int]:
        """Return paginated list of applications for a user."""
        stmt = (
            select(Application)
            .where(
                Application.user_id == uuid.UUID(user_id),
                Application.deleted_at.is_(None),
            )
            .order_by(Application.queued_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status:
            stmt = stmt.where(Application.status == status)

        result = await self._db.execute(stmt)
        applications = list(result.scalars().all())

        # Count total for pagination
        count_stmt = select(func.count()).select_from(Application).where(
            Application.user_id == uuid.UUID(user_id),
            Application.deleted_at.is_(None),
        )
        if status:
            count_stmt = count_stmt.where(Application.status == status)
        total = (await self._db.execute(count_stmt)).scalar_one()

        return applications, total

    async def get_status_history(self, application_id: str) -> list[ApplicationStatusHistory]:
        """Return all status transitions for an application, newest first."""
        stmt = (
            select(ApplicationStatusHistory)
            .where(ApplicationStatusHistory.application_id == uuid.UUID(application_id))
            .order_by(ApplicationStatusHistory.created_at.desc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def soft_delete(self, application_id: str) -> Application:
        """Soft-delete: set deleted_at timestamp, never remove the row."""
        application = await self._get_application(application_id)
        application.deleted_at = datetime.now(UTC)

        await self._append_log(
            application=application,
            level="INFO",
            event="application.deleted",
            message="Application soft-deleted by user",
            context={},
        )
        return application

    # ── Private helpers ─────────────────────────────────────────────────────────

    async def _get_application(self, application_id: str) -> Application:
        stmt = select(Application).where(
            Application.application_id == uuid.UUID(application_id),
            Application.deleted_at.is_(None),
        )
        result = await self._db.execute(stmt)
        application = result.scalar_one_or_none()
        if application is None:
            raise NotFoundError(
                f"Application {application_id} not found.",
                details={"application_id": application_id},
            )
        return application

    async def _append_status_history(
        self,
        application: Application,
        from_status: ApplicationStatus | None,
        to_status: ApplicationStatus,
        reason: str | None = None,
        changed_by: str = "system",
    ) -> None:
        history = ApplicationStatusHistory(
            application_id=application.application_id,
            from_status=from_status.value if from_status else None,
            to_status=to_status.value,
            reason=reason,
            changed_by=changed_by,
        )
        self._db.add(history)

    async def _append_log(
        self,
        application: Application,
        level: str,
        event: str,
        message: str,
        context: dict,
    ) -> None:
        import structlog
        trace_id = structlog.contextvars.get_contextvars().get("trace_id")
        log = ApplicationLog(
            application_id=application.application_id,
            level=level,
            event=event,
            message=message,
            context=context,
            trace_id=trace_id,
        )
        self._db.add(log)
