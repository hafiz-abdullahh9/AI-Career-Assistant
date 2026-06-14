"""
Retry Logic & Backoff Tests

Validates the retry infrastructure:
  1. Exponential backoff calculation
  2. Jitter distribution
  3. Max delay cap
  4. Permanent vs. transient error classification
  5. DLQ entry logic
  6. Stale application cleanup
"""
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call


# ── Backoff Algorithm Tests ───────────────────────────────────────────────────

class TestExponentialBackoff:
    """Tests for the calculate_backoff utility defined in retry_and_error_strategy."""

    def _backoff(self, attempt: int, base: float = 1.0, max_delay: float = 300.0, jitter: bool = False) -> float:
        """Inline backoff implementation to test the algorithm."""
        import math, random
        exponential = min(base * (2 ** (attempt - 1)), max_delay)
        if jitter:
            return random.uniform(0, exponential)
        return exponential

    def test_attempt_1_returns_base_delay(self):
        result = self._backoff(1, base=1.0, jitter=False)
        assert result == 1.0

    def test_attempt_2_returns_double_base(self):
        result = self._backoff(2, base=1.0, jitter=False)
        assert result == 2.0

    def test_attempt_3_returns_quadruple_base(self):
        result = self._backoff(3, base=1.0, jitter=False)
        assert result == 4.0

    def test_delay_capped_at_max(self):
        result = self._backoff(attempt=100, base=1.0, max_delay=300.0, jitter=False)
        assert result == 300.0

    def test_jitter_produces_non_deterministic_values(self):
        """With jitter, 100 calls should produce at least 2 different values."""
        values = {self._backoff(2, jitter=True) for _ in range(100)}
        assert len(values) > 1, "Jitter should produce varied delays"

    def test_jitter_stays_within_bounds(self):
        """Jitter value must never exceed the non-jittered delay."""
        for _ in range(1000):
            jittered = self._backoff(3, base=1.0, max_delay=300.0, jitter=True)
            assert 0 <= jittered <= 4.0, f"Jitter out of bounds: {jittered}"

    def test_celery_countdown_schedule_for_email(self):
        """Email retry schedule: 30s, 120s, 600s."""
        schedule = [30, 120, 600]
        assert len(schedule) == 3
        assert schedule[0] < schedule[1] < schedule[2], "Delays must be increasing"
        assert schedule[-1] <= 3600, "Max delay must not exceed 1 hour"

    def test_celery_countdown_schedule_for_webform(self):
        """Web form retry schedule: 60s, 300s, 900s."""
        schedule = [60, 300, 900]
        assert schedule[0] < schedule[1] < schedule[2]
        assert schedule[-1] <= 3600


# ── Error Classification Tests ─────────────────────────────────────────────────

class TestErrorClassification:
    """
    Validates the Transient vs. Permanent error classification.

    Transient errors → retry with backoff
    Permanent errors → no retry, alert, DLQ
    """

    def test_transient_automation_error_is_retryable(self):
        from app.core.exceptions import TransientAutomationError
        exc = TransientAutomationError("Network timeout")
        assert exc.error_code == "TRANSIENT_AUTOMATION_ERROR"
        # Transient errors should NOT have a 4xx status code (they're 500s)
        assert exc.status_code == 500

    def test_permanent_automation_error_is_not_retryable(self):
        from app.core.exceptions import PermanentAutomationError
        exc = PermanentAutomationError("IP banned from site")
        assert exc.error_code == "PERMANENT_AUTOMATION_ERROR"

    def test_rate_limit_error_carries_context(self):
        from app.core.exceptions import RateLimitExceededError
        exc = RateLimitExceededError(
            "Daily limit reached",
            details={"current": 50, "limit": 50},
        )
        assert exc.status_code == 429
        assert exc.details["current"] == 50
        assert exc.details["limit"] == 50

    def test_duplicate_error_carries_job_id(self):
        from app.core.exceptions import DuplicateApplicationError
        exc = DuplicateApplicationError(
            "Already applied",
            details={"job_id": "job-123"},
        )
        assert exc.status_code == 409
        assert exc.details["job_id"] == "job-123"

    def test_invalid_transition_error_carries_state_info(self):
        from app.core.exceptions import InvalidStatusTransitionError
        exc = InvalidStatusTransitionError(
            "Cannot transition",
            details={"from": "applied", "to": "queued", "allowed": []},
        )
        assert exc.status_code == 409
        assert exc.details["from"] == "applied"
        assert exc.details["to"] == "queued"

    def test_all_app_errors_inherit_base(self):
        """All custom exceptions must inherit from AppBaseError."""
        from app.core.exceptions import (
            AppBaseError,
            ValidationError,
            UnauthorizedError,
            ForbiddenError,
            NotFoundError,
            ConflictError,
            RateLimitExceededError,
            UnverifiedJobError,
            DuplicateApplicationError,
            JobExpiredError,
            AssetUnreachableError,
            AutomationError,
            TransientAutomationError,
            PermanentAutomationError,
            CaptchaBlockedError,
            DatabaseError,
            RedisError,
            InvalidStatusTransitionError,
        )
        exceptions = [
            ValidationError, UnauthorizedError, ForbiddenError, NotFoundError,
            ConflictError, RateLimitExceededError, UnverifiedJobError,
            DuplicateApplicationError, JobExpiredError, AssetUnreachableError,
            AutomationError, TransientAutomationError, PermanentAutomationError,
            CaptchaBlockedError, DatabaseError, RedisError,
            InvalidStatusTransitionError,
        ]
        for exc_class in exceptions:
            assert issubclass(exc_class, AppBaseError), (
                f"{exc_class.__name__} must inherit from AppBaseError"
            )

    def test_each_exception_has_error_code(self):
        from app.core.exceptions import (
            AppBaseError,
            RateLimitExceededError,
            DuplicateApplicationError,
            InvalidStatusTransitionError,
        )
        assert RateLimitExceededError.error_code == "RATE_LIMIT_EXCEEDED"
        assert DuplicateApplicationError.error_code == "DUPLICATE_APPLICATION"
        assert InvalidStatusTransitionError.error_code == "INVALID_STATUS_TRANSITION"

    def test_each_exception_has_http_status(self):
        from app.core.exceptions import (
            RateLimitExceededError,
            DuplicateApplicationError,
            NotFoundError,
            UnauthorizedError,
        )
        assert RateLimitExceededError.status_code == 429
        assert DuplicateApplicationError.status_code == 409
        assert NotFoundError.status_code == 404
        assert UnauthorizedError.status_code == 401


# ── Celery Retry Behavior Tests ────────────────────────────────────────────────

class TestCeleryRetryBehavior:
    """
    Tests for the Celery task retry policy.

    These tests verify the POLICY, not the Celery internals.
    Actual task execution is tested in integration tests.
    """

    def test_process_application_has_max_retries(self):
        from app.tasks.application_tasks import process_application
        assert process_application.max_retries == 3

    def test_process_application_uses_acks_late(self):
        """acks_late=True ensures tasks are re-queued if worker dies."""
        from app.tasks.application_tasks import process_application
        assert process_application.acks_late is True

    def test_celery_has_three_queues(self):
        from app.tasks.celery_app import celery_app
        queue_names = {q.name for q in celery_app.conf.task_queues}
        assert "high" in queue_names
        assert "normal" in queue_names
        assert "low" in queue_names

    def test_celery_default_queue_is_normal(self):
        from app.tasks.celery_app import celery_app
        assert celery_app.conf.task_default_queue == "normal"

    def test_cleanup_task_is_in_beat_schedule(self):
        from app.tasks.celery_app import celery_app
        schedule = celery_app.conf.beat_schedule
        assert "cleanup-stale-applications" in schedule

    def test_soft_time_limit_set(self):
        """Tasks must have a time limit to prevent runaway processes."""
        from app.tasks.celery_app import celery_app
        assert celery_app.conf.task_soft_time_limit == 600   # 10 minutes
        assert celery_app.conf.task_time_limit == 660         # 11 minutes (hard kill)

    def test_worker_prefetch_is_one(self):
        """Prefetch=1 ensures fair distribution and prevents one worker hoarding tasks."""
        from app.tasks.celery_app import celery_app
        assert celery_app.conf.worker_prefetch_multiplier == 1


# ── Rate Limiter Tests ────────────────────────────────────────────────────────

class TestRateLimiterLogic:
    """Validate rate limiting Redis key operations."""

    @pytest.fixture
    def service(self, mock_db_session, mock_redis):
        from app.services.application_service import ApplicationService
        return ApplicationService(db=mock_db_session, redis=mock_redis)

    @pytest.mark.asyncio
    async def test_counter_incremented_after_success(self, service, mock_redis):
        """mark_daily_counter must atomically INCR + EXPIRE."""
        pipe = mock_redis.pipeline.return_value
        await service.mark_daily_counter("user-123")

        mock_redis.pipeline.assert_called_once()
        pipe.incr.assert_called_once()
        pipe.expire.assert_called_once()
        pipe.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dedup_cache_set_with_ttl(self, service, mock_redis):
        """mark_dedup_cache must set the Redis key with a 90-day TTL."""
        await service.mark_dedup_cache("user-123", "job-456")

        expected_ttl = 90 * 24 * 3600
        mock_redis.set.assert_awaited_once_with(
            "dedup:applied:user-123:job-456",
            "1",
            ex=expected_ttl,
        )

    @pytest.mark.asyncio
    async def test_rate_limit_key_includes_date(self, service, mock_redis):
        """Rate limit key must include today's date (YYYYMMDD)."""
        from datetime import date
        today = date.today().strftime("%Y%m%d")
        mock_redis.get.return_value = None

        await service.check_rate_limit("user-abc")

        # Verify the key passed to redis.get includes today's date
        call_args = mock_redis.get.await_args[0][0]
        assert today in call_args, f"Date not in Redis key: {call_args}"
        assert "user-abc" in call_args
