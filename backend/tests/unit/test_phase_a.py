"""
Phase A Unit Tests — Schemas, Guardrails, Status Machine

These tests run with NO external dependencies (no DB, no Redis, no Celery).
Fast, isolated, deterministic.
"""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import ValidationError

from app.core.exceptions import (
    DuplicateApplicationError,
    InvalidStatusTransitionError,
    RateLimitExceededError,
)
from app.models.schemas import (
    ApplicationMethod,
    ApplicationStatus,
    ApplicationSubmitRequest,
    GuardrailConfig,
    JobMetadata,
    ResumeAsset,
    VALID_TRANSITIONS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def valid_email_request() -> dict:
    return {
        "user_id": str(uuid.uuid4()),
        "job_id": str(uuid.uuid4()),
        "job_metadata": {
            "company_name": "Acme Corp",
            "role_title": "Senior Engineer",
            "application_method": "email",
            "contact_email": "jobs@acme.example.com",
        },
        "resume": {
            "version_id": str(uuid.uuid4()),
            "storage_url": "https://our-storage.example.com/resume.pdf",
            "filename": "My_Resume.pdf",
        },
    }


@pytest.fixture
def valid_webform_request() -> dict:
    return {
        "user_id": str(uuid.uuid4()),
        "job_id": str(uuid.uuid4()),
        "job_metadata": {
            "company_name": "TechCorp",
            "role_title": "Data Engineer",
            "application_method": "web_form",
            "application_url": "https://boards.greenhouse.io/techcorp/jobs/123",
        },
        "resume": {
            "version_id": str(uuid.uuid4()),
            "storage_url": "https://our-storage.example.com/resume.pdf",
            "filename": "Resume.pdf",
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Schema Validation Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestApplicationSubmitRequestSchema:

    def test_valid_email_request_passes(self, valid_email_request):
        req = ApplicationSubmitRequest(**valid_email_request)
        assert req.job_metadata.company_name == "Acme Corp"
        assert req.job_metadata.application_method == ApplicationMethod.EMAIL

    def test_valid_webform_request_passes(self, valid_webform_request):
        req = ApplicationSubmitRequest(**valid_webform_request)
        assert req.job_metadata.application_method == ApplicationMethod.WEB_FORM

    def test_email_method_requires_contact_email(self, valid_email_request):
        valid_email_request["job_metadata"]["contact_email"] = None
        with pytest.raises(ValidationError, match="contact_email is required"):
            ApplicationSubmitRequest(**valid_email_request)

    def test_webform_method_requires_application_url(self, valid_webform_request):
        valid_email_request = valid_webform_request.copy()
        valid_email_request["job_metadata"] = valid_webform_request["job_metadata"].copy()
        valid_email_request["job_metadata"]["application_url"] = None
        with pytest.raises(ValidationError, match="application_url is required"):
            ApplicationSubmitRequest(**valid_email_request)

    def test_non_pdf_resume_rejected(self, valid_email_request):
        valid_email_request["resume"]["filename"] = "resume.docx"
        with pytest.raises(ValidationError, match="must be a PDF"):
            ApplicationSubmitRequest(**valid_email_request)

    def test_path_traversal_filename_rejected(self, valid_email_request):
        valid_email_request["resume"]["filename"] = "../../etc/passwd.pdf"
        with pytest.raises(ValidationError, match="path traversal"):
            ApplicationSubmitRequest(**valid_email_request)

    def test_non_https_storage_url_rejected(self, valid_email_request):
        valid_email_request["resume"]["storage_url"] = "http://insecure.example.com/resume.pdf"
        with pytest.raises(ValidationError, match="HTTPS"):
            ApplicationSubmitRequest(**valid_email_request)

    def test_default_guardrails_applied(self, valid_email_request):
        req = ApplicationSubmitRequest(**valid_email_request)
        assert req.guardrails.manual_approval_required is False
        assert req.guardrails.max_retries == 3
        assert req.guardrails.priority.value == "normal"

    def test_max_retries_upper_bound(self, valid_email_request):
        valid_email_request["guardrails"] = {"max_retries": 999}
        with pytest.raises(ValidationError):
            ApplicationSubmitRequest(**valid_email_request)


# ─────────────────────────────────────────────────────────────────────────────
# Status Transition Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestStatusTransitions:

    def test_queued_can_transition_to_processing(self):
        allowed = VALID_TRANSITIONS[ApplicationStatus.QUEUED]
        assert ApplicationStatus.PROCESSING in allowed

    def test_queued_cannot_transition_to_applied_directly(self):
        allowed = VALID_TRANSITIONS[ApplicationStatus.QUEUED]
        assert ApplicationStatus.APPLIED not in allowed

    def test_processing_can_transition_to_applied(self):
        allowed = VALID_TRANSITIONS[ApplicationStatus.PROCESSING]
        assert ApplicationStatus.APPLIED in allowed

    def test_processing_can_transition_to_failed(self):
        allowed = VALID_TRANSITIONS[ApplicationStatus.PROCESSING]
        assert ApplicationStatus.FAILED in allowed

    def test_applied_can_transition_to_interview(self):
        allowed = VALID_TRANSITIONS[ApplicationStatus.APPLIED]
        assert ApplicationStatus.INTERVIEW in allowed

    def test_applied_can_transition_to_rejected(self):
        allowed = VALID_TRANSITIONS[ApplicationStatus.APPLIED]
        assert ApplicationStatus.REJECTED in allowed

    def test_failed_is_terminal_state(self):
        allowed = VALID_TRANSITIONS[ApplicationStatus.FAILED]
        assert len(allowed) == 0

    def test_accepted_is_terminal_state(self):
        allowed = VALID_TRANSITIONS[ApplicationStatus.ACCEPTED]
        assert len(allowed) == 0

    def test_all_statuses_have_transition_entries(self):
        """Every status must have an entry in VALID_TRANSITIONS (even if empty)."""
        for status in ApplicationStatus:
            assert status in VALID_TRANSITIONS, f"{status} missing from VALID_TRANSITIONS"


# ─────────────────────────────────────────────────────────────────────────────
# Guardrails Unit Tests (mocked Redis + DB)
# ─────────────────────────────────────────────────────────────────────────────

class TestGuardrailsService:

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_redis(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db, mock_redis):
        from app.services.application_service import ApplicationService
        return ApplicationService(db=mock_db, redis=mock_redis)

    @pytest.mark.asyncio
    async def test_rate_limit_passes_when_under_limit(self, service, mock_redis):
        mock_redis.get.return_value = "12"   # Under the 50 default
        # Should not raise
        await service.check_rate_limit("user-123")

    @pytest.mark.asyncio
    async def test_rate_limit_raises_when_at_limit(self, service, mock_redis):
        mock_redis.get.return_value = "50"   # At the 50 default
        with pytest.raises(RateLimitExceededError):
            await service.check_rate_limit("user-123")

    @pytest.mark.asyncio
    async def test_rate_limit_passes_when_counter_missing(self, service, mock_redis):
        mock_redis.get.return_value = None   # No counter yet (first app of the day)
        # Should not raise
        await service.check_rate_limit("user-123")

    @pytest.mark.asyncio
    async def test_duplicate_detected_via_redis(self, service, mock_redis):
        mock_redis.exists.return_value = 1   # Key exists = already applied
        user_uuid = str(uuid.uuid4())
        job_uuid = str(uuid.uuid4())
        with pytest.raises(DuplicateApplicationError):
            await service.check_duplicate(user_uuid, job_uuid)

    @pytest.mark.asyncio
    async def test_no_duplicate_when_redis_clean_and_db_empty(self, service, mock_redis, mock_db):
        mock_redis.exists.return_value = 0
        # Simulate DB returning no existing application
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        user_uuid = str(uuid.uuid4())
        job_uuid = str(uuid.uuid4())
        # Should not raise
        await service.check_duplicate(user_uuid, job_uuid)



# ─────────────────────────────────────────────────────────────────────────────
# Redis Key Builder Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRedisKeyBuilders:

    def test_rate_limit_key_format(self):
        from app.core.redis import rate_limit_key
        key = rate_limit_key("user-abc", "20260612")
        assert key == "rate:daily:user-abc:20260612"

    def test_dedup_key_format(self):
        from app.core.redis import dedup_key
        key = dedup_key("user-abc", "job-xyz")
        assert key == "dedup:applied:user-abc:job-xyz"

    def test_task_lock_key_format(self):
        from app.core.redis import task_lock_key
        key = task_lock_key("app-id-123")
        assert key == "task:lock:app-id-123"

    def test_rate_limit_key_is_unique_per_day(self):
        from app.core.redis import rate_limit_key
        key1 = rate_limit_key("user-abc", "20260612")
        key2 = rate_limit_key("user-abc", "20260613")
        assert key1 != key2

    def test_dedup_key_is_unique_per_job(self):
        from app.core.redis import dedup_key
        key1 = dedup_key("user-abc", "job-1")
        key2 = dedup_key("user-abc", "job-2")
        assert key1 != key2
