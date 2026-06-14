"""
SQLAlchemy 2.0 ORM models.

Design rules:
  - All PKs are UUID (server-generated with gen_random_uuid()).
  - Every table has created_at / updated_at (updated_at via DB trigger).
  - Soft-delete via deleted_at (never hard-delete application records).
  - Status is stored as a String mapped to ApplicationStatus enum.
  - JSONB columns use MutableDict for change tracking.
"""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Application(Base):
    """
    Central tracking record for every job application attempt.

    One record per (user_id, job_id) pair — enforced by unique constraint.
    The status field drives the entire tracking lifecycle.
    """
    __tablename__ = "applications"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # Snapshot of job context at submission time
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_title: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str | None] = mapped_column(String(100))
    application_url: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(String(255))

    # Method and status
    method: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued", index=True)

    # Asset version IDs (references to files in object storage)
    resume_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cover_letter_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    # Timing
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Confirmation
    confirmation_id: Mapped[str | None] = mapped_column(String(255))

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Celery task reference
    celery_task_id: Mapped[str | None] = mapped_column(String(255))

    # Soft delete
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Flexible per-platform metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    status_history: Mapped[list["ApplicationStatusHistory"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", lazy="select"
    )
    logs: Mapped[list["ApplicationLog"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", lazy="select"
    )
    emails: Mapped[list["EmailSend"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", lazy="select"
    )
    approval_requests: Mapped[list["ApprovalRequest"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", lazy="select"
    )

    @property
    def manual_approval_required(self) -> bool:
        return self.metadata_.get("manual_approval_required", False)

    @manual_approval_required.setter
    def manual_approval_required(self, value: bool) -> None:
        self.metadata_["manual_approval_required"] = value

    def __repr__(self) -> str:
        return (
            f"<Application id={self.application_id} "
            f"company={self.company_name!r} status={self.status!r}>"
        )


class ApplicationStatusHistory(Base):
    """
    Immutable log of every status transition for an application.

    Never updated after creation — append-only audit trail.
    """
    __tablename__ = "application_status_history"

    history_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.application_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    from_status: Mapped[str | None] = mapped_column(String(50))
    to_status: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[str] = mapped_column(String(100), default="system", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationship back to parent
    application: Mapped["Application"] = relationship(back_populates="status_history")

    def __repr__(self) -> str:
        return (
            f"<StatusHistory {self.from_status} → {self.to_status} "
            f"app={self.application_id}>"
        )


class ApplicationLog(Base):
    """
    Structured event log scoped to a single application.

    Used for per-application debug trails, visible in the dashboard.
    Separate from the global structlog output (which is process-wide).
    """
    __tablename__ = "application_logs"

    log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.application_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    level: Mapped[str] = mapped_column(String(10), nullable=False)   # INFO | WARN | ERROR
    event: Mapped[str] = mapped_column(String(100), nullable=False)   # e.g. "email.sent"
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Structured context as JSONB for queryability
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    # Distributed trace ID (from request or task)
    trace_id: Mapped[str | None] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationship back to parent
    application: Mapped["Application"] = relationship(back_populates="logs")

    def __repr__(self) -> str:
        return f"<ApplicationLog [{self.level}] {self.event} app={self.application_id}>"


class EmailSend(Base):
    """
    Tracking record for every email delivery attempt.
    """
    __tablename__ = "email_sends"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.application_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    smtp_response: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship back to parent
    application: Mapped["Application"] = relationship(back_populates="emails")

    def __repr__(self) -> str:
        return f"<EmailSend id={self.id} status={self.status} app={self.application_id}>"


class ApprovalRequest(Base):
    """
    Tracks manual approval requests for applications.
    """
    __tablename__ = "approval_requests"

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.application_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision: Mapped[str | None] = mapped_column(String(20))  # 'approved' | 'rejected'
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[str | None] = mapped_column(String(100))  # 'user' | 'system'
    approval_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    application: Mapped["Application"] = relationship(back_populates="approval_requests")

    def __repr__(self) -> str:
        return f"<ApprovalRequest id={self.request_id} status={self.decision} app={self.application_id}>"

