import uuid
from datetime import datetime, UTC
from enum import StrEnum
from pydantic import BaseModel, Field


class GovernanceEventType(StrEnum):
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_APPROVED = "approval_approved"
    APPROVAL_REJECTED = "approval_rejected"
    POLICY_DENIAL = "policy_denial"
    QUOTA_HIT = "quota_hit"
    RATE_LIMIT_HIT = "rate_limit_hit"
    DEDUP_REJECT = "dedup_reject"
    ALLOWLIST_REJECT = "allowlist_reject"


class GovernanceEvent(BaseModel):
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    application_id: uuid.UUID
    user_id: uuid.UUID
    event_type: GovernanceEventType
    policy_name: str
    decision_reason: str
    metadata: dict = Field(default_factory=dict)


class QuotaCheckResult(BaseModel):
    allowed: bool
    current_count: int
    limit: int
    reason: str | None = None


class RateLimitCheckResult(BaseModel):
    allowed: bool
    retry_after_sec: float = 0.0
    reason: str | None = None


class DeduplicationResult(BaseModel):
    is_duplicate: bool
    reason: str | None = None
    existing_application_id: str | None = None


class ApprovalGateResult(BaseModel):
    approval_required: bool
    reason: str | None = None
    token: str | None = None
