import os
import time
import json
import pytest
import uuid
from datetime import datetime, UTC, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Application, ApprovalRequest
from app.models.schemas import ApplicationStatus, ApplicationMethod
from app.core.exceptions import ForbiddenError, DuplicateApplicationError, RateLimitExceededError

# Import Components Under Test
from app.orchestration.coordinators.execution_coordinator import ExecutionCoordinator
from app.orchestration.policies.execution_policies import (
    DomainAllowlistPolicy,
    ApprovalGatePolicy,
    RetryPolicy
)
from app.orchestration.rate_limits.rate_limiter import RateLimiter
from app.orchestration.quotas.quota_manager import QuotaManager
from app.orchestration.deduplication.deduplicator import Deduplicator, normalize_text, normalize_url
from app.orchestration.pause_resume.pause_resume_control import PauseResumeControl
from app.orchestration.services.concurrency_guard import ConcurrencyGuard
from app.orchestration.approvals.approval_gate import ApprovalGate


# --- Policy Unit Tests ---

def test_domain_allowlist_policy():
    assert DomainAllowlistPolicy.check_url(None) is True
    assert DomainAllowlistPolicy.check_url("file:///path/to/sandbox.html") is True
    assert DomainAllowlistPolicy.check_url("http://localhost:8000/sandbox") is True
    assert DomainAllowlistPolicy.check_url("https://www.greenhouse.io/jobs") is True
    assert DomainAllowlistPolicy.check_url("https://lever.co/careers") is True
    assert DomainAllowlistPolicy.check_url("https://unauthorized-site.com/apply") is False


def test_approval_gate_policy():
    assert ApprovalGatePolicy.requires_approval(manual_approval_required=True) is True
    assert ApprovalGatePolicy.requires_approval(manual_approval_required=False, priority="high") is True
    assert ApprovalGatePolicy.requires_approval(manual_approval_required=False, platform="linkedin") is True
    assert ApprovalGatePolicy.requires_approval(manual_approval_required=False, platform="greenhouse") is False


def test_retry_policy_calculation():
    # base delay 60
    assert 48.0 <= RetryPolicy.calculate_backoff(1, base_delay=60.0) <= 72.0
    assert 96.0 <= RetryPolicy.calculate_backoff(2, base_delay=60.0) <= 144.0
    # Capped at max delay
    assert RetryPolicy.calculate_backoff(5, base_delay=60.0, max_delay=300.0) <= 300.0


# --- Deduplication Normalization Tests ---

def test_dedup_normalization():
    assert normalize_text("Google Inc.") == "google"
    assert normalize_text("Facebook, LLC") == "facebook"
    assert normalize_text("Senior Software Engineer") == "senior software engineer"
    
    assert normalize_url("https://www.lever.co/jobs/123?utm_source=test/") == "https://lever.co/jobs/123"
    assert normalize_url("http://greenhouse.io/careers/") == "http://greenhouse.io/careers"


# --- Redis Mocking Helper Tests ---

@pytest.mark.asyncio
async def test_quota_manager():
    mock_redis = AsyncMock()
    # Mock daily quota not exceeded
    mock_redis.get.return_value = None
    manager = QuotaManager(mock_redis)
    user_id = str(uuid.uuid4())
    
    res = await manager.check_user_quota(user_id, "standard")
    assert res.allowed is True
    assert res.current_count == 0
    assert res.limit == 20

    # Mock daily quota exceeded
    mock_redis.get.return_value = b"25"
    res = await manager.check_user_quota(user_id, "standard")
    assert res.allowed is False
    assert res.current_count == 25
    assert res.limit == 20


@pytest.mark.asyncio
async def test_rate_limiter():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None  # No last applied, no daily count
    limiter = RateLimiter(mock_redis)
    user_id = str(uuid.uuid4())

    res = await limiter.check_platform_limit(user_id, "linkedin")
    assert res.allowed is True

    # Mock interval violation (last applied was 10 seconds ago)
    mock_redis.get.side_effect = [str(time.time() - 10.0).encode("utf-8"), None]
    res = await limiter.check_platform_limit(user_id, "linkedin")
    assert res.allowed is False
    assert "minimum interval" in res.reason


@pytest.mark.asyncio
async def test_pause_resume_control():
    mock_redis = AsyncMock()
    control = PauseResumeControl(mock_redis)
    
    mock_redis.exists.side_effect = lambda key: key == "orchestration:paused:global"
    assert await control.is_paused() is True

    mock_redis.exists.side_effect = lambda key: key == "orchestration:paused:user:usr1"
    assert await control.is_paused(user_id="usr1") is True


@pytest.mark.asyncio
async def test_concurrency_guard():
    mock_redis = AsyncMock()
    guard = ConcurrencyGuard(mock_redis, max_sessions=2)

    # Slot available
    mock_redis.incr.return_value = 1
    assert await guard.acquire_browser_session() is True

    # Slot busy (active sessions = 3 > limit 2)
    mock_redis.incr.return_value = 3
    assert await guard.acquire_browser_session() is False


# --- Approvals Tests ---

@pytest.mark.asyncio
async def test_approval_gate_resolve():
    mock_db = AsyncMock(spec=AsyncSession)
    gate = ApprovalGate()

    # Mock ApprovalRequest DB fetch
    mock_req = MagicMock(spec=ApprovalRequest)
    mock_req.application_id = uuid.uuid4()
    mock_req.user_id = uuid.uuid4()
    mock_req.expires_at = datetime.now(UTC) + timedelta(hours=2)
    mock_req.decision = None

    # Mock Application DB fetch
    mock_app = MagicMock(spec=Application)
    mock_app.application_id = mock_req.application_id
    mock_app.user_id = mock_req.user_id

    mock_db.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: mock_req),
        MagicMock(scalar_one=lambda: mock_app)
    ]

    resolved_app = await gate.resolve_approval(mock_db, "test_token", "approved", "Approved by reviewer")
    assert resolved_app == mock_app
    assert mock_req.decision == "approved"
    assert mock_req.decision_reason == "Approved by reviewer"


# --- Execution Coordinator Integration Mock Test ---

@pytest.mark.asyncio
async def test_coordinator_pre_evaluate_allowed():
    mock_db = AsyncMock(spec=AsyncSession)
    mock_redis = AsyncMock()

    # Return None for rate limit check and dedup checks
    mock_redis.get.return_value = None
    mock_redis.exists.return_value = False

    # Mock DB execute result for pre_evaluate query
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_res

    coordinator = ExecutionCoordinator(db=mock_db, redis=mock_redis)
    
    res = await coordinator.pre_evaluate(
        user_id=str(uuid.uuid4()),
        job_id=str(uuid.uuid4()),
        company_name="Google",
        role_title="Staff Engineer",
        url="file:///sandbox_form.html",
        method="web_form",
        manual_approval_required=False,
        priority="normal"
    )

    assert res["status"] == "allowed"
