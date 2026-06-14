import os
import re
import tempfile
import time
import uuid
from typing import Dict, Any, Optional, List, Tuple
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import (
    WebDriverException,
    NoSuchElementException,
    TimeoutException,
    StaleElementReferenceException
)
import structlog

from app.browser.sessions.session_manager import BrowserManager
from app.browser.selectors.field_selectors import FieldSelectors
from app.browser.uploads.upload_handler import UploadHandler
from app.browser.forms.form_automation import human_type, human_click, select_dropdown_value
from app.browser.schemas.browser_schemas import FormFieldMapping, AutomationOutcome
from app.browser.utils.wait_utils import wait_for_element_visible, wait_for_element_clickable

# Import Observability Components
from app.browser.observability.screenshots.screenshot_store import ScreenshotStore
from app.browser.observability.tracing.trace_tracker import TraceManager
from app.browser.observability.watchdogs.resource_watchdog import BrowserResourceWatchdog

logger = structlog.get_logger(__name__)

class FormAutomationService:
    """
    Orchestrates the lifecycle of form automation tasks:
    Loading pages, selector mapping, form filling, uploading files, submitting, and cleanup.
    Fully instrumented with telemetry tracing, screenshot persistence, and watchdog resource checks.
    """

    def __init__(self, browser_manager: BrowserManager) -> None:
        self.browser_manager = browser_manager
        self.upload_handler = UploadHandler()
        self._hooks = {
            "step_start": [],
            "step_success": [],
            "step_failure": []
        }

    def register_hook(self, event_type: str, callback: Any) -> None:
        """
        Registers an execution event callback. Available event_type:
        'step_start', 'step_success', 'step_failure'.
        """
        if event_type in self._hooks:
            self._hooks[event_type].append(callback)

    async def automate_form(
        self,
        url: str,
        field_data: Dict[str, Any],
        file_uploads: Dict[str, Dict[str, str]],
        custom_selectors: Optional[Dict[str, str]] = None,
        submit_selector: Optional[str] = None,
        success_indicators: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> AutomationOutcome:
        """
        Orchestrates form filling and submission task.
        """
        start_time = time.time()
        session_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"
        field_selectors = FieldSelectors(custom_selectors=custom_selectors)
        success_indicators = success_indicators or ["submitted", "success", "thank you", "received", "confirmation"]
        
        # Initialize Observability Layers
        screenshot_store = ScreenshotStore()
        trace_manager = TraceManager(session_id=session_id, task_id=task_id)
        watchdog = BrowserResourceWatchdog(max_duration_sec=120.0)

        # Register Service Hooks to Trace Manager
        for event_type, callbacks in self._hooks.items():
            for cb in callbacks:
                trace_manager.register_hook(event_type, cb)

        driver = None
        screenshot_path = None
        html_snapshot = None
        success_matched = False
        conf_id = None
        
        try:
            logger.info("browser.automation.start", session_id=session_id, url=url)
            
            # 1. Start Browser Session
            with trace_manager.start_action("start_session"):
                driver = self.browser_manager.start_session()
            
            # Perform initial watchdog check
            watchdog.check_health(driver)
            
            # 2. Navigate and Load Page
            with trace_manager.start_action("load_page", {"url": url}):
                driver.get(url)
                self._wait_for_page_ready(driver)

            watchdog.check_health(driver)
            
            # 3. Process File Downloads first
            local_file_paths = {}
            for field_key, file_info in file_uploads.items():
                with trace_manager.start_action(
                    "download_file", 
                    {"field_key": field_key, "filename": file_info.get("filename")}
                ):
                    local_path = await self.upload_handler.download_file(
                        url=file_info["url"],
                        filename=file_info["filename"]
                    )
                    local_file_paths[field_key] = local_path

            watchdog.check_health(driver)

            # 4. Fill standard form fields
            for field_key, value in field_data.items():
                if value is None:
                    continue
                watchdog.check_health(driver)
                self._fill_field_with_retry(driver, field_key, value, field_selectors, trace_manager)

            # 5. Upload files
            for field_key, local_path in local_file_paths.items():
                watchdog.check_health(driver)
                self._fill_field_with_retry(
                    driver, field_key, local_path, field_selectors, trace_manager, is_file=True
                )

            watchdog.check_health(driver)

            # 6. Locate and Click Submit Button
            submit_btn, submit_loc_str = self._find_submit_button(driver, submit_selector)
            
            # Capture BEFORE submit screenshot
            screenshot_store.capture(driver, session_id, "before_submit")
            
            with trace_manager.start_action("submit_form", {"selector_used": submit_loc_str}):
                logger.info("browser.automation.submitting", session_id=session_id)
                human_click(driver, submit_btn)

            watchdog.check_health(driver)

            # 7. Wait for success confirmation
            with trace_manager.start_action("wait_for_success"):
                success_matched = self._wait_for_success(driver, success_indicators)
            
            if not success_matched:
                logger.warning("browser.automation.success_indicator_not_found", session_id=session_id)
            
            # 8. Extract confirmation ID
            with trace_manager.start_action("extract_confirmation_id"):
                conf_id = self._extract_confirmation_id(driver)
            
            # Capture AFTER submit screenshot
            screenshot_path = screenshot_store.capture(driver, session_id, "after_submit")

            # Capture current page source snapshot
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
            logger.error("browser.automation.failed", session_id=session_id, error=str(e), exc_info=True)
            
            # Save exception context in telemetry
            trace_manager.telemetry.success = False
            trace_manager.telemetry.error_reason = str(e)

            # Capture failure screenshot
            if driver:
                try:
                    screenshot_path = screenshot_store.capture(driver, session_id, "on_exception")
                except Exception as se:
                    logger.warning("browser.automation.screenshot_failed", session_id=session_id, error=str(se))
                try:
                    html_snapshot = driver.page_source
                except Exception:
                    pass

            latency_ms = (time.time() - start_time) * 1000
            
            trace_manager.telemetry.screenshots = screenshot_store.captured_logs
            try:
                trace_manager.save_debug_report(driver, html_snapshot)
            except Exception as re:
                logger.warning("browser.automation.save_report_failed", error=str(re))

            return AutomationOutcome(
                success=False,
                message=str(e),
                screenshot_url=screenshot_path,
                latency_ms=latency_ms
            )
            
        finally:
            logger.info("browser.automation.cleanup", session_id=session_id)
            self.upload_handler.cleanup()
            self.browser_manager.close_session()

    def _wait_for_page_ready(self, driver: webdriver.Remote | webdriver.Chrome) -> None:
        """
        Wait for document state to be complete.
        """
        try:
            WebDriverWait(driver, 30).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except TimeoutException:
            logger.warning("browser.automation.page_ready_timeout")

    def _fill_field_with_retry(
        self,
        driver: webdriver.Remote | webdriver.Chrome,
        field_key: str,
        value: Any,
        field_selectors: FieldSelectors,
        trace_manager: TraceManager,
        is_file: bool = False
    ) -> None:
        """
        Finds the element and interacts with it, retrying if element is stale.
        Tracks selector used and registers traces for timing.
        """
        for attempt in range(2):
            try:
                # Find element and retrieve selector metadata
                element, selector_used, selector_type = self._find_field_element(
                    driver, field_key, field_selectors, is_file=is_file
                )
                
                tag_name = element.tag_name.lower()
                elem_type = (element.get_attribute("type") or "").lower()
                
                action_name = "upload_file" if is_file else (
                    "select_dropdown" if tag_name == "select" else (
                        "click_checkbox" if elem_type == "checkbox" else "type_field"
                    )
                )

                # Wrap the exact interaction step in trace context
                with trace_manager.start_action(action_name, {
                    "field_key": field_key,
                    "selector_used": selector_used,
                    "selector_type": selector_type,
                    "attempt": attempt + 1
                }):
                    if is_file:
                        logger.info("browser.automation.uploading", field_key=field_key, path=value)
                        element.send_keys(value)
                    elif tag_name == "select":
                        logger.info("browser.automation.selecting_dropdown", field_key=field_key, value=value)
                        select_dropdown_value(element, str(value))
                    elif elem_type == "checkbox":
                        logger.info("browser.automation.checking_checkbox", field_key=field_key, value=value)
                        is_selected = element.is_selected()
                        if (value and not is_selected) or (not value and is_selected):
                            human_click(driver, element)
                    else:
                        logger.info("browser.automation.typing", field_key=field_key, text=value)
                        human_type(element, str(value))
                
                return  # Successful interaction
            except StaleElementReferenceException:
                logger.warning("browser.automation.stale_element", field_key=field_key, attempt=attempt)
                if attempt == 1:
                    raise
                time.sleep(0.5)

    def _find_field_element(
        self,
        driver: webdriver.Remote | webdriver.Chrome,
        field_key: str,
        field_selectors: FieldSelectors,
        is_file: bool = False
    ) -> Tuple[WebElement, str, str]:
        """
        Locates the HTML element corresponding to the field key.
        Returns a tuple: (WebElement, selector_string_used, selector_type).
        """
        # 1. Custom locators check
        locator = field_selectors.get_locator(field_key)
        if locator:
            loc_str = f"{locator[0]}:{locator[1]}"
            logger.info("browser.selector.custom_found", field_key=field_key, locator=locator)
            return driver.find_element(*locator), loc_str, "custom"

        # 2. Match patterns across elements
        patterns = field_selectors.patterns.get(field_key, [field_key])
        
        candidates = driver.find_elements(By.XPATH, "//input | //textarea | //select")
        for element in candidates:
            try:
                tag_name = element.tag_name.lower()
                elem_id = (element.get_attribute("id") or "").lower()
                elem_name = (element.get_attribute("name") or "").lower()
                elem_placeholder = (element.get_attribute("placeholder") or "").lower()
                elem_aria = (element.get_attribute("aria-label") or "").lower()
                elem_type = (element.get_attribute("type") or "").lower()

                # Filter inputs based on type
                if elem_type in ["hidden", "submit", "button", "image"]:
                    continue
                if is_file and elem_type != "file":
                    continue
                if not is_file and elem_type == "file":
                    continue

                # Matches direct attributes
                for term in patterns:
                    term_lower = term.lower()
                    if (term_lower in elem_id or 
                        term_lower in elem_name or 
                        term_lower in elem_placeholder or 
                        term_lower in elem_aria):
                        logger.info(
                            "browser.selector.matched_attribute",
                            field_key=field_key,
                            tag=tag_name,
                            name=elem_name,
                            id=elem_id,
                            matched_term=term
                        )
                        return element, f"attribute:{term_lower}", "matched_attribute"

                # Check labels pointing to this element ID
                if elem_id:
                    try:
                        labels = driver.find_elements(By.XPATH, f"//label[@for='{elem_id}']")
                        for label in labels:
                            label_text = label.text.lower()
                            for term in patterns:
                                if term.lower() in label_text:
                                    logger.info(
                                        "browser.selector.matched_label_for",
                                        field_key=field_key,
                                        label_text=label.text,
                                        matched_term=term
                                    )
                                    return element, f"label_for:{term.lower()}", "matched_label"
                    except Exception:
                        pass

                # Check parent/ancestor labels wrapping this element
                try:
                    parent_labels = element.find_elements(By.XPATH, "ancestor::label")
                    for label in parent_labels:
                        label_text = label.text.lower()
                        for term in patterns:
                            if term.lower() in label_text:
                                logger.info(
                                    "browser.selector.matched_parent_label",
                                    field_key=field_key,
                                    label_text=label.text,
                                    matched_term=term
                                )
                                return element, f"parent_label:{term.lower()}", "matched_label"
                except Exception:
                    pass

            except StaleElementReferenceException:
                continue

        # 3. Direct XPath Attribute Fallback
        for term in patterns:
            for tag in ["input", "textarea", "select"]:
                file_cond = "[@type='file']" if is_file else "[not(@type='file')]"
                xpath = f"//{tag}{file_cond}[@id='{term}' or @name='{term}']"
                try:
                    element = driver.find_element(By.XPATH, xpath)
                    logger.info("browser.selector.fallback_xpath_matched", field_key=field_key, xpath=xpath)
                    return element, xpath, "fallback_xpath"
                except NoSuchElementException:
                    continue

        raise NoSuchElementException(f"Could not locate form element for field key: '{field_key}'")

    def _find_submit_button(
        self, 
        driver: webdriver.Remote | webdriver.Chrome, 
        submit_selector: Optional[str] = None
    ) -> Tuple[WebElement, str]:
        """
        Finds the form submit button. Returns a tuple: (WebElement, selector_string_used).
        """
        if submit_selector:
            locator = submit_selector
            if locator.startswith("css:"):
                return driver.find_element(By.CSS_SELECTOR, locator[4:]), locator
            elif locator.startswith("xpath:"):
                return driver.find_element(By.XPATH, locator[6:]), locator
            else:
                return driver.find_element(By.CSS_SELECTOR, locator), locator

        # Common HTML patterns for submit buttons
        submit_xpath_candidates = [
            "//button[@type='submit']",
            "//input[@type='submit']",
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'submit')]",
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply')]",
            "//input[contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'submit')]",
            "//input[contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply')]"
        ]
        
        for xpath in submit_xpath_candidates:
            try:
                element = driver.find_element(By.XPATH, xpath)
                logger.info("browser.submit.button_matched", xpath=xpath)
                return element, xpath
            except NoSuchElementException:
                continue
                
        raise NoSuchElementException("Could not locate form submit button on page")

    def _wait_for_success(self, driver: webdriver.Remote | webdriver.Chrome, success_indicators: List[str], timeout: float = 10.0) -> bool:
        """
        Waits until one of the success indicators is found in the page text/URL.
        """
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                current_url = driver.current_url.lower()
                page_source = driver.page_source.lower()
                
                for indicator in success_indicators:
                    indicator_lower = indicator.lower()
                    if indicator_lower in page_source or indicator_lower in current_url:
                        logger.info("browser.success.indicator_matched", indicator=indicator)
                        return True
            except Exception as e:
                logger.warning("browser.success.check_error", error=str(e))
                
            time.sleep(0.5)
            
        return False

    def _extract_confirmation_id(self, driver: webdriver.Remote | webdriver.Chrome) -> Optional[str]:
        """
        Attempts to extract a confirmation code from the page text or confirmation elements.
        """
        # 1. Direct elements check
        for selector, values in [(By.ID, ["confirmation-code", "confirmation_code", "confirmation-number"]),
                                 (By.CLASS_NAME, ["conf-id", "confirmation_code"])]:
            for val in values:
                try:
                    element = driver.find_element(selector, val)
                    if element.text:
                        logger.info("browser.success.id_extracted_element", selector=selector, value=val, text=element.text)
                        return element.text.strip()
                except NoSuchElementException:
                    continue

        # 2. Text body Regex search
        try:
            body_element = driver.find_element(By.TAG_NAME, "body")
            body_text = body_element.text
            match = re.search(r'(CONF-[0-9]+|CONF[0-9]+|Confirmation\s+(?:ID|Code|Number|#)\s*:\s*([A-Za-z0-9\-]+))', body_text, re.IGNORECASE)
            if match:
                extracted = match.group(1) or match.group(2)
                logger.info("browser.success.id_extracted_regex", match=extracted)
                return extracted.strip()
        except Exception as e:
            logger.warning("browser.success.regex_extraction_failed", error=str(e))

        return None
