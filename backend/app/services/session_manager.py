# app/services/session_manager.py
"""SessionManager service.

Manages authenticated user sessions, including DB persistence, SHA-256 token hashing,
sliding window inactivity expiration, absolute expiration, and Redis-based caching.
"""

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, UTC
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.rbac import User, UserSession

logger = get_logger(__name__)


class SessionManager:
    """Manages creation, validation, caching, and revocation of user sessions."""

    def __init__(self, redis_client: Any = None):
        self.redis = redis_client
        self.settings = get_settings()
        # Inactivity timeout (e.g. 2 hours)
        self.inactivity_timeout_minutes = 120
        # Absolute timeout (e.g. 30 days)
        self.absolute_timeout_days = 30

    def hash_token(self, token: str) -> str:
        """Compute the SHA-256 hash of a session token for storage and lookup."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def generate_token(self) -> str:
        """Generate a cryptographically secure, high-entropy session token."""
        # Generates a 64-character hex string (32 bytes of entropy)
        return secrets.token_hex(32)

    async def create_session(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        device_info: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> tuple[UserSession, str]:
        """Create a new session, persist it to the DB, and cache it in Redis.

        Returns a tuple of (UserSession, raw_token).
        """
        raw_token = self.generate_token()
        token_hash = self.hash_token(raw_token)

        now = datetime.now(UTC)
        # Session is initially valid for inactivity_timeout_minutes
        expires_at = now + timedelta(minutes=self.inactivity_timeout_minutes)

        session = UserSession(
            user_id=user_id,
            session_token=token_hash,
            device_info=device_info,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
            last_activity_at=now,
            created_at=now,
        )

        db.add(session)
        await db.flush()

        # Cache in Redis
        if self.redis:
            try:
                cache_key = f"session:{token_hash}"
                cache_data = {
                    "session_id": str(session.id),
                    "user_id": str(user_id),
                    "expires_at": expires_at.isoformat(),
                    "last_activity_at": now.isoformat(),
                    "created_at": now.isoformat(),
                }
                # Set TTL slightly longer than inactivity timeout
                ttl = self.inactivity_timeout_minutes * 60
                await self.redis.set(cache_key, json.dumps(cache_data), ex=ttl)
            except Exception as exc:
                logger.error("session_manager.redis_cache_failed", error=str(exc))

        logger.info("session.created", user_id=str(user_id), session_id=str(session.id))
        return session, raw_token

    async def validate_session(self, db: AsyncSession, raw_token: str) -> Optional[User]:
        """Validate a session token.

        Checks expiry, sliding-window inactivity, and revocation status.
        Updates last_activity_at and caches updates if valid.
        Returns the User if valid, otherwise None.
        """
        token_hash = self.hash_token(raw_token)
        now = datetime.now(UTC)

        # 1. Try Redis cache first
        cached_session = None
        if self.redis:
            try:
                cache_key = f"session:{token_hash}"
                data = await self.redis.get(cache_key)
                if data:
                    cached_session = json.loads(data)
            except Exception as exc:
                logger.error("session_manager.redis_get_failed", error=str(exc))

        user_id = None
        session_id = None

        if cached_session:
            user_id = uuid.UUID(cached_session["user_id"])
            session_id = uuid.UUID(cached_session["session_id"])
            expires_at = datetime.fromisoformat(cached_session["expires_at"])
            
            # Check absolute expiration (30 days since creation)
            created_at = datetime.fromisoformat(cached_session["created_at"])
            if now > created_at + timedelta(days=self.absolute_timeout_days):
                logger.warning("session.absolute_expired", session_id=str(session_id))
                await self.revoke_session(db, raw_token)
                return None

            # Check inactivity expiration
            if now > expires_at:
                logger.warning("session.inactivity_expired", session_id=str(session_id))
                await self.revoke_session(db, raw_token)
                return None
        else:
            # 2. Cache miss: Query DB
            stmt = (
                select(UserSession)
                .options(selectinload(UserSession.user).selectinload(User.roles))
                .where(UserSession.session_token == token_hash)
            )
            res = await db.execute(stmt)
            session = res.scalar_one_or_none()

            if not session or session.revoked_at:
                return None

            session_id = session.id
            user_id = session.user_id

            # Check absolute expiration
            if now > session.created_at + timedelta(days=self.absolute_timeout_days):
                logger.warning("session.absolute_expired", session_id=str(session_id))
                session.revoked_at = now
                await db.commit()
                return None

            # Check inactivity expiration
            if now > session.expires_at:
                logger.warning("session.inactivity_expired", session_id=str(session_id))
                session.revoked_at = now
                await db.commit()
                return None

        # 3. Slide the inactivity window (update last activity)
        new_expiry = now + timedelta(minutes=self.inactivity_timeout_minutes)

        # Update DB
        update_stmt = (
            update(UserSession)
            .where(UserSession.id == session_id)
            .values(last_activity_at=now, expires_at=new_expiry)
        )
        await db.execute(update_stmt)
        # Flush so changes are visible in current transaction without fully committing yet
        await db.flush()

        # Update Redis cache
        if self.redis:
            try:
                cache_key = f"session:{token_hash}"
                cache_data = {
                    "session_id": str(session_id),
                    "user_id": str(user_id),
                    "expires_at": new_expiry.isoformat(),
                    "last_activity_at": now.isoformat(),
                    "created_at": now.isoformat() if not cached_session else cached_session["created_at"],
                }
                ttl = self.inactivity_timeout_minutes * 60
                await self.redis.set(cache_key, json.dumps(cache_data), ex=ttl)
            except Exception as exc:
                logger.error("session_manager.redis_update_failed", error=str(exc))

        # Retrieve full user with roles preloaded
        user_stmt = select(User).options(selectinload(User.roles)).where(User.id == user_id)
        user_res = await db.execute(user_stmt)
        return user_res.scalar_one_or_none()

    async def revoke_session(self, db: AsyncSession, raw_token: str) -> bool:
        """Revoke a session by token.

        Updates DB revoked_at and clears the Redis cache.
        """
        token_hash = self.hash_token(raw_token)
        now = datetime.now(UTC)

        # Update DB
        stmt = (
            update(UserSession)
            .where(UserSession.session_token == token_hash, UserSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        res = await db.execute(stmt)
        await db.flush()

        # Delete from Redis
        if self.redis:
            try:
                cache_key = f"session:{token_hash}"
                await self.redis.delete(cache_key)
            except Exception as exc:
                logger.error("session_manager.redis_delete_failed", error=str(exc))

        success = res.rowcount > 0
        if success:
            logger.info("session.revoked", token_hash=token_hash)
        return success

    async def revoke_all_user_sessions(self, db: AsyncSession, user_id: uuid.UUID) -> int:
        """Revoke all active sessions for a given user.

        Used during password resets, MFA changes, or suspicious login activity.
        """
        now = datetime.now(UTC)

        # Get all session tokens for this user that are not revoked
        stmt = select(UserSession.session_token).where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None)
        )
        res = await db.execute(stmt)
        tokens_to_revoke = res.scalars().all()

        if not tokens_to_revoke:
            return 0

        # Update DB
        update_stmt = (
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await db.execute(update_stmt)
        await db.flush()

        # Clear from Redis
        if self.redis:
            try:
                keys = [f"session:{t}" for t in tokens_to_revoke]
                await self.redis.delete(*keys)
            except Exception as exc:
                logger.error("session_manager.redis_bulk_delete_failed", error=str(exc))

        logger.info("session.bulk_revoked", user_id=str(user_id), count=len(tokens_to_revoke))
        return len(tokens_to_revoke)
