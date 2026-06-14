# app/models/rbac.py
"""RBAC data models for Phase G.

Provides the foundational security tables:
- User
- Role
- Permission
- Association tables
- UserSession
- MfaSecret
- AuditEvent

All models inherit from the shared declarative ``Base`` defined in
``app.core.database`` so that Alembic can auto‑discover them.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional
import enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.core.database import Base

# ---------------------------------------------------------------------------
# Association tables (many‑to‑many)
# ---------------------------------------------------------------------------
from sqlalchemy import Table, Column

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

# ---------------------------------------------------------------------------
# Core models
# ---------------------------------------------------------------------------
class User(Base):
    """Core user record.

    Deterministic primary key, password hash, MFA flag, lockout handling and
    timestamps.  Roles are attached via the ``user_roles`` association table.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    username: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    roles: Mapped[list["Role"]] = relationship(
        "Role",
        secondary=user_roles,
        back_populates="users",
        lazy="selectin",
    )
    sessions: Mapped[list["UserSession"]] = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan", lazy="select"
    )
    mfa_secret: Mapped[Optional["MfaSecret"]] = relationship(
        "MfaSecret", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(
        "AuditEvent", back_populates="actor", cascade="all, delete-orphan", lazy="select"
    )

    def __repr__(self) -> str:  # pragma: no cover – debugging helper
        return f"<User id={self.id} username={self.username!r}>"


class Role(Base):
    """Fixed role definition.

    The ``name`` column is constrained to the four approved values.
    """

    __tablename__ = "roles"

    class RoleEnum(str, enum.Enum):
        admin = "admin"
        operator = "operator"
        auditor = "auditor"
        viewer = "viewer"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Relationships
    users: Mapped[list[User]] = relationship(
        "User", secondary=user_roles, back_populates="roles", lazy="selectin"
    )
    permissions: Mapped[list["Permission"]] = relationship(
        "Permission",
        secondary=role_permissions,
        back_populates="roles",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Role name={self.name}>"


class Permission(Base):
    """Atomic permission that can be assigned to a role.

    ``action`` and ``resource`` together uniquely identify a permission.
    """

    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("action", "resource", name="uq_permission_action_resource"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Relationships
    roles: Mapped[list[Role]] = relationship(
        "Role", secondary=role_permissions, back_populates="permissions", lazy="selectin"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Permission {self.action}:{self.resource}>"


class UserSession(Base):
    """Tracks a user's authenticated session.

    Used for revocation, inactivity timeout and audit trails.
    """

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    device_info: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="sessions")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UserSession token={self.session_token[:8]}... user_id={self.user_id}>"


class MfaSecret(Base):
    """Stores an encrypted TOTP secret for a user.

    ``secret_encrypted`` should be encrypted at rest (e.g., using Fernet).
    """

    __tablename__ = "mfa_secrets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(String(255), nullable=False)
    backup_codes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="mfa_secret")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MfaSecret user_id={self.user_id} enabled={self.enabled}>"


class AuditEvent(Base):
    """Immutable governance audit record.

    Every critical operation should emit one of these rows.
    """

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(45))
    reason: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    # Relationship to the actor (may be null if the actor was deleted)
    actor: Mapped[Optional[User]] = relationship("User", back_populates="audit_events")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuditEvent action={self.action} actor_id={self.actor_id}>"

# Export symbols for ``app.models`` package
__all__ = [
    "User",
    "Role",
    "Permission",
    "UserSession",
    "MfaSecret",
    "AuditEvent",
    "user_roles",
    "role_permissions",
]
