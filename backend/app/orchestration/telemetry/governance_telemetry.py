import structlog
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.orm import ApplicationLog
from app.orchestration.schemas.governance_schemas import GovernanceEvent, GovernanceEventType

logger = structlog.get_logger(__name__)


class GovernanceTelemetry:
    """
    Observer/Telemetry system tracking governance decisions:
    approvals, policy denials, quota hits, rate-limit events, and dedup rejects.
    """

    @classmethod
    async def record_event(
        cls,
        db: AsyncSession,
        application_id: str,
        user_id: str,
        event_type: GovernanceEventType,
        policy_name: str,
        reason: str,
        metadata: dict | None = None
    ) -> None:
        """
        Record a governance event in structured logs and database application logs.
        """
        meta = metadata or {}
        event = GovernanceEvent(
            application_id=application_id,
            user_id=user_id,
            event_type=event_type,
            policy_name=policy_name,
            decision_reason=reason,
            metadata=meta
        )

        # Log via structured logger (structlog)
        logger.info(
            f"governance.{event_type}",
            event_id=str(event.event_id),
            application_id=application_id,
            user_id=user_id,
            policy_name=policy_name,
            reason=reason,
            **meta
        )

        # Log into the database applications logs for auditing
        import structlog
        trace_id = structlog.contextvars.get_contextvars().get("trace_id")
        
        db_log = ApplicationLog(
            application_id=event.application_id,
            level="WARN" if event_type in (
                GovernanceEventType.POLICY_DENIAL,
                GovernanceEventType.QUOTA_HIT,
                GovernanceEventType.RATE_LIMIT_HIT,
                GovernanceEventType.DEDUP_REJECT,
                GovernanceEventType.ALLOWLIST_REJECT
            ) else "INFO",
            event=f"governance.{event_type}",
            message=f"[{policy_name}] {reason}",
            context={
                "event_id": str(event.event_id),
                "policy_name": policy_name,
                "reason": reason,
                **meta
            },
            trace_id=trace_id
        )
        db.add(db_log)
        await db.flush()
