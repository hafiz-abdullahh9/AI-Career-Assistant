import os
import time
import json
import base64
import pytest
import uuid
from datetime import datetime, UTC, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.testclient import TestClient
from selenium.webdriver.common.by import By

from app.models.orm import Application, ApprovalRequest
from app.models.schemas import ApplicationStatus
from app.core.exceptions import ForbiddenError
from app.browser.sessions.session_manager import BrowserManager
from app.browser.observability.tracing.trace_tracker import TraceManager
from app.browser.schemas.browser_schemas import AutomationOutcome

# Components under test
from app.integrations.adapters.registry import AdapterRegistry
from app.integrations.adapters.greenhouse import GreenhouseAdapter
from app.integrations.adapters.lever import LeverAdapter
from app.integrations.adapters.generic import GenericAdapter
from app.integrations.services.integration_service import IntegrationService
from app.api.v1.applications import router
from app.main import app


# --- STEP 1: Adapter Determinism / Selection Tests ---

def test_adapter_registry_resolves_correct_adapter():
    # Platform mappings
    gh_url = "https://boards.greenhouse.io/google/jobs/12345"
    lever_url = "https://jobs.lever.co/netflix/67890"
    generic_url = "https://example-employer.com/apply"

    # Registry lookup
    gh_adapter = AdapterRegistry.get_adapter(gh_url)
    lever_adapter = AdapterRegistry.get_adapter(lever_url)
    generic_adapter = AdapterRegistry.get_adapter(generic_url)

    # Class assertions
    assert isinstance(gh_adapter, GreenhouseAdapter)
    assert isinstance(lever_adapter, LeverAdapter)
    assert isinstance(generic_adapter, GenericAdapter)

    # Support domain configs loading check
    assert "greenhouse.io" in gh_adapter.supported_domains
    assert "lever.co" in lever_adapter.supported_domains
    assert not generic_adapter.supported_domains


def test_adapter_registry_resolves_sandbox_paths():
    gh_sandbox = "file:///e:/Antigravity%20Projects/Hackthon/Member_04_Application_Automation/tests/resources/greenhouse_form.html"
    lever_sandbox = "file:///e:/Antigravity%20Projects/Hackthon/Member_04_Application_Automation/tests/resources/lever_form.html"

    gh_adapter = AdapterRegistry.get_adapter(gh_sandbox)
    lever_adapter = AdapterRegistry.get_adapter(lever_sandbox)

    assert isinstance(gh_adapter, GreenhouseAdapter)
    assert isinstance(lever_adapter, LeverAdapter)


# --- STEP 2: Greenhouse and Lever Sandbox Automation Tests ---

@pytest.mark.asyncio
async def test_greenhouse_adapter_form_filling_success():
    manager = BrowserManager(headless=True)
    driver = manager.start_session()
    
    sandbox_path = os.path.abspath("tests/resources/greenhouse_form.html")
    sandbox_url = f"file:///{sandbox_path.replace(os.sep, '/')}"

    adapter = GreenhouseAdapter()
    trace_manager = TraceManager(session_id="test_sess_gh", task_id="test_task_gh")

    field_data = {
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane.doe@example.com",
        "phone": "555-0199"
    }

    # Create dummy file to test resume upload
    with tempfile_named("dummy_resume.pdf") as resume_path:
        file_uploads = {"resume": resume_path}

        try:
            driver.get(sandbox_url)
            adapter.fill_fields(driver, field_data, trace_manager)
            adapter.upload_files(driver, file_uploads, trace_manager)
            adapter.submit_form(driver, trace_manager)
            
            success = adapter.verify_success(driver, trace_manager)
            assert success is True

            # Check confirmation code extraction
            conf_id = IntegrationService(None, None)._extract_confirmation_id(driver, adapter.profile)
            assert conf_id == "CONF-GH123456"

        finally:
            manager.close_session()


@pytest.mark.asyncio
async def test_lever_adapter_form_filling_success():
    manager = BrowserManager(headless=True)
    driver = manager.start_session()
    
    sandbox_path = os.path.abspath("tests/resources/lever_form.html")
    sandbox_url = f"file:///{sandbox_path.replace(os.sep, '/')}"

    adapter = LeverAdapter()
    trace_manager = TraceManager(session_id="test_sess_lever", task_id="test_task_lever")

    # Name is combined from first/last name
    field_data = {
        "first_name": "John",
        "last_name": "Smith",
        "email": "john.smith@example.com",
        "phone": "555-0200"
    }

    with tempfile_named("dummy_cv.pdf") as cv_path:
        file_uploads = {"resume": cv_path}

        try:
            driver.get(sandbox_url)
            adapter.fill_fields(driver, field_data, trace_manager)
            adapter.upload_files(driver, file_uploads, trace_manager)
            adapter.submit_form(driver, trace_manager)
            
            success = adapter.verify_success(driver, trace_manager)
            assert success is True

            conf_id = IntegrationService(None, None)._extract_confirmation_id(driver, adapter.profile)
            assert conf_id == "CONF-LEVER9988"

        finally:
            manager.close_session()


# --- STEP 3: Deny-by-Default Policy Tests ---

@pytest.mark.asyncio
async def test_integration_service_blocks_unauthorized_domain():
    mock_db = AsyncMock(spec=AsyncSession)
    mock_redis = AsyncMock()

    service = IntegrationService(mock_db, mock_redis)
    app_record = Application(
        application_id=uuid.uuid4(),
        application_url="https://unauthorized-site.com/apply",
        metadata_={"manual_approval_required": False}
    )

    with pytest.raises(ForbiddenError) as exc_info:
        await service.execute_integration(app_record, "sess_123", "task_123")
    
    assert "not allowlisted" in str(exc_info.value)


@pytest.mark.asyncio
async def test_integration_service_blocks_missing_approval():
    mock_db = AsyncMock(spec=AsyncSession)
    mock_redis = AsyncMock()

    # Stub DB execution to return no approved ApprovalRequest
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res

    service = IntegrationService(mock_db, mock_redis)
    app_record = Application(
        application_id=uuid.uuid4(),
        application_url="file:///tests/resources/greenhouse_form.html",
        metadata_={"manual_approval_required": True}
    )

    with pytest.raises(ForbiddenError) as exc_info:
        await service.execute_integration(app_record, "sess_123", "task_123")
    
    assert "Manual approval is required" in str(exc_info.value)


@pytest.mark.asyncio
async def test_integration_service_blocks_missing_telemetry():
    mock_db = AsyncMock(spec=AsyncSession)
    mock_redis = AsyncMock()

    service = IntegrationService(mock_db, mock_redis)
    app_record = Application(
        application_id=uuid.uuid4(),
        application_url="file:///tests/resources/greenhouse_form.html",
        metadata_={"manual_approval_required": False}
    )

    # Missing session_id/task_id
    with pytest.raises(ValueError) as exc_info:
        await service.execute_integration(app_record, "", "")
    
    assert "Replay telemetry context" in str(exc_info.value)


# --- STEP 4: Execution Replay Viewer Tests ---

def test_replay_viewer_endpoints_render(monkeypatch):
    client = TestClient(app)
    
    # 1. Test fallback when no trace files exist
    non_existent_id = str(uuid.uuid4())
    res = client.get(f"/api/v1/applications/{non_existent_id}/replay")
    assert res.status_code == 200
    assert "No Replay Telemetry Found" in res.text

    # 2. Mock trace files and test valid replay render
    app_id = str(uuid.uuid4())
    mock_json = {
        "session_id": f"sess_{app_id[:8]}",
        "task_id": app_id,
        "success": True,
        "total_duration_ms": 1500,
        "fallback_selectors_count": 0,
        "system_metrics": {
            "page_title": "Mock Greenhouse Job Page",
            "current_url": "file:///mock_greenhouse.html"
        },
        "actions": [
            {
                "action_name": "fill_field",
                "status": "success",
                "duration_ms": 250,
                "selector_used": "css:#first_name",
                "selector_type": "profile"
            }
        ],
        "screenshots": []
    }

    # Setup directories
    artifacts_dir = os.path.abspath("tests/storage_test")
    os.makedirs(os.path.join(artifacts_dir, "traces"), exist_ok=True)
    os.makedirs(os.path.join(artifacts_dir, "screenshots"), exist_ok=True)

    monkeypatch.setenv("ANTIGRAVITY_ARTIFACTS_DIR", artifacts_dir)

    json_path = os.path.join(artifacts_dir, "traces", f"trace_sess_{app_id[:8]}_12345.json")
    html_path = os.path.join(artifacts_dir, "traces", f"trace_sess_{app_id[:8]}_12345.html")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(mock_json, f)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write("<html><body>Mock page source</body></html>")

    try:
        # Request dom_snapshot
        dom_res = client.get(f"/api/v1/applications/{app_id}/dom_snapshot")
        assert dom_res.status_code == 200
        assert "Mock page source" in dom_res.text

        # Request replay
        rep_res = client.get(f"/api/v1/applications/{app_id}/replay")
        assert rep_res.status_code == 200
        assert "Execution Replay Viewer" in rep_res.text
        assert "Mock Greenhouse Job Page" in rep_res.text
    finally:
        # Cleanup mock files
        if os.path.exists(json_path):
            os.remove(json_path)
        if os.path.exists(html_path):
            os.remove(html_path)
        try:
            os.rmdir(os.path.join(artifacts_dir, "traces"))
            os.rmdir(os.path.join(artifacts_dir, "screenshots"))
            os.rmdir(artifacts_dir)
        except OSError:
            pass


# --- Helper Context Manager for temp file ---

import tempfile
from contextlib import contextmanager

@contextmanager
def tempfile_named(name: str):
    temp_dir = tempfile.mkdtemp()
    filepath = os.path.join(temp_dir, name)
    # Write empty pdf header so it passes type validation
    with open(filepath, "wb") as f:
        f.write(b"%PDF-1.4 mock pdf contents")
    try:
        yield filepath
    finally:
        try:
            os.remove(filepath)
            os.rmdir(temp_dir)
        except OSError:
            pass
