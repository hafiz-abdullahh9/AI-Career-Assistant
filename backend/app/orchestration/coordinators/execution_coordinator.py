import uuid
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.orm import Application
from app.models.schemas import ApplicationStatus, ApplicationMethod
from app.core.exceptions import (
    RateLimitExceededError,
    DuplicateApplicationError,
    ForbiddenError,
    AppBaseError
)

# Policies and Helpers
from app.orchestration.policies.execution_policies import (
    DomainAllowlistPolicy,
    ApprovalGatePolicy,
    RetryPolicy
)
from app.orchestration.rate_limits.rate_limiter import RateLimiter
from app.orchestration.quotas.quota_manager import QuotaManager
from app.orchestration.deduplication.deduplicator import Deduplicator
from app.orchestration.pause_resume.pause_resume_control import PauseResumeControl
from app.orchestration.approvals.approval_gate import ApprovalGate
from app.orchestration.services.concurrency_guard import ConcurrencyGuard
from app.orchestration.telemetry.governance_telemetry import GovernanceTelemetry
from app.orchestration.schemas.governance_schemas import GovernanceEventType

logger = structlog.get_logger(__name__)


class ExecutionCoordinatorError(AppBaseError):
    error_code = "COORDINATOR_ERROR"
    status_code = 400


class ExecutionPausedError(ExecutionCoordinatorError):
    error_code = "EXECUTION_PAUSED"
    status_code = 503


class ExecutionCoordinator:
    """
    Main controller coordinating submission lifecycle, queue state, safety gates,
    approval flows, distributed locks, rate limit counters, and governance telemetry.
    """

    def __init__(self, db: AsyncSession, redis) -> None:
        self.db = db
        self.redis = redis
        self.rate_limiter = RateLimiter(redis)
        self.quota_manager = QuotaManager(redis)
        self.deduplicator = Deduplicator(redis)
        self.pause_resume = PauseResumeControl(redis)
        self.concurrency_guard = ConcurrencyGuard(redis)
        self.approval_gate = ApprovalGate()

    async def pre_evaluate(
        self,
        user_id: str,
        job_id: str,
        company_name: str,
        role_title: str,
        url: str | None,
        method: str,
        manual_approval_required: bool,
        priority: str,
        user_tier: str = "standard"
    ) -> dict:
        """
        Evaluate all governance policies BEFORE creating or executing an application.
        Throws appropriate exceptions on policy failures.
        Returns:
            dict containing:
              - 'status': 'allowed' | 'pending_approval' | 'paused'
              - 'reason': optional description string
              - 'token': optional approval token
              - 'retry_after_sec': delay before retry if rate limited/paused
        """
        # 1. Emergency Stop Check
        if await self.pause_resume.is_emergency_stop_active():
            raise ExecutionCoordinatorError("System under emergency stop. No applications processed.")

        # 2. Domain Allowlist Check
        if method == "web_form" and url:
            if not DomainAllowlistPolicy.check_url(url):
                # Fake an application ID for logging if not created yet
                fake_app_id = str(uuid.uuid4())
                await GovernanceTelemetry.record_event(
                    db=self.db,
                    application_id=fake_app_id,
                    user_id=user_id,
                    event_type=GovernanceEventType.ALLOWLIST_REJECT,
                    policy_name="DomainAllowlistPolicy",
                    reason=f"URL domain is not in allowlist: {url}"
                )
                raise ForbiddenError(f"Target URL domain not allowlisted for automation: {url}")

        # 3. Deduplication Check
        dedup_res = await self.deduplicator.check_duplicate(self.db, user_id, company_name, role_title, url)
        if dedup_res.is_duplicate:
            fake_app_id = dedup_res.existing_application_id or str(uuid.uuid4())
            await GovernanceTelemetry.record_event(
                db=self.db,
                application_id=fake_app_id,
                user_id=user_id,
                event_type=GovernanceEventType.DEDUP_REJECT,
                policy_name="DeduplicationPolicy",
                reason=dedup_res.reason or "Duplicate application"
            )
            raise DuplicateApplicationError(dedup_res.reason or "Duplicate application detected.")

        # 4. Plan Daily Quota Check
        quota_res = await self.quota_manager.check_user_quota(user_id, user_tier)
        if not quota_res.allowed:
            fake_app_id = str(uuid.uuid4())
            await GovernanceTelemetry.record_event(
                db=self.db,
                application_id=fake_app_id,
                user_id=user_id,
                event_type=GovernanceEventType.QUOTA_HIT,
                policy_name="QuotaPolicy",
                reason=quota_res.reason or "Quota exceeded"
            )
            raise RateLimitExceededError(quota_res.reason or "User daily quota exceeded.")

        # 5. Platform Rate Limit / Interval Check
        platform = "default"
        if method == "web_form" and url:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            netloc = parsed.netloc.lower()
            if netloc.startswith("www."):
                netloc = netloc[4:]
            platform = netloc.split(".")[0] if "." in netloc else netloc
        elif method == "email":
            platform = "email"

        rate_res = await self.rate_limiter.check_platform_limit(user_id, platform)
        if not rate_res.allowed:
            fake_app_id = str(uuid.uuid4())
            await GovernanceTelemetry.record_event(
                db=self.db,
                application_id=fake_app_id,
                user_id=user_id,
                event_type=GovernanceEventType.RATE_LIMIT_HIT,
                policy_name="RateLimitPolicy",
                reason=rate_res.reason or "Platform rate limit hit",
                metadata={"platform": platform, "retry_after_sec": rate_res.retry_after_sec}
            )
            if rate_res.retry_after_sec > 0:
                return {
                    "status": "paused",
                    "reason": rate_res.reason,
                    "retry_after_sec": rate_res.retry_after_sec
                }
            raise RateLimitExceededError(rate_res.reason or "Platform daily rate limit reached.")

        # 6. Check Pause State
        if await self.pause_resume.is_paused(user_id=user_id, domain=platform):
            return {
                "status": "paused",
                "reason": f"Execution queue or domain '{platform}' is currently paused.",
                "retry_after_sec": 60.0
            }

        # 7. Manual Approval Check
        if ApprovalGatePolicy.requires_approval(manual_approval_required, priority, platform):
            return {
                "status": "pending_approval",
                "reason": f"Manual approval gate triggered (priority={priority}, platform={platform})."
            }

        return {"status": "allowed"}

    async def handle_approval_trigger(
        self,
        application: Application,
        reason: str
    ) -> str:
        """
        Puts application in PENDING_APPROVAL and saves approval request token.
        """
        # Update status
        application.status = ApplicationStatus.PENDING_APPROVAL.value
        
        # Save request and token
        gate_res = await self.approval_gate.request_approval(self.db, application, reason)
        
        await GovernanceTelemetry.record_event(
            db=self.db,
            application_id=str(application.application_id),
            user_id=str(application.user_id),
            event_type=GovernanceEventType.APPROVAL_REQUESTED,
            policy_name="ApprovalGatePolicy",
            reason=reason,
            metadata={"token": gate_res.token}
        )
        return gate_res.token

    async def acquire_execution_slots(
        self,
        user_id: str,
        job_id: str,
        method: str
    ) -> bool:
        """
        Tries to acquire user-job distributed lock and, if web_form, browser slots.
        """
        # User-Job lock
        locked = await self.concurrency_guard.acquire_job_lock(user_id, job_id)
        if not locked:
            logger.warning("concurrency.lock_failed", user_id=user_id, job_id=job_id)
            return False

        # Browser session semaphore
        if method == "web_form":
            slot_acquired = await self.concurrency_guard.acquire_browser_session()
            if not slot_acquired:
                logger.warning("concurrency.semaphore_failed", user_id=user_id, job_id=job_id)
                # Release lock if semaphore failed
                await self.concurrency_guard.release_job_lock(user_id, job_id)
                return False

        return True

    async def release_execution_slots(
        self,
        user_id: str,
        job_id: str,
        method: str
    ) -> None:
        """
        Release acquired locks/semaphores.
        """
        await self.concurrency_guard.release_job_lock(user_id, job_id)
        if method == "web_form":
            await self.concurrency_guard.release_browser_session()

    async def record_successful_execution(
        self,
        user_id: str,
        platform: str,
        company_name: str,
        role_title: str,
        url: str | None
    ) -> None:
        """
        Increments quotas, platform rates, and registers applied dedup state.
        """
        await self.quota_manager.record_user_application(user_id)
        await self.rate_limiter.record_application(user_id, platform)
        # Store in long-term dedup (and short term 24h)
        await self.deduplicator.record_applied(
            user_id=user_id,
            company=company_name,
            role=role_title,
            url=url,
            application_id=""  # can store empty or populate as needed
        )
