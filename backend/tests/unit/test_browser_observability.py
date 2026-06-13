import os
import time
import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException

from app.browser.sessions.session_manager import BrowserManager
from app.browser.services.browser_service import FormAutomationService
from app.browser.observability.screenshots.screenshot_store import ScreenshotStore
from app.browser.observability.tracing.trace_tracker import TraceManager, ActionContext
from app.browser.observability.watchdogs.resource_watchdog import BrowserResourceWatchdog

# --- Screenshot Store Unit Tests ---

def test_screenshot_store_capture_and_rotation(tmp_path):
    # Setup screenshot store with max 2 limit for rotation testing
    store = ScreenshotStore(base_dir=str(tmp_path), max_screenshots=2)
    
    mock_driver = MagicMock()
    def save_screenshot_side_effect(path):
        with open(path, "wb") as f:
            f.write(b"mock screenshot")
    mock_driver.save_screenshot.side_effect = save_screenshot_side_effect
    
    # Capture 1
    path1 = store.capture(mock_driver, "sess_1", "step_1")
    assert path1 is not None
    assert os.path.exists(path1)
    assert len(store.captured_logs) == 1
    assert store.captured_logs[0]["trigger"] == "step_1"
    
    # Capture 2
    path2 = store.capture(mock_driver, "sess_1", "step_2")
    assert path2 is not None
    assert os.path.exists(path2)
    assert len(store.captured_logs) == 2
    
    # Capture 3 (triggers rotation: oldest is popped and deleted)
    path3 = store.capture(mock_driver, "sess_1", "step_3")
    assert path3 is not None
    assert os.path.exists(path3)
    assert len(store.captured_logs) == 2
    # Verify first captured log was rotated out and its file deleted
    assert store.captured_logs[0]["trigger"] == "step_2"
    assert store.captured_logs[1]["trigger"] == "step_3"
    assert not os.path.exists(path1)

# --- Trace Tracker Unit Tests ---

def test_trace_manager_tracking_and_hooks(tmp_path):
    manager = TraceManager(session_id="test_sess", task_id="task_123", base_dir=str(tmp_path))
    
    # Setup action context hooks
    events = []
    def hook_start(action, metadata):
        events.append(f"start:{action}")
    def hook_success(action, duration_ms, metadata):
        events.append(f"success:{action}")
        
    manager.register_hook("step_start", hook_start)
    manager.register_hook("step_success", hook_success)
    
    with manager.start_action("navigate_to_page", {"selector_used": "body", "selector_type": "custom"}) as ctx:
        time.sleep(0.01)
        
    assert len(manager.telemetry.actions) == 1
    trace = manager.telemetry.actions[0]
    
    assert trace.action_name == "navigate_to_page"
    assert trace.status == "success"
    assert trace.duration_ms > 0
    assert trace.selector_used == "body"
    assert trace.selector_type == "custom"
    
    # Verify hooks triggered
    assert "start:navigate_to_page" in events
    assert "success:navigate_to_page" in events

def test_trace_manager_save_debug_report(tmp_path):
    manager = TraceManager(session_id="test_sess", base_dir=str(tmp_path))
    
    mock_driver = MagicMock()
    mock_driver.page_source = "<html><body>Mock Source</body></html>"
    mock_driver.current_url = "http://localhost/sandbox"
    mock_driver.title = "Sandbox Form"
    
    # Record one action
    with manager.start_action("test_action"):
        pass
        
    report_path = manager.save_debug_report(mock_driver)
    
    assert os.path.exists(report_path)
    assert report_path.endswith(".json")
    
    html_snapshot_path = report_path.replace(".json", ".html")
    assert os.path.exists(html_snapshot_path)
    
    with open(html_snapshot_path, "r", encoding="utf-8") as f:
        content = f.read()
        assert "Mock Source" in content

# --- Watchdog Unit Tests ---

def test_resource_watchdog_healthy():
    watchdog = BrowserResourceWatchdog(max_duration_sec=10.0)
    mock_driver = MagicMock()
    mock_driver.service.process.poll.return_value = None
    mock_driver.execute_script.return_value = "complete"
    
    assert watchdog.check_health(mock_driver) is True

def test_resource_watchdog_timeout():
    # Setup watchdog with immediate timeout
    watchdog = BrowserResourceWatchdog(max_duration_sec=-1.0)
    mock_driver = MagicMock()
    
    with pytest.raises(ValueError) as exc_info:
        watchdog.check_health(mock_driver)
    assert "exceeded max allowed duration" in str(exc_info.value)

def test_resource_watchdog_unresponsive():
    watchdog = BrowserResourceWatchdog(max_duration_sec=30.0)
    mock_driver = MagicMock()
    mock_driver.service.process.poll.return_value = None
    # Mock JS check raising exception (tab is hung)
    mock_driver.execute_script.side_effect = Exception("Tab crash")
    
    with pytest.raises(WebDriverException) as exc_info:
        watchdog.check_health(mock_driver)
    assert "Browser tab is unresponsive" in str(exc_info.value)

# --- Integration Test with Sandbox Form ---

@pytest.mark.asyncio
async def test_form_automation_observability_integration(tmp_path):
    manager = BrowserManager(headless=True)
    service = FormAutomationService(manager)
    
    # Register hooks for tracing
    hooks_triggered = []
    service.register_hook("step_start", lambda name, metadata: hooks_triggered.append(f"start:{name}"))
    service.register_hook("step_success", lambda name, duration_ms, metadata: hooks_triggered.append(f"success:{name}"))
    
    # Prepare local form path
    sandbox_path = os.path.abspath("tests/resources/sandbox_form.html")
    sandbox_url = f"file:///{sandbox_path.replace(os.sep, '/')}"
    
    # Setup data
    field_data = {
        "first_name": "Jane",
        "last_name": "Smith",
        "email": "jane@example.com",
        "terms": True
    }
    
    # Override artifacts path in env to output to temp directory for cleanup ease
    with patch.dict(os.environ, {"ANTIGRAVITY_ARTIFACTS_DIR": str(tmp_path)}):
        outcome = await service.automate_form(
            url=sandbox_url,
            field_data=field_data,
            file_uploads={},
            success_indicators=["Application Submitted"],
            session_id="integration_test_session"
        )
        
        # Verify execution
        assert outcome.success is True
        
        # Verify telemetry trace JSON and DOM snapshot HTML was saved
        traces_dir = os.path.join(str(tmp_path), "traces")
        trace_files = os.listdir(traces_dir)
        
        json_file = next(f for f in trace_files if f.endswith(".json"))
        html_file = next(f for f in trace_files if f.endswith(".html"))
        
        # Read trace metrics
        with open(os.path.join(traces_dir, json_file), "r", encoding="utf-8") as f:
            telemetry_data = json.load(f)
            assert telemetry_data["session_id"] == "integration_test_session"
            assert telemetry_data["success"] is True
            assert len(telemetry_data["actions"]) > 0
            
            # Verify selector tracking metadata
            first_name_trace = next(act for act in telemetry_data["actions"] if act.get("metadata", {}).get("field_key") == "first_name")
            assert first_name_trace["selector_used"] == "attribute:first_name"
            assert first_name_trace["selector_type"] == "matched_attribute"
        
        # Verify screenshot is indexed in telemetry
        assert len(telemetry_data["screenshots"]) > 0
        
        # Verify hooks triggered
        assert "start:start_session" in hooks_triggered
        assert "success:start_session" in hooks_triggered
        assert "start:load_page" in hooks_triggered
        assert "success:load_page" in hooks_triggered
        assert "start:type_field" in hooks_triggered
        assert "success:type_field" in hooks_triggered
        assert "start:submit_form" in hooks_triggered
        assert "success:submit_form" in hooks_triggered
