# app/api/v1/audit.py
"""Audit API router — handles standalone /audit endpoints expected by validation."""

import uuid
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.rbac import AuditEvent
from app.models.schemas import SuccessResponse


router = APIRouter(prefix="/audit", tags=["Audit"])


def _make_meta(request: Request) -> dict:
    """Build standard response meta from request context."""
    return {
        "request_id": getattr(request.state, "trace_id", str(uuid.uuid4())),
        "timestamp": datetime.now(UTC),
    }


@router.get("", response_model=SuccessResponse)
async def get_audit_events(
    request: Request,
    user_id: uuid.UUID = Query(..., description="Filter by user ID"),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
) -> SuccessResponse:
    """Query audit events filtered by user_id."""
    stmt = select(AuditEvent).where(
        AuditEvent.actor_id == user_id
    ).order_by(AuditEvent.timestamp.desc()).limit(limit)

    res = await db.execute(stmt)
    events = res.scalars().all()

    events_list = []
    for e in events:
        events_list.append({
            "id": str(e.id),
            "actor_id": str(e.actor_id) if e.actor_id else None,
            "action": e.action,
            "resource_type": e.resource_type,
            "resource_id": str(e.resource_id) if e.resource_id else None,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "ip_address": e.ip_address,
            "reason": e.reason,
            "metadata": e.metadata_json
        })

    return SuccessResponse(data={"events": events_list}, meta=_make_meta(request))
