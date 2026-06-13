import secrets
import uuid
from datetime import datetime, timedelta, UTC
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.orm import Application, ApprovalRequest
from app.models.schemas import ApplicationStatus
from app.orchestration.schemas.governance_schemas import ApprovalGateResult


class ApprovalGate:
    """
    Manages the manual approval gate workflow:
    - Initiating approval requests with tokens and expiration.
    - Resolving approval requests (approve/reject).
    """

    def __init__(self, expiry_hours: int = 24) -> None:
        self.expiry_hours = expiry_hours

    async def request_approval(
        self,
        db: AsyncSession,
        application: Application,
        reason: str = "Manual review required"
    ) -> ApprovalGateResult:
        """
        Creates a manual approval request for the application,
        sets it to PENDING_APPROVAL status, and generates a token.
        """
        token = secrets.token_hex(32)
        now = datetime.now(UTC)
        expires = now + timedelta(hours=self.expiry_hours)

        approval_request = ApprovalRequest(
            application_id=application.application_id,
            user_id=application.user_id,
            expires_at=expires,
            decision=None,
            approval_token=token
        )

        db.add(approval_request)
        await db.flush()

        return ApprovalGateResult(
            approval_required=True,
            reason=reason,
            token=token
        )

    async def resolve_approval(
        self,
        db: AsyncSession,
        token: str,
        decision: str,  # 'approved' | 'rejected'
        reason: str | None = None,
        decided_by: str = "user"
    ) -> Application:
        """
        Resolve an approval request.
        If approved: updates request, application transitions to QUEUED state.
        If rejected: updates request, application transitions to FAILED state.
        """
        stmt = select(ApprovalRequest).where(
            ApprovalRequest.approval_token == token
        )
        res = await db.execute(stmt)
        req = res.scalar_one_or_none()

        if not req:
            raise ValueError("Approval request with this token does not exist.")

        if req.decision is not None:
            raise ValueError(f"Approval request has already been resolved as '{req.decision}'.")

        if req.expires_at < datetime.now(UTC):
            req.decision = "rejected"
            req.decided_by = "auto_expired"
            req.resolved_at = datetime.now(UTC)
            await db.flush()
            raise ValueError("Approval request has expired.")

        req.decision = decision
        req.decided_by = decided_by
        req.decision_reason = reason
        req.resolved_at = datetime.now(UTC)

        # Retrieve application
        app_stmt = select(Application).where(
            Application.application_id == req.application_id
        )
        app_res = await db.execute(app_stmt)
        application = app_res.scalar_one()

        await db.flush()
        return application
class ApprovalRequiredError(Exception):
    def __init__(self, message: str, token: str) -> None:
        super().__init__(message)
        self.token = token
