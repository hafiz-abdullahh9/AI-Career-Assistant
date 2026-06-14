# app/api/v1/approvals.py
"""Approvals API router — handles standalone /approvals/* endpoints expected by validation."""

import uuid
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.core.auth import get_current_user, RequiresPermission
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.exceptions import NotFoundError
from app.hitl.services.hitl_service import HitlService
from app.models.orm import Application, ApprovalRequest
from app.models.schemas import ApplicationStatus, SuccessResponse, TaskPayload
from app.services.application_service import ApplicationService
from app.tasks.application_tasks import process_application
from app.orchestration.approvals.approval_gate import ApprovalGate


router = APIRouter(prefix="/approvals", tags=["Approvals"])


def _make_meta(request: Request) -> dict:
    """Build standard response meta from request context."""
    return {
        "request_id": getattr(request.state, "trace_id", str(uuid.uuid4())),
        "timestamp": datetime.now(UTC),
    }


class ApprovalResolutionRequest(BaseModel):
    decision: str = Field(..., description="'approved' or 'rejected'")
    reason: str | None = Field(None, max_length=500)
    changed_by: str = "user"


@router.get("/pending", response_model=SuccessResponse)
async def get_pending_approvals(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
) -> SuccessResponse:
    """Returns pending approvals as a flat list under 'items' for client compatibility."""
    service = HitlService(db)
    queues = await service.get_queues()
    awaiting_approval = queues.get("awaiting_approval", [])

    items = []
    for q_item in awaiting_approval:
        items.append({
            "id": q_item.get("approval_token"),  # map token to 'id' as expected by tests
            "application_id": q_item.get("application_id"),
            "company_name": q_item.get("company_name"),
            "role_title": q_item.get("role_title"),
            "priority": q_item.get("priority"),
            "status": q_item.get("status"),
            "reason": q_item.get("reason"),
            "approval_token": q_item.get("approval_token")
        })

    return SuccessResponse(data={"items": items}, meta=_make_meta(request))


@router.post("/{application_id}/approve", response_model=SuccessResponse, dependencies=[Depends(RequiresPermission("approve_execution", "global"))])
async def approve_application_endpoint(
    application_id: uuid.UUID,
    body: ApprovalResolutionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis)
) -> SuccessResponse:
    """Resolves a pending manual approval gate by application ID."""
    stmt = select(ApprovalRequest).where(
        ApprovalRequest.application_id == application_id,
        ApprovalRequest.decision.is_(None)
    )
    res = await db.execute(stmt)
    req = res.scalar_one_or_none()

    if not req:
        raise NotFoundError("No pending approval request found for this application")

    gate = ApprovalGate()
    service = ApplicationService(db=db, redis=redis)

    application = await gate.resolve_approval(db, req.approval_token, body.decision, body.reason, body.changed_by)
    app_id = str(application_id)

    if body.decision == "approved":
        await service.transition_status(
            application_id=app_id,
            new_status=ApplicationStatus.QUEUED,
            reason="Manual approval granted",
            changed_by=body.changed_by
        )

        payload = TaskPayload(
            application_id=app_id,
            user_id=str(application.user_id),
            job_id=str(application.job_id),
            method=application.method,
            priority=application.metadata_.get("priority", "normal") if application.metadata_ else "normal",
            attempt=1,
        )

        queue_name = "high" if payload.priority == "high" else "normal"
        task = process_application.apply_async(
            args=[payload.model_dump()],
            queue=queue_name,
            task_id=f"apply-{app_id}",
        )
        await service.attach_task_id(app_id, task.id)
        msg = "Application approved and enqueued"
    else:
        await service.transition_status(
            application_id=app_id,
            new_status=ApplicationStatus.FAILED,
            reason=f"Manual approval rejected: {body.reason}",
            changed_by=body.changed_by
        )
        msg = "Application rejected and marked failed"

    await db.commit()

    return SuccessResponse(
        data={
            "application_id": app_id,
            "status": application.status,
            "message": msg
        },
        meta=_make_meta(request)
    )


@router.get("/escalated", response_model=SuccessResponse)
async def get_escalated_approvals(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
) -> SuccessResponse:
    """Returns escalated approval requests."""
    stmt = select(ApprovalRequest).where(
        ApprovalRequest.decision.is_(None),
        ApprovalRequest.decision_reason.like("Escalation%")
    )
    res = await db.execute(stmt)
    reqs = res.scalars().all()

    items = []
    for req in reqs:
        app_stmt = select(Application).where(Application.application_id == req.application_id)
        app_res = await db.execute(app_stmt)
        app = app_res.scalar_one_or_none()
        if app:
            items.append({
                "id": req.approval_token,
                "application_id": str(req.application_id),
                "company_name": app.company_name,
                "role_title": app.role_title,
                "reason": req.decision_reason,
                "expires_at": req.expires_at.isoformat() if req.expires_at else None
            })

    return SuccessResponse(data={"items": items}, meta=_make_meta(request))
