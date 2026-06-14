from datetime import date
from app.core.config import get_settings
from app.orchestration.schemas.governance_schemas import QuotaCheckResult

USER_TIERS = {
    "standard": 20,
    "pro": 50,
    "enterprise": 100
}


class QuotaManager:
    """
    Manages and enforces plan-specific execution quotas (e.g., daily caps per user tier).
    """

    def __init__(self, redis) -> None:
        self._redis = redis
        self._settings = get_settings()

    async def check_user_quota(
        self,
        user_id: str,
        user_tier: str = "standard"
    ) -> QuotaCheckResult:
        """
        Verify if the user has exceeded their daily application quota.
        """
        tier = (user_tier or "standard").lower()
        limit = USER_TIERS.get(tier, self._settings.daily_application_limit_default)

        today = date.today().strftime("%Y%m%d")
        key = f"rate:daily:{user_id}:{today}"

        current_bytes = await self._redis.get(key)
        current = int(current_bytes) if current_bytes else 0

        if current >= limit:
            return QuotaCheckResult(
                allowed=False,
                current_count=current,
                limit=limit,
                reason=f"Daily quota of {limit} applications reached for plan tier '{tier}'."
            )

        return QuotaCheckResult(
            allowed=True,
            current_count=current,
            limit=limit
        )

    async def record_user_application(self, user_id: str) -> None:
        """
        Record user application to count against daily limit.
        """
        today = date.today().strftime("%Y%m%d")
        key = f"rate:daily:{user_id}:{today}"

        pipe = self._redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 48 * 3600)  # 48h TTL
        await pipe.execute()
