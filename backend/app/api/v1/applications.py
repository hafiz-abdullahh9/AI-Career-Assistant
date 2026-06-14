"""
Applications API router — handles all /applications/* endpoints.

Architecture rules enforced here:
  1. Routes contain ZERO business logic — they call services only.
  2. Every route returns a standard envelope (SuccessResponse / ErrorResponse).
  3. Errors are caught by the global exception handler in main.py, not here.
  4. All heavy work is async — no blocking calls in route handlers.
"""
import uuid
from datetime import datetime, UTC

import os
import base64
import json
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.hitl.services.hitl_service import HitlService
from app.core.database import get_db
from app.core.redis import get_redis
from app.models.schemas import (
    ApplicationListItem,
    ApplicationResponse,
    ApplicationStatus,
    ApplicationSubmitRequest,
    ApplicationSubmitResponse,
    StatusUpdateRequest,
    SuccessResponse,
    TaskPayload,
)
from app.services.application_service import ApplicationService
from app.tasks.application_tasks import process_application

from pydantic import BaseModel, Field
from app.orchestration.pause_resume.pause_resume_control import PauseResumeControl
from app.orchestration.approvals.approval_gate import ApprovalGate


class PauseResumeRequest(BaseModel):
    user_id: str | None = None
    domain: str | None = None
    task_id: str | None = None
    global_pause: bool = False
    emergency_stop: bool = False


class ApprovalResolutionRequest(BaseModel):
    decision: str = Field(..., description="'approved' or 'rejected'")
    reason: str | None = Field(None, max_length=500)
    changed_by: str = "user"

router = APIRouter(prefix="/applications", tags=["Applications"])


def _make_meta(request: Request) -> dict:
    """Build standard response meta from request context."""
    return {
        "request_id": getattr(request.state, "trace_id", str(uuid.uuid4())),
        "timestamp": datetime.now(UTC),
    }


# ── POST /applications/submit ──────────────────────────────────────────────────

@router.post(
    "/submit",
    status_code=202,
    response_model=SuccessResponse,
    summary="Submit a job application",
    description=(
        "Validates the request, runs guardrails, creates a tracking record, "
        "and enqueues an async Celery task. Returns immediately with a tracking URL."
    ),
)
async def submit_application(
    body: ApplicationSubmitRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> SuccessResponse:
    """
    Entry point for job application submission.

    The route handler's only job:
      1. Call service to run guardrails + create DB record.
      2. Enqueue Celery task.
      3. Return 202 with tracking info.

    All business logic lives in ApplicationService.
    """
    service = ApplicationService(db=db, redis=redis)

    # ── Guardrails (fail fast before creating any record) ──────────────────
    await service.check_rate_limit(str(body.user_id))
    await service.check_duplicate(str(body.user_id), str(body.job_id))

    # ── Create application record ──────────────────────────────────────────
    application = await service.create_application(body)
    app_id = str(application.application_id)

    # ── Build task payload ─────────────────────────────────────────────────
    payload = TaskPayload(
        application_id=app_id,
        user_id=str(body.user_id),
        job_id=str(body.job_id),
        method=body.job_metadata.application_method.value,
        priority=body.guardrails.priority.value,
        attempt=1,
    )

    # ── Enqueue Celery task ────────────────────────────────────────────────
    # Queue selection based on priority
    queue_name = (
        "high" if body.guardrails.priority.value == "high" else "normal"
    )
    task = process_application.apply_async(
        args=[payload.model_dump()],
        queue=queue_name,
        task_id=f"apply-{app_id}",   # Deterministic task ID for dedup
    )

    # Store the task ID on the application record for observability
    await service.attach_task_id(app_id, task.id)

    return SuccessResponse(
        data=ApplicationSubmitResponse(
            application_id=application.application_id,
            status=ApplicationStatus.QUEUED,
            tracking_url=f"/api/v1/applications/{app_id}/status",
            message="Application queued for processing",
        ).model_dump(mode="json"),
        meta=_make_meta(request),
    )


# ── GET /applications/{application_id}/status ──────────────────────────────────

@router.get(
    "/{application_id}/status",
    response_model=SuccessResponse,
    summary="Get application status",
    description="Returns the current status and full details of a specific application.",
)
async def get_application_status(
    application_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> SuccessResponse:
    service = ApplicationService(db=db, redis=redis)
    application = await service.get_application(application_id)

    return SuccessResponse(
        data=ApplicationResponse.model_validate(application).model_dump(mode="json"),
        meta=_make_meta(request),
    )


# ── GET /applications ──────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=SuccessResponse,
    summary="List applications",
    description="Returns a paginated list of applications for a given user.",
)
async def list_applications(
    request: Request,
    user_id: str = Query(..., description="Filter by user UUID"),
    status: str | None = Query(None, description="Filter by application status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> SuccessResponse:
    service = ApplicationService(db=db, redis=redis)
    applications, total = await service.list_applications(
        user_id=user_id,
        status=status,
        limit=limit,
        offset=offset,
    )

    return SuccessResponse(
        data={
            "applications": [
                ApplicationListItem.model_validate(app).model_dump(mode="json")
                for app in applications
            ],
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total,
            },
        },
        meta=_make_meta(request),
    )


# ── PATCH /applications/{application_id}/status ────────────────────────────────

@router.patch(
    "/{application_id}/status",
    response_model=SuccessResponse,
    summary="Update application status",
    description=(
        "Manually transition an application to a new status. "
        "Validates transition is allowed per the state machine."
    ),
)
async def update_application_status(
    application_id: str,
    body: StatusUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> SuccessResponse:
    service = ApplicationService(db=db, redis=redis)
    application = await service.transition_status(
        application_id=application_id,
        new_status=body.status,
        reason=body.reason,
        changed_by=body.changed_by,
    )

    return SuccessResponse(
        data={
            "application_id": str(application.application_id),
            "status": application.status,
            "updated_at": application.updated_at.isoformat(),
        },
        meta=_make_meta(request),
    )


# ── GET /applications/{application_id}/history ────────────────────────────────

@router.get(
    "/{application_id}/history",
    response_model=SuccessResponse,
    summary="Get status history",
    description="Returns the full status transition audit trail for an application.",
)
async def get_application_history(
    application_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> SuccessResponse:
    service = ApplicationService(db=db, redis=redis)
    history = await service.get_status_history(application_id)

    return SuccessResponse(
        data={
            "application_id": application_id,
            "history": [
                {
                    "from_status": h.from_status,
                    "to_status": h.to_status,
                    "reason": h.reason,
                    "changed_by": h.changed_by,
                    "created_at": h.created_at.isoformat(),
                }
                for h in history
            ],
        },
        meta=_make_meta(request),
    )


# ── DELETE /applications/{application_id} ─────────────────────────────────────

@router.delete(
    "/{application_id}",
    response_model=SuccessResponse,
    summary="Delete application",
    description="Soft-deletes an application record. The data is retained but hidden.",
)
async def delete_application(
    application_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> SuccessResponse:
    service = ApplicationService(db=db, redis=redis)
    application = await service.soft_delete(application_id)

    return SuccessResponse(
        data={
            "application_id": str(application.application_id),
            "deleted_at": application.deleted_at.isoformat(),
        },
        meta=_make_meta(request),
    )


# ── POST /applications/{application_id}/retry ─────────────────────────────────

class RetryRequest(BaseModel):
    reason: str | None = Field(None, max_length=500, description="Reason for retry")


@router.post(
    "/{application_id}/retry",
    response_model=SuccessResponse,
    summary="Retry a failed application",
    description="Re-enqueues a failed application for another processing attempt.",
)
async def retry_application(
    application_id: str,
    request: Request,
    body: RetryRequest | None = None,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> SuccessResponse:
    """Retry a failed application by resetting to QUEUED and re-enqueuing."""
    service = ApplicationService(db=db, redis=redis)
    application = await service.get_application(application_id)

    # Only allow retry from terminal-failure or retryable states
    retryable_statuses = {"failed", "asset_error", "email_failed"}
    if application.status not in retryable_statuses:
        from app.core.exceptions import ConflictError
        raise ConflictError(
            f"Application in status '{application.status}' is not eligible for retry.",
            details={"current_status": application.status, "retryable_statuses": list(retryable_statuses)},
        )

    # Check retry budget
    if application.retry_count >= application.max_retries:
        from app.core.exceptions import ConflictError
        raise ConflictError(
            f"Application has exhausted all {application.max_retries} retry attempts.",
            details={"retry_count": application.retry_count, "max_retries": application.max_retries},
        )

    # Increment retry count
    await service.increment_retry_count(application_id)

    # Transition back to QUEUED (FAILED has no outbound transitions by default,
    # so we update status directly for retry)
    reason = (body.reason if body and body.reason else "Manual retry requested") + f" (attempt {application.retry_count + 1})"
    application.status = ApplicationStatus.QUEUED.value
    from app.models.orm import ApplicationStatusHistory
    history = ApplicationStatusHistory(
        application_id=application.application_id,
        from_status="failed",
        to_status=ApplicationStatus.QUEUED.value,
        reason=reason,
        changed_by="user",
    )
    db.add(history)
    await db.flush()

    # Re-enqueue Celery task
    payload = TaskPayload(
        application_id=application_id,
        user_id=str(application.user_id),
        job_id=str(application.job_id),
        method=application.method,
        priority=application.metadata_.get("priority", "normal") if application.metadata_ else "normal",
        attempt=application.retry_count + 1,
    )

    queue_name = "high" if payload.priority == "high" else "normal"
    task = process_application.apply_async(
        args=[payload.model_dump()],
        queue=queue_name,
        task_id=f"apply-{application_id}-retry-{application.retry_count}",
    )
    await service.attach_task_id(application_id, task.id)

    return SuccessResponse(
        data={
            "application_id": application_id,
            "status": ApplicationStatus.QUEUED.value,
            "retry_count": application.retry_count,
            "message": f"Application re-enqueued for retry (attempt {application.retry_count})",
        },
        meta=_make_meta(request),
    )


# ── POST /applications/pause ──────────────────────────────────────────────────

@router.post(
    "/pause",
    response_model=SuccessResponse,
    summary="Pause application queue",
)
async def pause_applications(
    body: PauseResumeRequest,
    request: Request,
    redis=Depends(get_redis),
) -> SuccessResponse:
    control = PauseResumeControl(redis)
    if body.emergency_stop:
        await control.set_emergency_stop(True)
    if body.global_pause:
        await control.set_global_pause(True)
    if body.user_id:
        await control.set_user_pause(body.user_id, True)
    if body.domain:
        await control.set_domain_pause(body.domain, True)
    if body.task_id:
        await control.set_task_pause(body.task_id, True)

    return SuccessResponse(
        data={"message": "Paused successfully"},
        meta=_make_meta(request),
    )


# ── POST /applications/resume ─────────────────────────────────────────────────

@router.post(
    "/resume",
    response_model=SuccessResponse,
    summary="Resume application queue",
)
async def resume_applications(
    body: PauseResumeRequest,
    request: Request,
    redis=Depends(get_redis),
) -> SuccessResponse:
    control = PauseResumeControl(redis)
    if body.emergency_stop:
        await control.set_emergency_stop(False)
    if body.global_pause:
        await control.set_global_pause(False)
    if body.user_id:
        await control.set_user_pause(body.user_id, False)
    if body.domain:
        await control.set_domain_pause(body.domain, False)
    if body.task_id:
        await control.set_task_pause(body.task_id, False)

    return SuccessResponse(
        data={"message": "Resumed successfully"},
        meta=_make_meta(request),
    )


# ── POST /applications/approvals/{token}/resolve ─────────────────────────────

@router.post(
    "/approvals/{token}/resolve",
    response_model=SuccessResponse,
    summary="Resolve manual approval request",
)
async def resolve_approval(
    token: str,
    body: ApprovalResolutionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> SuccessResponse:
    gate = ApprovalGate()
    service = ApplicationService(db=db, redis=redis)

    # 1. Resolve approval request in DB
    application = await gate.resolve_approval(db, token, body.decision, body.reason, body.changed_by)
    app_id = str(application.application_id)

    if body.decision == "approved":
        # Transition to QUEUED
        await service.transition_status(
            application_id=app_id,
            new_status=ApplicationStatus.QUEUED,
            reason="Manual approval granted",
            changed_by=body.changed_by
        )

        # Enqueue task
        payload = TaskPayload(
            application_id=app_id,
            user_id=str(application.user_id),
            job_id=str(application.job_id),
            method=application.method,
            priority=application.metadata_.get("priority", "normal") if application.metadata_ else "normal",
            attempt=1,
        )

        queue_name = (
            "high" if payload.priority == "high" else "normal"
        )
        task = process_application.apply_async(
            args=[payload.model_dump()],
            queue=queue_name,
            task_id=f"apply-{app_id}",
        )
        await service.attach_task_id(app_id, task.id)
        msg = "Application approved and enqueued"
    else:
        # Transition to FAILED
        await service.transition_status(
            application_id=app_id,
            new_status=ApplicationStatus.FAILED,
            reason=f"Manual approval rejected: {body.reason}",
            changed_by=body.changed_by
        )
        msg = "Application rejected and marked failed"

    return SuccessResponse(
        data={
            "application_id": app_id,
            "status": application.status,
            "message": msg
        },
        meta=_make_meta(request),
    )



class ResolveChecklistRequest(BaseModel):
    decision: str
    reason: str | None = None
    checklist: dict[str, bool]
    operator_id: str = "operator"


class EscalateRequest(BaseModel):
    reason: str
    operator_id: str = "operator"


class CancelRequest(BaseModel):
    reason: str
    operator_id: str = "operator"


# ── GET /applications/approvals/dashboard ────────────────────────────────────

@router.get("/approvals/dashboard", response_class=HTMLResponse)
async def get_approvals_dashboard(request: Request):
    """
    Renders the HITL Operational Control Center / Dashboard page.
    """
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>HITL Governance & Control Center</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-primary: #0f172a;
                --bg-secondary: #1e293b;
                --border-color: rgba(255, 255, 255, 0.08);
                --text-main: #f8fafc;
                --text-sub: #94a3b8;
                --accent-blue: #3b82f6;
                --accent-green: #10b981;
                --accent-red: #ef4444;
                --accent-orange: #f59e0b;
            }
            body {
                font-family: 'Outfit', sans-serif;
                background-color: var(--bg-primary);
                color: var(--text-main);
                margin: 0;
                padding: 0;
                height: 100vh;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
            header {
                background-color: var(--bg-secondary);
                border-bottom: 1px solid var(--border-color);
                padding: 15px 30px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                flex-shrink: 0;
            }
            .logo-section h1 {
                font-size: 20px;
                font-weight: 600;
                margin: 0;
                color: #f1f5f9;
            }
            .logo-section p {
                font-size: 12px;
                color: var(--text-sub);
                margin: 4px 0 0 0;
            }
            .main-layout {
                display: flex;
                flex: 1;
                overflow: hidden;
            }
            .sidebar {
                width: 320px;
                background-color: var(--bg-secondary);
                border-right: 1px solid var(--border-color);
                display: flex;
                flex-direction: column;
                flex-shrink: 0;
            }
            .tab-menu {
                padding: 20px 10px;
                display: flex;
                flex-direction: column;
                gap: 8px;
            }
            .tab-item {
                background: none;
                border: 1px solid transparent;
                color: var(--text-sub);
                padding: 12px 16px;
                text-align: left;
                font-family: inherit;
                font-size: 13px;
                font-weight: 500;
                border-radius: 8px;
                cursor: pointer;
                transition: all 0.2s;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .tab-item:hover {
                background-color: rgba(255, 255, 255, 0.02);
                color: var(--text-main);
            }
            .tab-item.active {
                background-color: rgba(59, 130, 246, 0.1);
                color: var(--accent-blue);
                border-color: rgba(59, 130, 246, 0.2);
            }
            .badge {
                font-size: 11px;
                font-weight: 600;
                padding: 2px 6px;
                border-radius: 999px;
                background-color: rgba(255,255,255,0.08);
                color: var(--text-sub);
            }
            .tab-item.active .badge {
                background-color: var(--accent-blue);
                color: white;
            }
            .queue-list-panel {
                width: 400px;
                border-right: 1px solid var(--border-color);
                display: flex;
                flex-direction: column;
                overflow-y: auto;
                background-color: #111827;
                flex-shrink: 0;
            }
            .panel-header {
                padding: 20px;
                border-bottom: 1px solid var(--border-color);
                font-size: 14px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: var(--text-sub);
            }
            .search-box {
                padding: 10px 20px;
                border-bottom: 1px solid var(--border-color);
            }
            .search-box input {
                width: 100%;
                background-color: rgba(255,255,255,0.05);
                border: 1px solid var(--border-color);
                border-radius: 6px;
                padding: 8px 12px;
                color: white;
                font-family: inherit;
                font-size: 13px;
                box-sizing: border-box;
            }
            .app-card {
                padding: 16px 20px;
                border-bottom: 1px solid var(--border-color);
                cursor: pointer;
                transition: all 0.2s;
            }
            .app-card:hover {
                background-color: rgba(255,255,255,0.02);
            }
            .app-card.selected {
                background-color: rgba(59, 130, 246, 0.05);
                border-left: 3px solid var(--accent-blue);
            }
            .card-header {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-bottom: 6px;
            }
            .card-title {
                font-size: 14px;
                font-weight: 600;
                color: var(--text-main);
            }
            .priority-tag {
                font-size: 10px;
                font-weight: 600;
                text-transform: uppercase;
                padding: 2px 6px;
                border-radius: 4px;
            }
            .priority-high { background-color: rgba(239, 68, 68, 0.15); color: var(--accent-red); }
            .priority-normal { background-color: rgba(59, 130, 246, 0.15); color: var(--accent-blue); }
            .priority-low { background-color: rgba(156, 163, 175, 0.15); color: var(--text-sub); }
            .card-meta {
                font-size: 12px;
                color: var(--text-sub);
                margin-bottom: 4px;
            }
            .card-reason {
                font-size: 12px;
                color: var(--accent-orange);
                font-style: italic;
            }
            .detail-panel {
                flex: 1;
                display: flex;
                flex-direction: column;
                overflow-y: auto;
                padding: 30px;
                background-color: #0b0f19;
            }
            .detail-header {
                border-bottom: 1px solid var(--border-color);
                padding-bottom: 20px;
                margin-bottom: 25px;
            }
            .detail-header h2 {
                margin: 0 0 8px 0;
                font-size: 22px;
                font-weight: 600;
            }
            .detail-subtitle {
                color: var(--text-sub);
                font-size: 14px;
            }
            .section-title {
                font-size: 14px;
                font-weight: 600;
                text-transform: uppercase;
                color: var(--text-sub);
                margin-top: 0;
                margin-bottom: 15px;
                letter-spacing: 0.05em;
            }
            .diff-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
                margin-bottom: 30px;
            }
            .diff-card {
                background-color: var(--bg-secondary);
                border: 1px solid var(--border-color);
                border-radius: 12px;
                padding: 20px;
            }
            .field-row {
                display: flex;
                justify-content: space-between;
                padding: 10px 0;
                border-bottom: 1px solid rgba(255,255,255,0.04);
                font-size: 13px;
            }
            .field-row:last-child { border-bottom: none; }
            .field-label { color: var(--text-sub); }
            .field-value { font-weight: 600; }
            .field-value.missing { color: var(--accent-red); }
            .field-value.ok { color: var(--accent-green); }
            .checklist-section {
                background-color: rgba(245, 158, 11, 0.03);
                border: 1px dashed rgba(245, 158, 11, 0.2);
                border-radius: 12px;
                padding: 25px;
                margin-bottom: 30px;
            }
            .checkbox-item {
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 12px;
                font-size: 14px;
                cursor: pointer;
            }
            .checkbox-item input {
                width: 18px;
                height: 18px;
                cursor: pointer;
            }
            .action-bar {
                display: flex;
                gap: 15px;
                align-items: center;
                margin-top: 10px;
            }
            .btn {
                font-family: inherit;
                font-size: 14px;
                font-weight: 600;
                padding: 12px 24px;
                border-radius: 8px;
                cursor: pointer;
                border: 1px solid transparent;
                transition: all 0.2s;
            }
            .btn-approve {
                background-color: var(--accent-green);
                color: white;
            }
            .btn-approve:hover:not(:disabled) {
                background-color: #059669;
            }
            .btn-approve:disabled {
                opacity: 0.4;
                cursor: not-allowed;
            }
            .btn-reject {
                background-color: rgba(239, 68, 68, 0.15);
                color: var(--accent-red);
                border-color: rgba(239, 68, 68, 0.3);
            }
            .btn-reject:hover {
                background-color: rgba(239, 68, 68, 0.25);
            }
            .btn-cancel {
                background-color: rgba(245, 158, 11, 0.15);
                color: var(--accent-orange);
                border-color: rgba(245, 158, 11, 0.3);
            }
            .btn-cancel:hover {
                background-color: rgba(245, 158, 11, 0.25);
            }
            .btn-escalate {
                background-color: rgba(59, 130, 246, 0.15);
                color: var(--accent-blue);
                border-color: rgba(59, 130, 246, 0.3);
            }
            .btn-escalate:hover {
                background-color: rgba(59, 130, 246, 0.25);
            }
            .reason-input {
                width: 100%;
                background-color: var(--bg-secondary);
                border: 1px solid var(--border-color);
                border-radius: 8px;
                padding: 12px;
                color: white;
                font-family: inherit;
                font-size: 13px;
                margin-bottom: 20px;
                box-sizing: border-box;
                resize: vertical;
            }
            .empty-state {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100%;
                color: var(--text-sub);
                text-align: center;
            }
            .empty-state h3 { color: var(--text-main); margin-bottom: 8px; }
            .audit-log-table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 10px;
                font-size: 13px;
            }
            .audit-log-table th {
                text-align: left;
                padding: 12px 16px;
                background-color: var(--bg-secondary);
                color: var(--text-sub);
                border-bottom: 1px solid var(--border-color);
            }
            .audit-log-table td {
                padding: 12px 16px;
                border-bottom: 1px solid var(--border-color);
            }
            .decision-badge {
                font-size: 10px;
                font-weight: bold;
                text-transform: uppercase;
                padding: 2px 6px;
                border-radius: 4px;
            }
            .decision-approved { background-color: rgba(16, 185, 129, 0.15); color: var(--accent-green); }
            .decision-rejected { background-color: rgba(239, 68, 68, 0.15); color: var(--accent-red); }
            .replay-iframe-container {
                margin-top: 25px;
                height: 450px;
                border: 1px solid var(--border-color);
                border-radius: 12px;
                overflow: hidden;
            }
            .replay-iframe-container iframe {
                width: 100%;
                height: 100%;
                border: none;
            }
        </style>
    </head>
    <body>
        <header>
            <div class="logo-section">
                <h1>HITL Control Center</h1>
                <p>Human-in-the-Loop Governance, Approvals, & Escalate Workflows</p>
            </div>
            <div class="operator-badge">
                <span class="badge" style="background-color: var(--accent-blue); color: white; padding: 6px 12px;">OPERATOR ACTIVE</span>
            </div>
        </header>

        <div class="main-layout">
            <div class="sidebar">
                <div class="tab-menu">
                    <button class="tab-item active" id="tab-awaiting" onclick="switchQueue('awaiting_approval')">
                        <span>Awaiting Approval</span>
                        <span class="badge" id="badge-awaiting">0</span>
                    </button>
                    <button class="tab-item" id="tab-mismatch" onclick="switchQueue('selector_mismatch')">
                        <span>Selector Mismatches</span>
                        <span class="badge" id="badge-mismatch">0</span>
                    </button>
                    <button class="tab-item" id="tab-assets" onclick="switchQueue('missing_assets')">
                        <span>Missing Assets</span>
                        <span class="badge" id="badge-assets">0</span>
                    </button>
                    <button class="tab-item" id="tab-failed" onclick="switchQueue('failed_execution')">
                        <span>Failed Executions</span>
                        <span class="badge" id="badge-failed">0</span>
                    </button>
                    <button class="tab-item" id="tab-replay" onclick="switchQueue('replay_review')">
                        <span>Replay Reviews</span>
                        <span class="badge" id="badge-replay">0</span>
                    </button>
                    <button class="tab-item" id="tab-retry" onclick="switchQueue('retry_approval')">
                        <span>Retry Approvals</span>
                        <span class="badge" id="badge-retry">0</span>
                    </button>
                    <button class="tab-item" id="tab-audit" onclick="switchQueue('audit_logs')">
                        <span>Operator Audits</span>
                        <span class="badge" id="badge-audit">Logs</span>
                    </button>
                </div>
            </div>

            <div class="queue-list-panel">
                <div class="panel-header" id="queue-title">Awaiting Approval Queue</div>
                <div class="search-box">
                    <input type="text" id="search-input" placeholder="Search applications..." oninput="filterQueue()">
                </div>
                <div id="queue-items-container">
                    <!-- Cards injected here -->
                </div>
            </div>

            <div class="detail-panel" id="detail-panel-container">
                <div class="empty-state" id="empty-state-view">
                    <h3>Select an Application</h3>
                    <p>Click on any execution card in the queue list to load details, checklists, differences, and rollback controls.</p>
                </div>
                
                <div id="detail-content-view" style="display: none;">
                    <!-- Details injected here -->
                </div>
            </div>
        </div>

        <script>
            let currentQueueKey = 'awaiting_approval';
            let queuesData = {};
            let selectedAppId = null;

            async function fetchQueues() {
                try {
                    const response = await fetch('/api/v1/applications/approvals/pending');
                    const envelope = await response.json();
                    queuesData = envelope.data;

                    // Update badges
                    document.getElementById('badge-awaiting').innerText = queuesData.awaiting_approval.length;
                    document.getElementById('badge-mismatch').innerText = queuesData.selector_mismatch.length;
                    document.getElementById('badge-assets').innerText = queuesData.missing_assets.length;
                    document.getElementById('badge-failed').innerText = queuesData.failed_execution.length;
                    document.getElementById('badge-replay').innerText = queuesData.replay_review.length;
                    document.getElementById('badge-retry').innerText = queuesData.retry_approval.length;

                    renderQueueList();
                } catch (e) {
                    console.error("Failed to fetch queues", e);
                }
            }

            async function fetchAuditLogs() {
                try {
                    const response = await fetch('/api/v1/applications/approvals/audit-logs');
                    const envelope = await response.json();
                    const logs = envelope.data;

                    const container = document.getElementById('queue-items-container');
                    container.innerHTML = '';

                    const detailPanel = document.getElementById('detail-panel-container');
                    detailPanel.innerHTML = `
                        <div class="panel-header" style="padding-left:0; margin-bottom: 20px;">Operator Action Audits</div>
                        <table class="audit-log-table">
                            <thead>
                                <tr>
                                    <th>Application</th>
                                    <th>Resolved At</th>
                                    <th>Decision</th>
                                    <th>Reason</th>
                                    <th>Operator</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${logs.map(log => `
                                    <tr>
                                        <td><strong>${log.company_name}</strong><br><span style="font-size:11px;color:var(--text-sub);">${log.role_title}</span></td>
                                        <td>${new Date(log.resolved_at).toLocaleString()}</td>
                                        <td><span class="decision-badge decision-${log.decision}">${log.decision}</span></td>
                                        <td>${log.decision_reason || 'N/A'}</td>
                                        <td><code>${log.decided_by}</code></td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    `;
                } catch(e) {
                    console.error("Failed to fetch audit logs", e);
                }
            }

            function switchQueue(queueKey) {
                currentQueueKey = queueKey;
                
                // Update active tab styles
                document.querySelectorAll('.tab-item').forEach(btn => btn.classList.remove('active'));
                
                let tabId = 'tab-awaiting';
                let title = 'Awaiting Approval Queue';
                
                if (queueKey === 'awaiting_approval') { tabId = 'tab-awaiting'; title = 'Awaiting Approval Queue'; }
                else if (queueKey === 'selector_mismatch') { tabId = 'tab-mismatch'; title = 'Selector Mismatches'; }
                else if (queueKey === 'missing_assets') { tabId = 'tab-assets'; title = 'Missing Assets'; }
                else if (queueKey === 'failed_execution') { tabId = 'tab-failed'; title = 'Failed Executions'; }
                else if (queueKey === 'replay_review') { tabId = 'tab-replay'; title = 'Replay Reviews'; }
                else if (queueKey === 'retry_approval') { tabId = 'tab-retry'; title = 'Retry Approvals'; }
                else if (queueKey === 'audit_logs') { tabId = 'tab-audit'; title = 'Operator Audits'; }

                document.getElementById(tabId).classList.add('active');
                document.getElementById('queue-title').innerText = title;

                // Reset detail view
                resetDetailPanel();

                if (queueKey === 'audit_logs') {
                    fetchAuditLogs();
                } else {
                    renderQueueList();
                }
            }

            function renderQueueList() {
                const container = document.getElementById('queue-items-container');
                container.innerHTML = '';
                
                const list = queuesData[currentQueueKey] || [];
                if (list.length === 0) {
                    container.innerHTML = '<div style="padding: 30px; text-align:center; color: var(--text-sub); font-size:13px;">No applications in this queue.</div>';
                    return;
                }

                list.forEach(app => {
                    const card = document.createElement('div');
                    card.className = `app-card ${selectedAppId === app.application_id ? 'selected' : ''}`;
                    card.onclick = () => selectApplication(app.application_id, app.approval_token, app.status);
                    
                    const timeStr = new Date(app.updated_at).toLocaleTimeString();

                    card.innerHTML = `
                        <div class="card-header">
                            <div class="card-title">${app.company_name}</div>
                            <span class="priority-tag priority-${app.priority}">${app.priority}</span>
                        </div>
                        <div class="card-meta">${app.role_title}</div>
                        <div class="card-meta" style="font-size:11px;">Status: <strong>${app.status.toUpperCase()}</strong></div>
                        <div class="card-reason">${app.reason || ''}</div>
                    `;
                    container.appendChild(card);
                });
            }

            function filterQueue() {
                const query = document.getElementById('search-input').value.toLowerCase();
                const cards = document.querySelectorAll('.app-card');
                
                cards.forEach(card => {
                    const title = card.querySelector('.card-title').innerText.toLowerCase();
                    const meta = card.querySelector('.card-meta').innerText.toLowerCase();
                    if (title.includes(query) || meta.includes(query)) {
                        card.style.display = 'block';
                    } else {
                        card.style.display = 'none';
                    }
                });
            }

            function resetDetailPanel() {
                const detailPanel = document.getElementById('detail-panel-container');
                detailPanel.innerHTML = `
                    <div class="empty-state" id="empty-state-view">
                        <h3>Select an Application</h3>
                        <p>Click on any execution card in the queue list to load details, checklists, differences, and rollback controls.</p>
                    </div>
                `;
                selectedAppId = null;
            }

            async function selectApplication(appId, token, status) {
                selectedAppId = appId;
                renderQueueList();

                const response = await fetch(`/api/v1/applications/${appId}/diff`);
                const envelope = await response.json();
                const diff = envelope.data;

                const detailPanel = document.getElementById('detail-panel-container');
                
                let statusUpper = status.toUpperCase();

                // Build Actions HTML based on app status
                let actionsHtml = '';
                let checklistHtml = '';

                if (status === 'pending_approval' && token) {
                    checklistHtml = `
                        <div class="checklist-section">
                            <div class="section-title" style="color: var(--accent-orange);">Governance Checkpoints Checklist</div>
                            <label class="checkbox-item">
                                <input type="checkbox" id="chk-domain" onchange="validateChecklist()">
                                <span>Target domain allowlist verified and marked safe</span>
                            </label>
                            <label class="checkbox-item">
                                <input type="checkbox" id="chk-resume" onchange="validateChecklist()">
                                <span>Candidate resume document verified and valid</span>
                            </label>
                            <label class="checkbox-item">
                                <input type="checkbox" id="chk-fields" onchange="validateChecklist()">
                                <span>Input form fields completed without unmapped required inputs</span>
                            </label>
                        </div>
                    `;
                    actionsHtml = `
                        <textarea class="reason-input" id="reason-text" placeholder="Resolution reason / Operator comments (required on rejection)..."></textarea>
                        <div class="action-bar">
                            <button class="btn btn-approve" id="btn-submit-approve" disabled onclick="resolveApp('${token}', 'approved')">Approve & Enqueue</button>
                            <button class="btn btn-reject" onclick="resolveApp('${token}', 'rejected')">Reject & Fail</button>
                        </div>
                    `;
                } else if (status === 'queued' || status === 'processing') {
                    actionsHtml = `
                        <textarea class="reason-input" id="cancel-reason" placeholder="Cancellation reason (required)..."></textarea>
                        <div class="action-bar">
                            <button class="btn btn-cancel" onclick="cancelExecution('${appId}')">Cancel Execution / Rollback</button>
                        </div>
                    `;
                } else if (status === 'failed' || status === 'asset_error') {
                    actionsHtml = `
                        <textarea class="reason-input" id="escalate-reason" placeholder="Escalation reason (required)..."></textarea>
                        <div class="action-bar">
                            <button class="btn btn-escalate" onclick="escalateApplication('${appId}')">Escalate Back to Queue</button>
                        </div>
                    `;
                }

                // Show visual replay option if it is applied or failed
                let replayHtml = '';
                if (status === 'applied' || status === 'failed') {
                    replayHtml = `
                        <div class="section-title" style="margin-top:30px;">Integrated Replay Verification</div>
                        <div class="replay-iframe-container">
                            <iframe src="/api/v1/applications/${appId}/replay"></iframe>
                        </div>
                    `;
                }

                detailPanel.innerHTML = `
                    <div class="detail-header">
                        <h2>${diff.company_name}</h2>
                        <div class="detail-subtitle">${diff.role_title} &bull; Target URL: <a href="${diff.application_url}" target="_blank" style="color:var(--accent-blue);">${diff.application_url}</a></div>
                    </div>

                    <div class="section-title">Application Parameters & Difference Check</div>
                    <div class="diff-grid">
                        <div class="diff-card">
                            <div class="section-title" style="font-size:12px;">Expected Fields</div>
                            ${diff.required_fields.map(field => `
                                <div class="field-row">
                                    <span class="field-label">${field}</span>
                                    <span class="field-value ok">Required</span>
                                </div>
                            `).join('') || '<div style="font-size:13px;color:var(--text-sub);">No specific fields required.</div>'}
                        </div>
                        <div class="diff-card">
                            <div class="section-title" style="font-size:12px;">Candidate Values</div>
                            ${Object.entries(diff.mapped_fields).map(([k, v]) => `
                                <div class="field-row">
                                    <span class="field-label">${k}</span>
                                    <span class="field-value">${v}</span>
                                </div>
                            `).join('') || '<div style="font-size:13px;color:var(--text-sub);">No fields provided.</div>'}
                            ${diff.unmapped_fields.map(field => `
                                <div class="field-row">
                                    <span class="field-label">${field}</span>
                                    <span class="field-value missing">Unmapped Mismatch</span>
                                </div>
                            `).join('')}
                        </div>
                    </div>

                    <div class="diff-card" style="margin-bottom:30px;">
                        <div class="section-title" style="font-size:12px;">Asset Verification</div>
                        <div class="field-row">
                            <span class="field-label">Resume Document</span>
                            <span class="field-value ${diff.has_resume ? 'ok' : 'missing'}">${diff.has_resume ? 'Verified (PDF)' : 'Missing'}</span>
                        </div>
                        <div class="field-row">
                            <span class="field-label">Cover Letter Document</span>
                            <span class="field-value">${diff.has_cover_letter ? 'Attached' : 'Not Attached'}</span>
                        </div>
                    </div>

                    ${checklistHtml}
                    ${actionsHtml}
                    ${replayHtml}
                `;
            }

            function validateChecklist() {
                const domain = document.getElementById('chk-domain').checked;
                const resume = document.getElementById('chk-resume').checked;
                const fields = document.getElementById('chk-fields').checked;
                
                document.getElementById('btn-submit-approve').disabled = !(domain && resume && fields);
            }

            async function resolveApp(token, decision) {
                const reason = document.getElementById('reason-text').value;
                if (decision === 'rejected' && !reason) {
                    alert('Please specify a rejection reason.');
                    return;
                }

                const checklist = {
                    domain_verified: document.getElementById('chk-domain') ? document.getElementById('chk-domain').checked : true,
                    resume_verified: document.getElementById('chk-resume') ? document.getElementById('chk-resume').checked : true,
                    fields_verified: document.getElementById('chk-fields') ? document.getElementById('chk-fields').checked : true
                };

                const res = await fetch(`/api/v1/applications/approvals/${token}/resolve-checklist`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        decision: decision,
                        reason: reason,
                        checklist: checklist,
                        operator_id: "operator_01"
                    })
                });

                if (res.ok) {
                    alert(`Application successfully ${decision}.`);
                    resetDetailPanel();
                    fetchQueues();
                } else {
                    const err = await res.json();
                    alert(`Resolution failed: ${err.error.message}`);
                }
            }

            async function cancelExecution(appId) {
                const reason = document.getElementById('cancel-reason').value;
                if (!reason) {
                    alert('Please specify a cancellation reason.');
                    return;
                }

                const res = await fetch(`/api/v1/applications/${appId}/cancel`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ reason: reason, operator_id: "operator_01" })
                });

                if (res.ok) {
                    alert('Execution canceled successfully.');
                    resetDetailPanel();
                    fetchQueues();
                } else {
                    alert('Failed to cancel execution.');
                }
            }

            async function escalateApplication(appId) {
                const reason = document.getElementById('escalate-reason').value;
                if (!reason) {
                    alert('Please specify an escalation reason.');
                    return;
                }

                const res = await fetch(`/api/v1/applications/${appId}/escalate`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ reason: reason, operator_id: "operator_01" })
                });

                if (res.ok) {
                    alert('Application escalated successfully.');
                    resetDetailPanel();
                    fetchQueues();
                } else {
                    alert('Failed to escalate application.');
                }
            }

            // Init load
            fetchQueues();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.get("/approvals/pending", response_model=SuccessResponse)
async def get_pending_queues(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> SuccessResponse:
    """
    Exposes categorized review queues.
    """
    service = HitlService(db)
    queues = await service.get_queues()
    return SuccessResponse(data=queues, meta=_make_meta(request))


@router.get("/approvals/audit-logs", response_model=SuccessResponse)
async def get_operator_audit_logs(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> SuccessResponse:
    """
    Exposes completed operator decisions log trail.
    """
    service = HitlService(db)
    logs = await service.get_audit_logs()
    return SuccessResponse(data=logs, meta=_make_meta(request))


@router.get("/{application_id}/diff", response_model=SuccessResponse)
async def get_application_diff(
    application_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> SuccessResponse:
    """
    Generates difference mapping for an application.
    """
    service = HitlService(db)
    diff = await service.get_app_diff(application_id)
    return SuccessResponse(data=diff, meta=_make_meta(request))


@router.post("/approvals/{token}/resolve-checklist", response_model=SuccessResponse)
async def resolve_approval_with_checklist(
    token: str,
    body: ResolveChecklistRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis)
) -> SuccessResponse:
    """
    Resolves manual approval request using operator checklist confirmation checkpoints.
    """
    service = HitlService(db)
    application = await service.resolve_with_checklist(
        token=token,
        decision=body.decision,
        reason=body.reason,
        checklist=body.checklist,
        operator_id=body.operator_id
    )
    
    app_id = str(application.application_id)

    # If operator approved, trigger task execution pipeline
    if body.decision == "approved":
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
        app_service = ApplicationService(db=db, redis=redis)
        await app_service.attach_task_id(app_id, task.id)
        msg = "Application enqueued via operator approval"
    else:
        msg = "Application rejected via operator review"

    await db.commit()

    return SuccessResponse(
        data={
            "application_id": app_id,
            "status": application.status,
            "message": msg
        },
        meta=_make_meta(request)
    )


@router.post("/{application_id}/escalate", response_model=SuccessResponse)
async def escalate_failed_application(
    application_id: uuid.UUID,
    body: EscalateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> SuccessResponse:
    """
    Manually escalates a failed / asset_error application back into the review queues.
    """
    service = HitlService(db)
    application = await service.escalate_application(
        application_id=application_id,
        reason=body.reason,
        operator_id=body.operator_id
    )
    await db.commit()
    return SuccessResponse(
        data={
            "application_id": str(application.application_id),
            "status": application.status,
            "message": "Application escalated back to operator review queues"
        },
        meta=_make_meta(request)
    )


@router.post("/{application_id}/cancel", response_model=SuccessResponse)
async def cancel_running_execution(
    application_id: uuid.UUID,
    body: CancelRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> SuccessResponse:
    """
    Operator cancel control to immediately stop queued or processing tasks.
    """
    service = HitlService(db)
    application = await service.cancel_execution(
        application_id=application_id,
        reason=body.reason,
        operator_id=body.operator_id
    )
    await db.commit()
    return SuccessResponse(
        data={
            "application_id": str(application.application_id),
            "status": application.status,
            "message": "Execution canceled and slots rolled back"
        },
        meta=_make_meta(request)
    )


class RetryRequest(BaseModel):
    reason: str | None = None


@router.post(
    "/{application_id}/retry",
    status_code=202,
    response_model=SuccessResponse,
    summary="Retry a failed application",
)
async def retry_application(
    application_id: uuid.UUID,
    body: RetryRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> SuccessResponse:
    service = ApplicationService(db=db, redis=redis)
    application = await service.get_application(str(application_id))

    if application.status in (ApplicationStatus.QUEUED.value, ApplicationStatus.PROCESSING.value):
        return SuccessResponse(
            success=False,
            data={"message": "Application is already queued or processing"},
            meta=_make_meta(request)
        )

    # Force reset status to QUEUED (bypassing normal state machine transition checks)
    application.status = ApplicationStatus.QUEUED.value
    application.retry_count = 0  # reset for new manual attempt

    await service._append_status_history(
        application=application,
        from_status=None,
        to_status=ApplicationStatus.QUEUED,
        reason=body.reason or "Manual retry requested",
        changed_by="operator"
    )

    payload = TaskPayload(
        application_id=str(application_id),
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
        task_id=f"apply-{application_id}",
    )
    await service.attach_task_id(str(application_id), task.id)
    await db.commit()

    return SuccessResponse(
        data={
            "application_id": str(application_id),
            "status": application.status,
            "message": "Application requeued for retry"
        },
        meta=_make_meta(request)
    )



# ── GET /applications/{application_id}/replay ───────────────────────────────

def _find_trace_files(application_id: str):
    artifacts_env = os.environ.get("ANTIGRAVITY_ARTIFACTS_DIR")
    if artifacts_env:
        traces_dir = os.path.join(artifacts_env, "traces")
        screenshots_dir = os.path.join(artifacts_env, "screenshots")
    else:
        traces_dir = os.path.join(os.getcwd(), "storage", "traces")
        screenshots_dir = os.path.join(os.getcwd(), "storage", "screenshots")

    prefix = f"trace_sess_{application_id[:8]}_"
    
    json_files = []
    html_files = []
    if os.path.exists(traces_dir):
        for fname in os.listdir(traces_dir):
            if fname.startswith(prefix):
                full_path = os.path.join(traces_dir, fname)
                if fname.endswith(".json"):
                    json_files.append(full_path)
                elif fname.endswith(".html"):
                    html_files.append(full_path)
    
    json_files.sort(key=os.path.getmtime, reverse=True)
    html_files.sort(key=os.path.getmtime, reverse=True)
    
    json_file = json_files[0] if json_files else None
    html_file = html_files[0] if html_files else None
    return json_file, html_file, screenshots_dir


@router.get("/{application_id}/dom_snapshot")
async def get_dom_snapshot(application_id: str):
    """
    Serves the raw HTML DOM snapshot captured during execution.
    """
    _, html_file, _ = _find_trace_files(application_id)
    if not html_file or not os.path.exists(html_file):
        return Response(content="<html><body><h3>DOM snapshot not found</h3></body></html>", media_type="text/html")
    
    with open(html_file, "r", encoding="utf-8") as f:
        content = f.read()
    return Response(content=content, media_type="text/html")


@router.get("/{application_id}/replay", response_class=HTMLResponse)
async def get_application_replay(application_id: str, request: Request):
    """
    Renders a premium visual timeline execution replay dashboard.
    """
    json_file, html_file, screenshots_dir = _find_trace_files(application_id)
    
    # Beautiful CSS and fallback layout if no telemetry exists
    if not json_file or not os.path.exists(json_file):
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>No Telemetry Found</title>
            <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
            <style>
                body {{
                    font-family: 'Outfit', sans-serif;
                    background: radial-gradient(circle at top, #1e293b, #0f172a);
                    color: #e2e8f0;
                    height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0;
                }}
                .card {{
                    background: rgba(30, 41, 59, 0.7);
                    backdrop-filter: blur(12px);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    padding: 40px;
                    border-radius: 16px;
                    text-align: center;
                    max-width: 450px;
                    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
                }}
                h2 {{ color: #f8fafc; margin-bottom: 12px; }}
                p {{ color: #94a3b8; font-weight: 300; line-height: 1.5; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h2>No Replay Telemetry Found</h2>
                <p>An execution replay has not been recorded for application <strong>{application_id}</strong> yet, or the trace data has been rotated.</p>
            </div>
        </body>
        </html>
        """)

    with open(json_file, "r", encoding="utf-8") as f:
        telemetry = json.load(f)

    # Encode screenshots to base64
    screenshots_encoded = []
    for ss in telemetry.get("screenshots", []):
        filename = ss.get("filename")
        if filename:
            ss_path = os.path.join(screenshots_dir, filename)
            if os.path.exists(ss_path):
                try:
                    with open(ss_path, "rb") as img_f:
                        encoded = base64.b64encode(img_f.read()).decode("utf-8")
                    screenshots_encoded.append({
                        "trigger": ss.get("trigger", "unknown"),
                        "timestamp": datetime.fromtimestamp(ss.get("timestamp", 0)).strftime("%H:%M:%S"),
                        "base64": f"data:image/png;base64,{encoded}"
                    })
                except Exception:
                    pass

    # Build steps list dynamically
    actions_html = ""
    for idx, act in enumerate(telemetry.get("actions", [])):
        status = act.get("status", "success")
        badge_class = "success-badge" if status == "success" else "failure-badge"
        indicator_icon = "✓" if status == "success" else "✗"
        
        sel_used = act.get("selector_used") or "None"
        sel_type = act.get("selector_type") or "None"
        duration = round(act.get("duration_ms", 0), 1)
        
        actions_html += f"""
        <div class="timeline-item" onclick="selectStep({idx}, '{sel_used}')" id="step-{idx}">
            <div class="step-status {badge_class}">{indicator_icon}</div>
            <div class="step-details">
                <div class="step-title">{act.get('action_name')}</div>
                <div class="step-meta">
                    <span>Duration: <strong>{duration} ms</strong></span>
                    <span>Type: <strong>{sel_type}</strong></span>
                </div>
                {f'<div class="step-selector">Selector: <code>{sel_used}</code></div>' if sel_used != 'None' else ''}
                {f'<div class="step-error">{act.get("error_context")}</div>' if act.get("error_context") else ''}
            </div>
        </div>
        """

    # System metrics HTML
    sys_metrics = telemetry.get("system_metrics", {})
    metrics_html = "".join([f"<li><span>{k}:</span><strong>{v}</strong></li>" for k, v in sys_metrics.items()])

    # Build screenshots gallery
    gallery_html = ""
    if not screenshots_encoded:
        gallery_html = "<div class='no-screenshots'>No screenshots were captured for this execution.</div>"
    else:
        for ss in screenshots_encoded:
            gallery_html += f"""
            <div class="gallery-item">
                <div class="gallery-title">{ss['trigger'].replace('_', ' ').title()} ({ss['timestamp']})</div>
                <img src="{ss['base64']}" alt="{ss['trigger']}">
            </div>
            """

    page_title = sys_metrics.get("page_title", "Job Board")
    target_url = sys_metrics.get("current_url") or telemetry.get("system_metrics", {}).get("current_url") or "Sandbox Form"
    status_label = "SUCCESS" if telemetry.get("success", True) else "FAILED"
    status_class = "status-success" if telemetry.get("success", True) else "status-failed"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Execution Replay - {page_title}</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg-primary: #0f172a;
                --bg-secondary: #1e293b;
                --border-color: rgba(255, 255, 255, 0.08);
                --text-main: #f8fafc;
                --text-sub: #94a3b8;
                --accent-blue: #3b82f6;
                --accent-green: #10b981;
                --accent-red: #ef4444;
            }}
            body {{
                font-family: 'Outfit', sans-serif;
                background-color: var(--bg-primary);
                color: var(--text-main);
                margin: 0;
                padding: 0;
                height: 100vh;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }}
            header {{
                background-color: var(--bg-secondary);
                border-bottom: 1px solid var(--border-color);
                padding: 15px 30px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                flex-shrink: 0;
            }}
            .logo-section h1 {{
                font-size: 20px;
                font-weight: 600;
                margin: 0;
                color: #f1f5f9;
            }}
            .logo-section p {{
                font-size: 12px;
                color: var(--text-sub);
                margin: 4px 0 0 0;
            }}
            .header-meta {{
                display: flex;
                gap: 20px;
                align-items: center;
            }}
            .status-badge {{
                padding: 6px 12px;
                border-radius: 9999px;
                font-size: 12px;
                font-weight: 600;
                letter-spacing: 0.05em;
            }}
            .status-success {{
                background-color: rgba(16, 185, 129, 0.15);
                color: var(--accent-green);
                border: 1px solid rgba(16, 185, 129, 0.3);
            }}
            .status-failed {{
                background-color: rgba(239, 68, 68, 0.15);
                color: var(--accent-red);
                border: 1px solid rgba(239, 68, 68, 0.3);
            }}
            .main-content {{
                display: flex;
                flex: 1;
                overflow: hidden;
            }}
            .sidebar {{
                width: 420px;
                background-color: var(--bg-secondary);
                border-right: 1px solid var(--border-color);
                display: flex;
                flex-direction: column;
                overflow-y: auto;
                flex-shrink: 0;
            }}
            .metadata-card {{
                padding: 20px;
                border-bottom: 1px solid var(--border-color);
            }}
            .metadata-card ul {{
                list-style: none;
                padding: 0;
                margin: 0;
            }}
            .metadata-card li {{
                display: flex;
                justify-content: space-between;
                font-size: 13px;
                margin-bottom: 10px;
            }}
            .metadata-card li span {{
                color: var(--text-sub);
            }}
            .timeline-section {{
                padding: 20px;
                flex: 1;
            }}
            .timeline-section h3 {{
                font-size: 14px;
                color: var(--text-sub);
                margin-top: 0;
                margin-bottom: 15px;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }}
            .timeline-item {{
                display: flex;
                gap: 15px;
                padding: 12px;
                border-radius: 8px;
                margin-bottom: 10px;
                cursor: pointer;
                border: 1px solid transparent;
                transition: all 0.2s;
            }}
            .timeline-item:hover {{
                background-color: rgba(255, 255, 255, 0.02);
                border-color: rgba(255, 255, 255, 0.05);
            }}
            .timeline-item.active-step {{
                background-color: rgba(59, 130, 246, 0.08);
                border-color: rgba(59, 130, 246, 0.2);
            }}
            .step-status {{
                width: 20px;
                height: 20px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 11px;
                font-weight: bold;
                flex-shrink: 0;
                margin-top: 2px;
            }}
            .success-badge {{
                background-color: rgba(16, 185, 129, 0.15);
                color: var(--accent-green);
            }}
            .failure-badge {{
                background-color: rgba(239, 68, 68, 0.15);
                color: var(--accent-red);
            }}
            .step-details {{
                flex: 1;
            }}
            .step-title {{
                font-size: 14px;
                font-weight: 500;
                margin-bottom: 4px;
            }}
            .step-meta {{
                font-size: 11px;
                color: var(--text-sub);
                display: flex;
                gap: 12px;
                margin-bottom: 4px;
            }}
            .step-selector {{
                font-size: 11px;
                color: var(--accent-blue);
                word-break: break-all;
                margin-top: 4px;
            }}
            .step-error {{
                font-size: 11px;
                color: var(--accent-red);
                margin-top: 4px;
                background-color: rgba(239, 68, 68, 0.05);
                padding: 6px;
                border-radius: 4px;
            }}
            .viewer-panel {{
                flex: 1;
                display: flex;
                flex-direction: column;
                background-color: #0b0f19;
            }}
            .tabs {{
                display: flex;
                background-color: var(--bg-secondary);
                border-bottom: 1px solid var(--border-color);
                padding: 0 20px;
            }}
            .tab-btn {{
                background: none;
                border: none;
                color: var(--text-sub);
                padding: 15px 20px;
                font-family: inherit;
                font-size: 13px;
                font-weight: 500;
                cursor: pointer;
                border-bottom: 2px solid transparent;
                transition: all 0.2s;
            }}
            .tab-btn:hover {{
                color: var(--text-main);
            }}
            .tab-btn.active {{
                color: var(--accent-blue);
                border-bottom-color: var(--accent-blue);
            }}
            .tab-content {{
                flex: 1;
                display: none;
                overflow: hidden;
            }}
            .tab-content.active {{
                display: flex;
                flex-direction: column;
            }}
            iframe {{
                border: none;
                width: 100%;
                height: 100%;
                background-color: white;
            }}
            .gallery-view {{
                padding: 30px;
                overflow-y: auto;
                display: flex;
                flex-direction: column;
                gap: 30px;
                align-items: center;
            }}
            .gallery-item {{
                background-color: var(--bg-secondary);
                border: 1px solid var(--border-color);
                border-radius: 12px;
                padding: 15px;
                max-width: 800px;
                width: 100%;
                box-shadow: 0 4px 6px rgba(0,0,0,0.2);
            }}
            .gallery-title {{
                font-size: 14px;
                font-weight: 500;
                margin-bottom: 10px;
                color: var(--text-sub);
            }}
            .gallery-item img {{
                width: 100%;
                border-radius: 6px;
                border: 1px solid rgba(255,255,255,0.05);
            }}
            .no-screenshots {{
                color: var(--text-sub);
                font-size: 14px;
                margin-top: 40px;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <header>
            <div class="logo-section">
                <h1>Execution Replay Viewer</h1>
                <p>Telemetry, DOM Snapshots, and Screenshot logs for form submission</p>
            </div>
            <div class="header-meta">
                <span class="status-badge {status_class}">{status_label}</span>
            </div>
        </header>
        <div class="main-content">
            <div class="sidebar">
                <div class="metadata-card">
                    <ul>
                        <li><span>Application ID:</span><strong>{application_id[:8]}...</strong></li>
                        <li><span>Target URL:</span><strong style="word-break:break-all;text-align:right;max-width:240px;">{target_url}</strong></li>
                        <li><span>Duration:</span><strong>{round(telemetry.get('total_duration_ms', 0) / 1000, 2)}s</strong></li>
                        <li><span>Fallback Selectors:</span><strong>{telemetry.get('fallback_selectors_count', 0)}</strong></li>
                        {metrics_html}
                    </ul>
                </div>
                <div class="timeline-section">
                    <h3>Execution Steps</h3>
                    {actions_html}
                </div>
            </div>
            <div class="viewer-panel">
                <div class="tabs">
                    <button class="tab-btn active" onclick="switchTab('snapshot')">DOM Snapshot</button>
                    <button class="tab-btn" onclick="switchTab('screenshots')">Screenshots</button>
                </div>
                <div id="tab-snapshot" class="tab-content active">
                    <iframe id="dom-snapshot-iframe" src="/api/v1/applications/{application_id}/dom_snapshot"></iframe>
                </div>
                <div id="tab-screenshots" class="tab-content">
                    <div class="gallery-view">
                        {gallery_html}
                    </div>
                </div>
            </div>
        </div>
        <script>
            function switchTab(tabName) {{
                document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
                
                if (tabName === 'snapshot') {{
                    document.querySelectorAll('.tab-btn')[0].classList.add('active');
                    document.getElementById('tab-snapshot').classList.add('active');
                }} else {{
                    document.querySelectorAll('.tab-btn')[1].classList.add('active');
                    document.getElementById('tab-screenshots').classList.add('active');
                }}
            }}

            function selectStep(index, selector) {{
                document.querySelectorAll('.timeline-item').forEach(item => item.classList.remove('active-step'));
                document.getElementById('step-' + index).classList.add('active-step');
                
                // Highlight inside iframe
                highlightIframeElement(selector);
            }}

            function highlightIframeElement(selector) {{
                const iframe = document.getElementById('dom-snapshot-iframe');
                if (!iframe || !iframe.contentWindow) return;
                const doc = iframe.contentDocument || iframe.contentWindow.document;
                if (!doc) return;
                
                // Remove previous highlights
                doc.querySelectorAll('.antigravity-highlight').forEach(el => {{
                    el.classList.remove('antigravity-highlight');
                    el.style.outline = '';
                    el.style.backgroundColor = '';
                }});
                
                if (!selector || selector === 'None') return;
                
                let element = null;
                if (selector.startsWith('css:')) {{
                    element = doc.querySelector(selector.substring(4));
                }} else if (selector.startsWith('xpath:')) {{
                    const xpathResult = doc.evaluate(selector.substring(6), doc, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                    element = xpathResult.singleNodeValue;
                }} else if (selector.startsWith('attribute:')) {{
                    const val = selector.split(':')[1];
                    element = doc.querySelector(`[id*="${{val}}"], [name*="${{val}}"], [placeholder*="${{val}}"]`);
                }} else {{
                    try {{
                        element = doc.querySelector(selector);
                    }} catch(e) {{
                        try {{
                            const xpathResult = doc.evaluate(selector, doc, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                            element = xpathResult.singleNodeValue;
                        }} catch(e2) {{}}
                    }}
                }}
                
                if (element) {{
                    element.classList.add('antigravity-highlight');
                    element.style.outline = '3px dashed #3b82f6';
                    element.style.outlineOffset = '2px';
                    element.style.backgroundColor = 'rgba(59, 130, 246, 0.15)';
                    element.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                }}
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

