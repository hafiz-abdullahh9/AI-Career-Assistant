import time
from datetime import date
from app.orchestration.schemas.governance_schemas import RateLimitCheckResult

PLATFORM_LIMITS = {
    "linkedin": {"per_day": 10, "min_interval_seconds": 120},
    "indeed": {"per_day": 15, "min_interval_seconds": 60},
    "greenhouse": {"per_day": 20, "min_interval_seconds": 30},
    "lever": {"per_day": 20, "min_interval_seconds": 30},
    "default": {"per_day": 20, "min_interval_seconds": 30},
}


class RateLimiter:
    """
    Enforces user daily caps, platform-specific daily limits, and platform-specific minimum interval delays.
    Uses Redis keys.
    """

    def __init__(self, redis) -> None:
        self._redis = redis

    async def check_platform_limit(
        self,
        user_id: str,
        platform: str
    ) -> RateLimitCheckResult:
        """
        Check if the platform daily limit or minimum interval constraints are violated.
        """
        plat = (platform or "default").lower()
        limits = PLATFORM_LIMITS.get(plat, PLATFORM_LIMITS["default"])

        today = date.today().strftime("%Y%m%d")
        daily_key = f"rate:platform:daily:{user_id}:{plat}:{today}"
        last_applied_key = f"rate:platform:last_applied:{user_id}:{plat}"

        # 1. Check last applied timestamp for min interval
        last_ts_bytes = await self._redis.get(last_applied_key)
        if last_ts_bytes:
            last_ts = float(last_ts_bytes)
            elapsed = time.time() - last_ts
            min_sec = limits["min_interval_seconds"]
            if elapsed < min_sec:
                retry_after = min_sec - elapsed
                return RateLimitCheckResult(
                    allowed=False,
                    retry_after_sec=retry_after,
                    reason=f"Platform '{plat}' requires minimum interval of {min_sec}s. Try again in {retry_after:.1f}s."
                )

        # 2. Check daily limits
        current_count_bytes = await self._redis.get(daily_key)
        if current_count_bytes:
            current_count = int(current_count_bytes)
            limit = limits["per_day"]
            if current_count >= limit:
                return RateLimitCheckResult(
                    allowed=False,
                    reason=f"Platform '{plat}' daily application limit of {limit} reached."
                )

        return RateLimitCheckResult(allowed=True)

    async def record_application(self, user_id: str, platform: str) -> None:
        """
        Record a successful application event in Redis to update rate limit state.
        """
        plat = (platform or "default").lower()
        today = date.today().strftime("%Y%m%d")
        daily_key = f"rate:platform:daily:{user_id}:{plat}:{today}"
        last_applied_key = f"rate:platform:last_applied:{user_id}:{plat}"

        # Increment platform daily count with 48h TTL
        pipe = self._redis.pipeline()
        pipe.incr(daily_key)
        pipe.expire(daily_key, 48 * 3600)
        # Update last applied timestamp
        pipe.set(last_applied_key, str(time.time()), ex=24 * 3600)
        await pipe.execute()
