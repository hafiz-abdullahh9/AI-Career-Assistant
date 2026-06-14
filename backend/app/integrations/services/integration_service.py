import time
import uuid
import re
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from app.core.config import get_settings
from app.core.exceptions import ForbiddenError, AppBaseError
from app.models.orm import Application, ApprovalRequest
from app.models.schemas import ApplicationStatus
from app.browser.sessions.session_manager import BrowserManager
from app.browser.observability.tracing.trace_tracker import TraceManager
from app.browser.observability.screenshots.screenshot_store import ScreenshotStore
from app.browser.observability.watchdogs.resource_watchdog import BrowserResourceWatchdog
from app.browser.schemas.browser_schemas import AutomationOutcome
from app.browser.uploads.upload_handler import UploadHandler

# Integrations registry & policies
from app.integrations.adapters.registry import AdapterRegistry
from app.orchestration.policies.execution_policies import DomainAllowlistPolicy, ApprovalGatePolicy

logger = structlog.get_logger(__name__)

class IntegrationService:
    """
    Orchestration authority for running controlled integration adapters.
    Implements a strict DENY-BY-DEFAULT policy:
    If allowlists, approvals, selectors, or replay telemetry are missing/unvalidated, execution is blocked.
    """

    def __init__(self, db: AsyncSession, redis: Any) -> None:
        self.db = db
        self.redis = redis
        self.upload_handler = UploadHandler()

    async def execute_integration(
        self,
        application: Application,
        session_id: str,
        task_id: str
    ) -> AutomationOutcome:
        """
        Executes form automation via the matched integration adapter.
        Performs pre-flight deny-by-default checks before starting browser session.
        """
        start_time = time.time()
        url = application.application_url
        if not url:
            raise ValueError("Application URL is missing.")

        # ── 1. DENY-BY-DEFAULT: Domain Allowlist validation ──
        if not DomainAllowlistPolicy.check_url(url):
            raise ForbiddenError(f"Target URL domain not allowlisted: {url}")

        # ── 2. DENY-BY-DEFAULT: Approvals validation ──
        priority = application.metadata_.get("priority", "normal") if application.metadata_ else "normal"
        from urllib.parse import urlparse
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        platform = netloc.split(".")[0] if "." in netloc else netloc
        if parsed.scheme == "file":
            platform = "sandbox"

        requires_approval = ApprovalGatePolicy.requires_approval(
            manual_approval_required=application.manual_approval_required,
            priority=priority,
            platform=platform
        )
        
        if requires_approval:
            # Query if there exists an APPROVED ApprovalRequest
            stmt = select(ApprovalRequest).where(
                ApprovalRequest.application_id == application.application_id,
                ApprovalRequest.decision == "approved"
            )
            res = await self.db.execute(stmt)
            app_req = res.scalar_one_or_none()
            if not app_req:
                raise ForbiddenError("Execution blocked: Manual approval is required but missing or not granted.")

        # ── 3. DENY-BY-DEFAULT: Adapter selection & Profile Selector validation ──
        custom_selectors = application.metadata_.get("custom_selectors") if application.metadata_ else None
        adapter = AdapterRegistry.get_adapter(url, custom_selectors=custom_selectors)
        
        # If it's a platform adapter, verify its profile config is valid and loaded
        if adapter.profile_name:
            if not adapter.profile:
                raise ValueError(f"Malformed or missing selector profile config for: {adapter.profile_name}")
            # Ensure required fields in profile have mapped selectors
            required = adapter.profile.get("required_fields", [])
            for req_field in required:
                if not adapter.get_selector(req_field):
                    raise ValueError(f"Required selector '{req_field}' is unmapped in profile '{adapter.profile_name}'")

        # ── 4. DENY-BY-DEFAULT: Replay Telemetry validation ──
        if not session_id or not task_id:
            raise ValueError("Replay telemetry context (session_id / task_id) is unavailable.")

        # Initialize Observability Layers
        screenshot_store = ScreenshotStore()
        trace_manager = TraceManager(session_id=session_id, task_id=task_id)
        watchdog = BrowserResourceWatchdog(max_duration_sec=120.0)

        # Enforce writable state (TraceManager saves trace to disk)
        try:
            trace_manager.save_debug_report(None, "init_check")
        except Exception as te:
            raise ValueError(f"Replay telemetry persistence folder is unavailable or not writable: {te}")

        browser_manager = BrowserManager(headless=True)
        driver = None
        screenshot_path = None
        html_snapshot = None
        success_matched = False
        conf_id = None

        try:
            logger.info("integrations.execution.start", session_id=session_id, url=url, adapter=adapter.__class__.__name__)
            
            # Start Browser Session
            with trace_manager.start_action("start_session"):
                driver = browser_manager.start_session()
            
            watchdog.check_health(driver)
            
            # Navigate to page
            with trace_manager.start_action("load_page", {"url": url}):
                driver.get(url)
                self._wait_for_page_ready(driver)

            watchdog.check_health(driver)

            # Retrieve field inputs
            field_data = application.metadata_.get("field_data") or {
                "first_name": "John",
                "last_name": "Doe",
                "email": "candidate@example.com",
                "phone": "555-0199"
            }

            # Pre-download resume files if any
            file_uploads = {}
            if application.resume_version_id:
                resume_meta = application.metadata_.get("resume")
                if resume_meta:
                    with trace_manager.start_action("download_file", {"filename": resume_meta.get("filename")}):
                        local_path = await self.upload_handler.download_file(
                            url=resume_meta["storage_url"],
                            filename=resume_meta["filename"]
                        )
                        file_uploads["resume"] = local_path

            # Fill Fields
            watchdog.check_health(driver)
            adapter.fill_fields(driver, field_data, trace_manager)

            # Upload files
            if file_uploads:
                watchdog.check_health(driver)
                adapter.upload_files(driver, file_uploads, trace_manager)

            watchdog.check_health(driver)

            # Capture pre-submit screenshot
            screenshot_store.capture(driver, session_id, "before_submit")

            # Submit form
            adapter.submit_form(driver, trace_manager)

            watchdog.check_health(driver)

            # Verify Success
            with trace_manager.start_action("wait_for_success"):
                success_matched = adapter.verify_success(driver, trace_manager)

            if not success_matched:
                logger.warning("integrations.execution.success_verification_timeout", session_id=session_id)

            # Extract confirmation ID if possible
            conf_id = self._extract_confirmation_id(driver, adapter.profile)

            # Capture post-submit screenshot
            screenshot_path = screenshot_store.capture(driver, session_id, "after_submit")

            # Capture DOM snapshot
            try:
                html_snapshot = driver.page_source
            except Exception:
                pass

            latency_ms = (time.time() - start_time) * 1000
            
            trace_manager.telemetry.screenshots = screenshot_store.captured_logs
            trace_manager.save_debug_report(driver, html_snapshot)

            return AutomationOutcome(
                success=True,
                confirmation_id=conf_id,
                message="Form submitted successfully" if success_matched else "Form submitted but success verification timed out",
                screenshot_url=screenshot_path,
                latency_ms=latency_ms
            )

        except Exception as e:
            logger.error("integrations.execution.failed", session_id=session_id, error=str(e), exc_info=True)
            
            trace_manager.telemetry.success = False
            trace_manager.telemetry.error_reason = str(e)

            # Capture exception telemetry/screenshot
            if driver:
                try:
                    screenshot_path = screenshot_store.capture(driver, session_id, "on_exception")
                except Exception as se:
                    logger.warning("integrations.screenshot_failed", session_id=session_id, error=str(se))
                try:
                    html_snapshot = driver.page_source
                except Exception:
                    pass

            latency_ms = (time.time() - start_time) * 1000
            trace_manager.telemetry.screenshots = screenshot_store.captured_logs
            try:
                trace_manager.save_debug_report(driver, html_snapshot)
            except Exception as re:
                logger.warning("integrations.save_report_failed", error=str(re))

            return AutomationOutcome(
                success=False,
                message=str(e),
                screenshot_url=screenshot_path,
                latency_ms=latency_ms
            )

        finally:
            logger.info("integrations.execution.cleanup", session_id=session_id)
            self.upload_handler.cleanup()
            browser_manager.close_session()

    def _wait_for_page_ready(self, driver: webdriver.Remote | webdriver.Chrome) -> None:
        try:
            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            logger.warning("integrations.page_ready_timeout")

    def _extract_confirmation_id(self, driver: webdriver.Remote | webdriver.Chrome, profile: Dict[str, Any]) -> Optional[str]:
        conf_cfg = profile.get("confirmation_extraction", {})
        selectors = conf_cfg.get("selectors", ["#confirmation-code", ".confirmation-id"])
        regex_pattern = conf_cfg.get("regex", r'(CONF-[0-9]+|CONF[0-9]+|Confirmation\s+(?:ID|Code|Number|#)\s*:\s*([A-Za-z0-9\-]+))')

        # Try selectors first
        for sel in selectors:
            try:
                by_type = By.CSS_SELECTOR if not sel.startswith("//") else By.XPATH
                element = driver.find_element(by_type, sel)
                if element.text:
                    return element.text.strip()
            except Exception:
                continue

        # Try regex search on body text
        try:
            body = driver.find_element(By.TAG_NAME, "body").text
            match = re.search(regex_pattern, body, re.IGNORECASE)
            if match:
                return match.group(1) or match.group(2)
        except Exception:
            pass

        return None
