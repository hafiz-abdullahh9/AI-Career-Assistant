import os
import uuid
import pytest
from datetime import datetime, UTC, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.testclient import TestClient

from app.models.orm import Application, ApprovalRequest, ApplicationStatusHistory, ApplicationLog
from app.models.schemas import ApplicationStatus
from app.core.exceptions import ForbiddenError
from app.hitl.services.hitl_service import HitlService
from app.main import app


# --- Helper to create a standard mock session context ---

@pytest.fixture
def mock_db():
    return AsyncMock(spec=AsyncSession)


# --- Tests for HITL Queues and Classifications ---

@pytest.mark.asyncio
async def test_hitl_service_categorizes_queues(mock_db):
    # Setup mock data for applications
    app_pending = Application(
        application_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        company_name="PendingCorp",
        role_title="Software Engineer",
        application_url="file:///tests/resources/greenhouse_form.html",
        method="web_form",
        status=ApplicationStatus.PENDING_APPROVAL.value,
        resume_version_id=uuid.uuid4(),
        updated_at=datetime.now(UTC)
    )

    app_missing = Application(
        application_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        company_name="Assetcorp",
        role_title="Product Manager",
        application_url="file:///tests/resources/greenhouse_form.html",
        method="web_form",
        status=ApplicationStatus.QUEUED.value,
        resume_version_id=None, # Missing resume asset
        updated_at=datetime.now(UTC)
    )

    app_failed = Application(
        application_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        company_name="FailCorp",
        role_title="Designer",
        application_url="file:///tests/resources/greenhouse_form.html",
        method="web_form",
        status=ApplicationStatus.FAILED.value,
        resume_version_id=uuid.uuid4(),
        updated_at=datetime.now(UTC)
    )

    # Stub DB execution to return these 3 applications
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [app_pending, app_missing, app_failed]
    mock_db.execute.return_value = mock_res

    # Mock ApprovalRequest lookup for PENDING_APPROVAL app
    mock_req_res = MagicMock()
    mock_req = ApprovalRequest(
        application_id=app_pending.application_id,
        approval_token="pending_token_123",
        decision_reason="Policy trigger"
    )
    mock_req_res.scalar_one_or_none.return_value = mock_req
    
    # We call db.execute twice: first for applications, second for the approval request
    mock_db.execute.side_effect = [mock_res, mock_req_res]

    service = HitlService(mock_db)
    queues = await service.get_queues()

    assert len(queues["awaiting_approval"]) == 1
    assert queues["awaiting_approval"][0]["company_name"] == "PendingCorp"
    assert queues["awaiting_approval"][0]["approval_token"] == "pending_token_123"

    assert len(queues["missing_assets"]) == 1
    assert queues["missing_assets"][0]["company_name"] == "Assetcorp"

    assert len(queues["failed_execution"]) == 1
    assert queues["failed_execution"][0]["company_name"] == "FailCorp"


# --- Tests for Checklist Validation & Decision Resolution ---

@pytest.mark.asyncio
async def test_resolve_approval_with_complete_checklist(mock_db):
    app_id = uuid.uuid4()
    app_record = Application(
        application_id=app_id,
        user_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        company_name="VerifiedCorp",
        role_title="Staff Developer",
        status=ApplicationStatus.PENDING_APPROVAL.value,
        metadata_={}
    )

    req_record = ApprovalRequest(
        application_id=app_id,
        approval_token="tok_checklist_99",
        decision=None
    )

    # Mock DB select queries
    mock_req_res = MagicMock()
    mock_req_res.scalar_one_or_none.return_value = req_record
    mock_app_res = MagicMock()
    mock_app_res.scalar_one.return_value = app_record
    
    mock_db.execute.side_effect = [mock_req_res, mock_app_res]

    service = HitlService(mock_db)
    
    checklist = {
        "domain_verified": True,
        "resume_verified": True,
        "fields_verified": True
    }

    resolved_app = await service.resolve_with_checklist(
        token="tok_checklist_99",
        decision="approved",
        reason="Checks verified by operator",
        checklist=checklist,
        operator_id="admin_op"
    )

    assert resolved_app.status == ApplicationStatus.QUEUED.value
    assert req_record.decision == "approved"
    assert req_record.decided_by == "admin_op"
    assert "operator_checklist" in resolved_app.metadata_
    assert resolved_app.metadata_["operator_checklist"]["checklist"]["domain_verified"] is True


@pytest.mark.asyncio
async def test_resolve_approval_blocks_incomplete_checklist(mock_db):
    app_id = uuid.uuid4()
    app_record = Application(
        application_id=app_id,
        user_id=uuid.uuid4(),
        status=ApplicationStatus.PENDING_APPROVAL.value,
        metadata_={}
    )
    req_record = ApprovalRequest(
        application_id=app_id,
        approval_token="tok_checklist_fail",
        decision=None
    )

    mock_req_res = MagicMock()
    mock_req_res.scalar_one_or_none.return_value = req_record
    mock_app_res = MagicMock()
    mock_app_res.scalar_one.return_value = app_record
    mock_db.execute.side_effect = [mock_req_res, mock_app_res]

    service = HitlService(mock_db)
    
    # Incomplete checklists (fields_verified is False)
    checklist = {
        "domain_verified": True,
        "resume_verified": True,
        "fields_verified": False
    }

    with pytest.raises(ForbiddenError) as exc_info:
        await service.resolve_with_checklist(
            token="tok_checklist_fail",
            decision="approved",
            reason="Operator skipped fields verification",
            checklist=checklist
        )
    
    assert "Checkpoint 'fields_verified' must be verified" in str(exc_info.value)


# --- Tests for Execution Rollback & Cancellation ---

@pytest.mark.asyncio
async def test_cancel_execution_transitions_and_audits(mock_db):
    app_id = uuid.uuid4()
    app_record = Application(
        application_id=app_id,
        company_name="QueuedCorp",
        status=ApplicationStatus.QUEUED.value
    )

    mock_app_res = MagicMock()
    mock_app_res.scalar_one_or_none.return_value = app_record
    mock_db.execute.return_value = mock_app_res

    service = HitlService(mock_db)
    canceled_app = await service.cancel_execution(app_id, "Operator rollback test", "operator_bob")

    assert canceled_app.status == ApplicationStatus.FAILED.value
    mock_db.add.assert_any_call(
        # We assert that the status history record is stored
        pytest.approx_history_record(ApplicationStatusHistory, to_status="failed", changed_by="operator_bob")
    )


# --- Tests for Escalation Workflows ---

@pytest.mark.asyncio
async def test_escalate_failed_application_requeues(mock_db):
    app_id = uuid.uuid4()
    app_record = Application(
        application_id=app_id,
        user_id=uuid.uuid4(),
        company_name="FailedCorp",
        status=ApplicationStatus.FAILED.value
    )

    mock_app_res = MagicMock()
    mock_app_res.scalar_one_or_none.return_value = app_record
    mock_db.execute.return_value = mock_app_res

    service = HitlService(mock_db)
    escalated_app = await service.escalate_application(app_id, "Escalating for review", "operator_ann")

    assert escalated_app.status == ApplicationStatus.PENDING_APPROVAL.value
    mock_db.add.assert_any_call(
        # Check that approval request is added to DB
        pytest.approx_approval_request(ApprovalRequest, application_id=app_id)
    )


# --- REST API Endpoint Coverage ---

def test_hitl_endpoints_render():
    client = TestClient(app)
    
    # 1. Test /dashboard page rendering
    res = client.get("/api/v1/applications/approvals/dashboard")
    assert res.status_code == 200
    assert "HITL Control Center" in res.text
    assert "OPERATOR ACTIVE" in res.text


# --- Pytest Matcher Helpers for SQLAlchemy Objects ---

class pytest_approx_history_record:
    def __init__(self, cls, to_status, changed_by):
        self.cls = cls
        self.to_status = to_status
        self.changed_by = changed_by

    def __eq__(self, other):
        return (
            isinstance(other, self.cls) and
            other.to_status == self.to_status and
            other.changed_by == self.changed_by
        )

pytest.approx_history_record = pytest_approx_history_record


class pytest_approx_approval_request:
    def __init__(self, cls, application_id):
        self.cls = cls
        self.application_id = application_id

    def __eq__(self, other):
        return (
            isinstance(other, self.cls) and
            other.application_id == self.application_id
        )

pytest.approx_approval_request = pytest_approx_approval_request
