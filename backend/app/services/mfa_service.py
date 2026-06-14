# app/services/mfa_service.py
"""MfaService service.

Manages MFA initialization, code verification (totp and backup recovery codes),
encryption at rest for secrets, backup code hashing, and replay protection.
"""

import hashlib
import json
import secrets
import uuid
from datetime import datetime, UTC
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import (
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    generate_totp_secret,
    get_totp_provisioning_uri,
    verify_totp_token,
)
from app.models.rbac import MfaSecret, User

logger = get_logger(__name__)


class MfaService:
    """Manages multi-factor authentication enrollment, verification, and recovery."""

    def __init__(self, redis_client: Any = None):
        self.redis = redis_client
        self.backup_code_count = 8
        self.backup_code_length = 10

    def generate_backup_codes(self) -> list[str]:
        """Generate cryptographically secure backup recovery codes."""
        # Generate 8 codes of 10 characters (e.g. hex digits)
        return [secrets.token_hex(self.backup_code_length // 2) for _ in range(self.backup_code_count)]

    def hash_backup_code(self, code: str) -> str:
        """Hash a backup code using SHA-256 for secure storage."""
        return hashlib.sha256(code.strip().lower().encode("utf-8")).hexdigest()

    def generate_mfa_setup(self, username: str) -> tuple[str, list[str], str]:
        """Initialize TOTP configuration for a user.

        Returns (secret_plaintext, backup_codes, provisioning_uri).
        """
        secret = generate_totp_secret()
        backup_codes = self.generate_backup_codes()
        provisioning_uri = get_totp_provisioning_uri(secret, username)
        return secret, backup_codes, provisioning_uri

    async def enable_mfa(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        secret_plaintext: str,
        code: str,
        backup_codes: list[str],
    ) -> bool:
        """Verify the initial TOTP token and enable MFA for the user."""
        # Verify the provided code against the plaintext secret
        if not verify_totp_token(secret_plaintext, code):
            logger.warning("mfa.enable_failed_invalid_code", user_id=str(user_id))
            return False

        # Encrypt the secret for storage at rest
        encrypted_secret = encrypt_mfa_secret(secret_plaintext)

        # Hash backup codes for secure storage
        hashed_backup_codes = [self.hash_backup_code(bc) for bc in backup_codes]

        now = datetime.now(UTC)

        # Upsert MfaSecret
        stmt = select(MfaSecret).where(MfaSecret.user_id == user_id)
        res = await db.execute(stmt)
        mfa_secret = res.scalar_one_or_none()

        if mfa_secret:
            mfa_secret.secret_encrypted = encrypted_secret
            mfa_secret.backup_codes = {"codes": hashed_backup_codes}
            mfa_secret.enabled = True
            mfa_secret.verified_at = now
        else:
            mfa_secret = MfaSecret(
                user_id=user_id,
                secret_encrypted=encrypted_secret,
                backup_codes={"codes": hashed_backup_codes},
                enabled=True,
                verified_at=now,
            )
            db.add(mfa_secret)

        # Update user status
        user_stmt = select(User).where(User.id == user_id)
        user_res = await db.execute(user_stmt)
        user = user_res.scalar_one()
        user.mfa_enabled = True

        await db.flush()
        logger.info("mfa.enabled", user_id=str(user_id))
        return True

    async def disable_mfa(self, db: AsyncSession, user_id: uuid.UUID) -> bool:
        """Disable MFA for a user."""
        # Retrieve MFA secret
        stmt = select(MfaSecret).where(MfaSecret.user_id == user_id)
        res = await db.execute(stmt)
        mfa_secret = res.scalar_one_or_none()

        if not mfa_secret or not mfa_secret.enabled:
            return False

        # Soft disable: set enabled to False and clear secret data
        mfa_secret.enabled = False
        mfa_secret.secret_encrypted = "DISABLED"
        mfa_secret.backup_codes = {"codes": []}

        # Update User model
        user_stmt = select(User).where(User.id == user_id)
        user_res = await db.execute(user_stmt)
        user = user_res.scalar_one()
        user.mfa_enabled = False

        await db.flush()
        logger.info("mfa.disabled", user_id=str(user_id))
        return True

    async def verify_mfa_code(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        code: str,
    ) -> bool:
        """Verify an MFA code (either a standard TOTP token or a backup recovery code).

        Includes replay protection for TOTP tokens.
        """
        stmt = select(MfaSecret).where(MfaSecret.user_id == user_id)
        res = await db.execute(stmt)
        mfa_secret = res.scalar_one_or_none()

        if not mfa_secret or not mfa_secret.enabled:
            logger.warning("mfa.verification_failed_not_enabled", user_id=str(user_id))
            return False

        code_clean = code.strip().lower()

        # 1. Check if it is a backup recovery code
        hashed_code = self.hash_backup_code(code_clean)
        stored_backup_codes = mfa_secret.backup_codes.get("codes", [])

        if hashed_code in stored_backup_codes:
            # Backup code matches! Consume it (single-use constraint)
            stored_backup_codes.remove(hashed_code)
            mfa_secret.backup_codes = {"codes": stored_backup_codes}
            await db.flush()
            logger.info("mfa.backup_code_used", user_id=str(user_id))
            return True

        # 2. Check if it is a standard 6-digit TOTP token
        if len(code_clean) == 6 and code_clean.isdigit():
            # Replay protection check via Redis
            if self.redis:
                replay_key = f"mfa:replay:{user_id}:{code_clean}"
                try:
                    exists = await self.redis.exists(replay_key)
                    if exists:
                        logger.warning("mfa.replay_detected", user_id=str(user_id), code=code_clean)
                        return False
                except Exception as exc:
                    logger.error("mfa.redis_replay_check_failed", error=str(exc))

            # Decrypt secret
            secret_plaintext = decrypt_mfa_secret(mfa_secret.secret_encrypted)

            # Verify token
            if verify_totp_token(secret_plaintext, code_clean):
                # Set replay prevention key in Redis with 90s expiry (covering drift window)
                if self.redis:
                    try:
                        await self.redis.set(replay_key, "1", ex=90)
                    except Exception as exc:
                        logger.error("mfa.redis_replay_set_failed", error=str(exc))
                return True

        logger.warning("mfa.verification_failed_invalid_token", user_id=str(user_id))
        return False
