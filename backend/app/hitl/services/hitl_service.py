import uuid
import structlog
from datetime import datetime, UTC
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Application, ApprovalRequest, ApplicationStatusHistory, ApplicationLog
from app.models.schemas import ApplicationStatus
from app.integrations.adapters.registry import AdapterRegistry
from app.core.exceptions import ForbiddenError

logger = structlog.get_logger(__name__)

class HitlService:
    """
    Core business logic and gatekeeper for the Human-in-the-Loop (HITL) Execution Layer.
    Enforces that operator oversight respects and extends governance controls.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_queues(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Retrieves and categorizes applications into distinct operator queues.
        """
        # Fetch all non-deleted applications
        stmt = select(Application).where(Application.deleted_at.is_(None)).order_by(desc(Application.updated_at))
        res = await self.db.execute(stmt)
        apps = res.scalars().all()

        queues = {
            "awaiting_approval": [],
            "selector_mismatch": [],
            "missing_assets": [],
            "failed_execution": [],
            "replay_review": [],
            "retry_approval": []
        }

        for app in apps:
            app_id_str = str(app.application_id)
            meta = app.metadata_ or {}
            status = app.status

            # Calculate missing fields or selector mismatches
            has_selector_mismatch = False
            missing_fields = []
            
            if app.application_url:
                try:
                    adapter = AdapterRegistry.get_adapter(app.application_url)
                    if adapter and adapter.profile_name:
                        required = adapter.profile.get("required_fields", [])
                        for req in required:
                            if not adapter.get_selector(req):
                                has_selector_mismatch = True
                                missing_fields.append(req)
                except Exception:
                    has_selector_mismatch = True

            has_missing_assets = not app.resume_version_id

            # Classify into queues
            # 1. Selector Mismatch Queue
            if has_selector_mismatch:
                queues["selector_mismatch"].append(self._serialize_app_for_queue(app, f"Missing selectors: {', '.join(missing_fields)}"))

            # 2. Missing Assets Queue
            if has_missing_assets or status == ApplicationStatus.ASSET_ERROR.value:
                queues["missing_assets"].append(self._serialize_app_for_queue(app, "Missing resume/cover letter asset"))

            # 3. Retry Approval Queue
            if (app.retry_count or 0) > 0 and status in (ApplicationStatus.QUEUED.value, ApplicationStatus.PENDING_APPROVAL.value):
                queues["retry_approval"].append(self._serialize_app_for_queue(app, f"Retry attempt #{app.retry_count}"))

            # 4. Failed Execution Queue
            if status == ApplicationStatus.FAILED.value:
                queues["failed_execution"].append(self._serialize_app_for_queue(app, "Execution failed"))

            # 5. Replay Required Review Queue
            if status == ApplicationStatus.APPLIED.value:
                queues["replay_review"].append(self._serialize_app_for_queue(app, "Successful submission replay"))
            elif status == ApplicationStatus.FAILED.value:
                queues["replay_review"].append(self._serialize_app_for_queue(app, "Failed submission diagnostics"))

            # 6. Awaiting Approval Queue (Primary manual approval state)
            if status == ApplicationStatus.PENDING_APPROVAL.value:
                # Get the pending token if it exists
                stmt_req = select(ApprovalRequest).where(
                    ApprovalRequest.application_id == app.application_id,
                    ApprovalRequest.decision.is_(None)
                )
                res_req = await self.db.execute(stmt_req)
                req = res_req.scalar_one_or_none()
                token = req.approval_token if req else None
                reason = req.decision_reason if req else "Awaiting approval review"
                queues["awaiting_approval"].append(self._serialize_app_for_queue(app, reason, token))

        return queues

    async def get_app_diff(self, application_id: uuid.UUID) -> Dict[str, Any]:
        """
        Generates comparison differences for form inputs and unmapped fields.
        """
        stmt = select(Application).where(Application.application_id == application_id)
        res = await self.db.execute(stmt)
        app = res.scalar_one_or_none()
        if not app:
            raise ValueError("Application not found.")

        meta = app.metadata_ or {}
        field_data = meta.get("field_data") or {}
        
        profile_fields = {}
        required_fields = []
        unmapped_fields = []
        mapped_fields = {}

        if app.application_url:
            try:
                adapter = AdapterRegistry.get_adapter(app.application_url)
                if adapter and adapter.profile:
                    profile_fields = adapter.profile.get("selectors", {})
                    required_fields = adapter.profile.get("required_fields", [])
                    for fkey in required_fields:
                        if not adapter.get_selector(fkey):
                            unmapped_fields.append(fkey)
                        else:
                            mapped_fields[fkey] = field_data.get(fkey, "[Not Provided]")
            except Exception:
                pass

        return {
            "application_id": str(application_id),
            "company_name": app.company_name,
            "role_title": app.role_title,
            "application_url": app.application_url,
            "priority": meta.get("priority", "normal"),
            "field_data": field_data,
            "required_fields": required_fields,
            "mapped_fields": mapped_fields,
            "unmapped_fields": unmapped_fields,
            "has_resume": app.resume_version_id is not None,
            "has_cover_letter": app.cover_letter_version_id is not None
        }

    async def resolve_with_checklist(
        self,
        token: str,
        decision: str,  # 'approved' | 'rejected'
        reason: str | None,
        checklist: Dict[str, bool],
        operator_id: str = "operator"
    ) -> Application:
        """
        Resolves an approval request requiring checklist validation.
        Persists checklist state permanently in the application's metadata.
        """
        # Retrieve Approval Request
        stmt = select(ApprovalRequest).where(ApprovalRequest.approval_token == token)
        res = await self.db.execute(stmt)
        req = res.scalar_one_or_none()
        if not req:
            raise ValueError("Approval request not found.")

        # Retrieve Application
        app_stmt = select(Application).where(Application.application_id == req.application_id)
        app_res = await self.db.execute(app_stmt)
        app = app_res.scalar_one()

        # Enforce checklist validation on approval
        if decision == "approved":
            required_checks = ["domain_verified", "resume_verified", "fields_verified"]
            for check in required_checks:
                if not checklist.get(check):
                    raise ForbiddenError(f"Cannot approve application: Checkpoint '{check}' must be verified.")

        # Persist checklist state in application metadata_
        app.metadata_["operator_checklist"] = {
            "checklist": checklist,
            "operator_id": operator_id,
            "resolved_at": datetime.now(UTC).isoformat()
        }

        # Resolve via ApprovalGate schema
        req.decision = decision
        req.decided_by = operator_id
        req.decision_reason = reason
        req.resolved_at = datetime.now(UTC)

        if decision == "approved":
            app.status = ApplicationStatus.QUEUED.value
        else:
            app.status = ApplicationStatus.FAILED.value

        # Log transition
        history = ApplicationStatusHistory(
            application_id=app.application_id,
            from_status=ApplicationStatus.PENDING_APPROVAL.value,
            to_status=app.status,
            reason=f"Operator resolution: {reason}",
            changed_by=operator_id
        )
        self.db.add(history)
        
        # Add operator audit log
        audit_log = ApplicationLog(
            application_id=app.application_id,
            level="INFO",
            event="hitl.approval_resolved",
            message=f"Operator '{operator_id}' resolved approval with decision '{decision}'",
            context={
                "operator_id": operator_id,
                "checklist": checklist,
                "reason": reason
            }
        )
        self.db.add(audit_log)

        await self.db.flush()
        return app

    async def cancel_execution(self, application_id: uuid.UUID, reason: str, operator_id: str = "operator") -> Application:
        """
        Cancels a queued or processing execution task, freeing concurrent slots.
        """
        stmt = select(Application).where(Application.application_id == application_id)
        res = await self.db.execute(stmt)
        app = res.scalar_one_or_none()
        if not app:
            raise ValueError("Application not found.")

        old_status = app.status
        if old_status not in (ApplicationStatus.QUEUED.value, ApplicationStatus.PROCESSING.value, ApplicationStatus.PENDING_APPROVAL.value):
            raise ForbiddenError(f"Cannot cancel application in terminal state: {old_status}")

        app.status = ApplicationStatus.FAILED.value

        # Status history
        history = ApplicationStatusHistory(
            application_id=app.application_id,
            from_status=old_status,
            to_status=ApplicationStatus.FAILED.value,
            reason=f"Canceled by operator: {reason}",
            changed_by=operator_id
        )
        self.db.add(history)

        # Audit log
        audit_log = ApplicationLog(
            application_id=app.application_id,
            level="WARN",
            event="hitl.execution_canceled",
            message=f"Execution canceled by operator '{operator_id}'",
            context={"reason": reason}
        )
        self.db.add(audit_log)

        await self.db.flush()
        return app

    async def escalate_application(self, application_id: uuid.UUID, reason: str, operator_id: str = "operator") -> Application:
        """
        Escalates a failed/asset_error application back to PENDING_APPROVAL status.
        """
        stmt = select(Application).where(Application.application_id == application_id)
        res = await self.db.execute(stmt)
        app = res.scalar_one_or_none()
        if not app:
            raise ValueError("Application not found.")

        old_status = app.status
        if old_status not in (ApplicationStatus.FAILED.value, ApplicationStatus.ASSET_ERROR.value):
            raise ForbiddenError(f"Cannot escalate application in status: {old_status}")

        app.status = ApplicationStatus.PENDING_APPROVAL.value
        
        # Create a new Approval Request
        token = uuid.uuid4().hex
        expires = datetime.now(UTC) + timedelta(hours=24)
        approval_request = ApprovalRequest(
            application_id=app.application_id,
            user_id=app.user_id,
            expires_at=expires,
            decision=None,
            approval_token=token,
            decision_reason=f"Escalation: {reason}"
        )
        self.db.add(approval_request)

        # Status history
        history = ApplicationStatusHistory(
            application_id=app.application_id,
            from_status=old_status,
            to_status=ApplicationStatus.PENDING_APPROVAL.value,
            reason=f"Escalated by operator: {reason}",
            changed_by=operator_id
        )
        self.db.add(history)

        # Audit log
        audit_log = ApplicationLog(
            application_id=app.application_id,
            level="INFO",
            event="hitl.escalated",
            message=f"Application escalated back to approvals by '{operator_id}'",
            context={"reason": reason, "token": token}
        )
        self.db.add(audit_log)

        await self.db.flush()
        return app

    async def get_audit_logs(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Retrieves operator action history and resolutions.
        """
        stmt = select(ApprovalRequest).where(ApprovalRequest.decision.is_not(None)).order_by(desc(ApprovalRequest.resolved_at)).limit(limit).offset(offset)
        res = await self.db.execute(stmt)
        reqs = res.scalars().all()

        logs = []
        for req in reqs:
            # Fetch application details
            app_stmt = select(Application).where(Application.application_id == req.application_id)
            app_res = await self.db.execute(app_stmt)
            app = app_res.scalar_one()

            logs.append({
                "request_id": str(req.request_id),
                "application_id": str(req.application_id),
                "company_name": app.company_name,
                "role_title": app.role_title,
                "resolved_at": req.resolved_at.isoformat() if req.resolved_at else None,
                "decision": req.decision,
                "decision_reason": req.decision_reason,
                "decided_by": req.decided_by
            })

        return logs

    def _serialize_app_for_queue(self, app: Application, reason: str, token: str | None = None) -> Dict[str, Any]:
        meta = app.metadata_ or {}
        return {
            "application_id": str(app.application_id),
            "company_name": app.company_name,
            "role_title": app.role_title,
            "priority": meta.get("priority", "normal"),
            "status": app.status,
            "updated_at": app.updated_at.isoformat(),
            "reason": reason,
            "approval_token": token
        }

from datetime import timedelta
