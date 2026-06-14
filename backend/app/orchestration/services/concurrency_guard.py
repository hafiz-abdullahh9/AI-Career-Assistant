class ConcurrencyGuard:
    """
    Enforces concurrency constraints using Redis:
    - Global active browser session limit (semaphore).
    - Per-user and per-job distributed locks to prevent race conditions.
    """

    def __init__(self, redis, max_sessions: int = 10) -> None:
        self._redis = redis
        self.max_sessions = max_sessions

    async def acquire_browser_session(self) -> bool:
        """
        Attempt to acquire a browser session slot by incrementing the active counter.
        Returns True if acquired, False otherwise.
        """
        active = await self._redis.incr("selenium:sessions:active")
        # Ensure key TTL just in case of crash (e.g. 5 minutes session max)
        await self._redis.expire("selenium:sessions:active", 300)

        if active > self.max_sessions:
            await self._redis.decr("selenium:sessions:active")
            return False

        return True

    async def release_browser_session(self) -> None:
        """
        Release a browser session slot.
        """
        active = await self._redis.get("selenium:sessions:active")
        if active and int(active) > 0:
            await self._redis.decr("selenium:sessions:active")

    async def acquire_job_lock(self, user_id: str, job_id: str) -> bool:
        """
        Attempt to acquire a distributed lock for a user applying to a specific job.
        Prevents duplicate parallel worker tasks.
        """
        lock_key = f"lock:user_job:{user_id}:{job_id}"
        success = await self._redis.set(lock_key, "1", ex=600, nx=True)
        return bool(success)

    async def release_job_lock(self, user_id: str, job_id: str) -> None:
        """
        Release the user-job lock.
        """
        lock_key = f"lock:user_job:{user_id}:{job_id}"
        await self._redis.delete(lock_key)
