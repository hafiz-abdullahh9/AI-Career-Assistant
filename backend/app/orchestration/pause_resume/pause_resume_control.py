class PauseResumeControl:
    """
    Manages global, domain-specific, user-specific, and task-specific pause/resume states,
    as well as system-wide emergency stops.
    All states are backed by Redis for instant propagation across workers.
    """

    def __init__(self, redis) -> None:
        self._redis = redis

    # ── Setters ─────────────────────────────────────────────────────────────────

    async def set_global_pause(self, paused: bool) -> None:
        if paused:
            await self._redis.set("orchestration:paused:global", "1")
        else:
            await self._redis.delete("orchestration:paused:global")

    async def set_user_pause(self, user_id: str, paused: bool) -> None:
        key = f"orchestration:paused:user:{user_id}"
        if paused:
            await self._redis.set(key, "1")
        else:
            await self._redis.delete(key)

    async def set_domain_pause(self, domain: str, paused: bool) -> None:
        key = f"orchestration:paused:domain:{domain.lower()}"
        if paused:
            await self._redis.set(key, "1")
        else:
            await self._redis.delete(key)

    async def set_task_pause(self, task_id: str, paused: bool) -> None:
        key = f"orchestration:paused:task:{task_id}"
        if paused:
            await self._redis.set(key, "1")
        else:
            await self._redis.delete(key)

    async def set_emergency_stop(self, active: bool) -> None:
        if active:
            await self._redis.set("orchestration:emergency_stop", "1")
        else:
            await self._redis.delete("orchestration:emergency_stop")

    # ── Checkers ────────────────────────────────────────────────────────────────

    async def is_paused(
        self,
        user_id: str | None = None,
        domain: str | None = None,
        task_id: str | None = None
    ) -> bool:
        """
        Check if execution is paused globally, for a specific user, domain, or task.
        """
        # Check global pause
        if await self._redis.exists("orchestration:paused:global"):
            return True

        # Check user pause
        if user_id and await self._redis.exists(f"orchestration:paused:user:{user_id}"):
            return True

        # Check domain pause
        if domain:
            dom = domain.lower()
            if dom.startswith("www."):
                dom = dom[4:]
            if await self._redis.exists(f"orchestration:paused:domain:{dom}"):
                return True

        # Check task pause
        if task_id and await self._redis.exists(f"orchestration:paused:task:{task_id}"):
            return True

        return False

    async def is_emergency_stop_active(self) -> bool:
        """
        Check if emergency stop is triggered.
        """
        return bool(await self._redis.exists("orchestration:emergency_stop"))
