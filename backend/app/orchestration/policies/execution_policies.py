import random
import math
from app.orchestration.allowlists.domain_allowlist import DomainAllowlist
from app.orchestration.rate_limits.rate_limiter import RateLimiter
from app.orchestration.quotas.quota_manager import QuotaManager
from app.orchestration.deduplication.deduplicator import Deduplicator
from app.orchestration.schemas.governance_schemas import ApprovalGateResult


class DomainAllowlistPolicy:
    """Policy to enforce allowed domains."""

    @classmethod
    def check_url(cls, url: str | None) -> bool:
        if not url:
            # Email method doesn't have application URL, which is fine
            return True
        return DomainAllowlist.is_url_allowed(url)


class ApprovalGatePolicy:
    """Policy to evaluate whether manual approval is required."""

    @classmethod
    def requires_approval(
        cls,
        manual_approval_required: bool,
        priority: str = "normal",
        platform: str | None = None
    ) -> bool:
        """
        Determine if manual approval is required based on request flags
        or safety rules.
        """
        # If user explicitly requested manual approval
        if manual_approval_required:
            return True

        # Custom safety rules: high priority or specific platforms trigger manual approval
        if priority == "high":
            return True

        plat = (platform or "").lower()
        if plat in ("linkedin", "indeed"):
            # Flag LinkedIn/Indeed for manual approval as they are high risk
            return True

        return False


class RetryPolicy:
    """
    Calculates exponential backoff delays with jitter.
    """

    @classmethod
    def calculate_backoff(
        cls,
        attempt: int,
        base_delay: float = 60.0,
        max_delay: float = 900.0,
        jitter: bool = True
    ) -> float:
        """
        Calculates exponential backoff: delay = base_delay * 2^(attempt - 1).
        If jitter is True, applies random multiplier between 0.8 and 1.2.
        Caps output at max_delay.
        """
        if attempt < 1:
            attempt = 1
        
        delay = base_delay * math.pow(2, attempt - 1)
        if jitter:
            delay = delay * random.uniform(0.8, 1.2)
        
        return min(delay, max_delay)
