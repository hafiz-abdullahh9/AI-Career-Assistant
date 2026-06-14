# app/services/auth_service.py
"""AuthService service.

Handles user registration, authentication, brute-force protection (lockouts),
and automatic logging of audit events.
"""

import uuid
from datetime import datetime, timedelta, UTC
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.models.rbac import AuditEvent, Role, User

logger = get_logger(__name__)


class AuthService:
    """Manages core authentication, user registration, and brute-force lockout policy."""

    def __init__(self, lockout_attempts: int = 5, lockout_window_minutes: int = 15):
        self.lockout_attempts = lockout_attempts
        self.lockout_window_minutes = lockout_window_minutes

    async def log_audit_event(
        self,
        db: AsyncSession,
        actor_id: Optional[uuid.UUID],
        action: str,
        resource_type: str,
        resource_id: Optional[uuid.UUID] = None,
        ip_address: Optional[str] = None,
        reason: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> AuditEvent:
        """Create and persist an immutable AuditEvent record."""
        event = AuditEvent(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            reason=reason,
            metadata_json=metadata or {},
            timestamp=datetime.now(UTC),
        )
        db.add(event)
        await db.flush()
        return event

    async def register_user(
        self,
        db: AsyncSession,
        username: str,
        email: str,
        password: str,
        ip_address: Optional[str] = None,
    ) -> User:
        """Register a new user, hashes password, and assigns the default 'operator' role."""
        # 1. Check if user already exists
        stmt = select(User).where(or_(User.username == username, User.email == email))
        res = await db.execute(stmt)
        existing_user = res.scalar_one_or_none()

        if existing_user:
            if existing_user.username == username:
                raise ConflictError("Username is already taken")
            else:
                raise ConflictError("Email is already registered")

        # 2. Hash password
        pw_hash = hash_password(password)

        # 3. Create user
        user = User(
            username=username,
            email=email,
            password_hash=pw_hash,
            is_active=True,
            mfa_enabled=False,
            failed_login_attempts=0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        db.add(user)
        await db.flush()

        # 4. Assign default 'operator' role
        role_stmt = select(Role).where(Role.name == Role.RoleEnum.operator)
        role_res = await db.execute(role_stmt)
        default_role = role_res.scalar_one_or_none()

        if default_role:
            from sqlalchemy import insert
            from app.models.rbac import user_roles
            await db.execute(insert(user_roles).values(user_id=user.id, role_id=default_role.id))
            await db.flush()
        else:
            logger.warning("auth.default_role_not_found", role="operator")

        await db.refresh(user, ["roles"])

        # 5. Log audit event
        await self.log_audit_event(
            db,
            actor_id=user.id,
            action="user_registered",
            resource_type="user",
            resource_id=user.id,
            ip_address=ip_address,
            reason="User registered successfully",
            metadata={"username": username, "email": email},
        )

        logger.info("user.registered", username=username, user_id=str(user.id))
        return user

    async def authenticate_user(
        self,
        db: AsyncSession,
        username_or_email: str,
        password: str,
        ip_address: Optional[str] = None,
    ) -> User:
        """Authenticate user credentials and handle brute-force protection."""
        now = datetime.now(UTC)

        # 1. Fetch user by username or email
        stmt = select(User).where(or_(User.username == username_or_email, User.email == username_or_email))
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()

        if not user:
            logger.warning("auth.user_not_found", identifier=username_or_email)
            raise UnauthorizedError("Invalid username or password")

        # 2. Check lockout status
        if user.locked_until and user.locked_until > now:
            minutes_left = int((user.locked_until - now).total_seconds() / 60) + 1
            await self.log_audit_event(
                db,
                actor_id=user.id,
                action="login_failed_locked",
                resource_type="user",
                resource_id=user.id,
                ip_address=ip_address,
                reason="Account locked due to brute force protection",
            )
            raise UnauthorizedError(
                f"Account is temporarily locked. Try again in {minutes_left} minutes."
            )

        # 3. Verify password
        if not verify_password(password, user.password_hash):
            # Increment failed attempts
            user.failed_login_attempts += 1
            
            if user.failed_login_attempts >= self.lockout_attempts:
                # Trigger lockout
                user.locked_until = now + timedelta(minutes=self.lockout_window_minutes)
                await self.log_audit_event(
                    db,
                    actor_id=user.id,
                    action="user_locked_out",
                    resource_type="user",
                    resource_id=user.id,
                    ip_address=ip_address,
                    reason=f"Account locked after {self.lockout_attempts} failed attempts",
                )
                logger.warning("auth.user_locked", user_id=str(user.id), attempts=user.failed_login_attempts)
                raise UnauthorizedError("Invalid username or password")
            else:
                await self.log_audit_event(
                    db,
                    actor_id=user.id,
                    action="login_failed",
                    resource_type="user",
                    resource_id=user.id,
                    ip_address=ip_address,
                    reason="Invalid password attempt",
                    metadata={"failed_attempts": user.failed_login_attempts},
                )
                await db.flush()
                raise UnauthorizedError("Invalid username or password")

        # 4. Successful login
        # Reset failed attempts and lockout timer
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        await db.flush()

        await self.log_audit_event(
            db,
            actor_id=user.id,
            action="login_success",
            resource_type="user",
            resource_id=user.id,
            ip_address=ip_address,
            reason="User logged in successfully",
        )

        logger.info("auth.login_success", user_id=str(user.id))
        return user
