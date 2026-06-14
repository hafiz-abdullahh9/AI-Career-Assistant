import time
from typing import Dict, Any, List, Tuple, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
import structlog

from app.integrations.adapters.base_adapter import BaseIntegrationAdapter
from app.browser.selectors.field_selectors import FieldSelectors
from app.browser.forms.form_automation import human_type, human_click, select_dropdown_value
from app.browser.observability.tracing.trace_tracker import TraceManager

logger = structlog.get_logger(__name__)

class GenericAdapter(BaseIntegrationAdapter):
    """
    Fallback integration adapter for websites without dedicated profiles.
    Reuses the dynamic selector matching logic built for the foundation.
    """

    @property
    def supported_domains(self) -> List[str]:
        return []

    @property
    def profile_name(self) -> str:
        return ""

    def __init__(self, custom_selectors: Optional[Dict[str, str]] = None) -> None:
        # Generic adapter doesn't load a profile, but uses FieldSelectors
        self.profile = {}
        self.field_selectors = FieldSelectors(custom_selectors=custom_selectors)

    def fill_fields(self, driver: webdriver.Remote | webdriver.Chrome, field_data: Dict[str, Any], trace_manager: TraceManager) -> None:
        """
        Interacts with form inputs by dynamically matching candidate elements.
        """
        for field_key, value in field_data.items():
            if value is None:
                continue

            for attempt in range(2):
                try:
                    element, selector_used, selector_type = self._find_field_element(driver, field_key, is_file=False)
                    tag_name = element.tag_name.lower()
                    elem_type = (element.get_attribute("type") or "").lower()

                    action_name = "select_dropdown" if tag_name == "select" else (
                        "click_checkbox" if elem_type == "checkbox" else "type_field"
                    )

                    with trace_manager.start_action(action_name, {
                        "field_key": field_key,
                        "selector_used": selector_used,
                        "selector_type": selector_type,
                        "attempt": attempt + 1
                    }):
                        if tag_name == "select":
                            select_dropdown_value(element, str(value))
                        elif elem_type == "checkbox":
                            is_selected = element.is_selected()
                            if (value and not is_selected) or (not value and is_selected):
                                human_click(driver, element)
                        else:
                            human_type(element, str(value))
                    break
                except StaleElementReferenceException:
                    if attempt == 1:
                        raise
                    time.sleep(0.5)

    def upload_files(self, driver: webdriver.Remote | webdriver.Chrome, file_uploads: Dict[str, str], trace_manager: TraceManager) -> None:
        """
        Interacts with file inputs by dynamically matching file candidates.
        """
        for field_key, local_path in file_uploads.items():
            if not local_path:
                continue

            for attempt in range(2):
                try:
                    element, selector_used, selector_type = self._find_field_element(driver, field_key, is_file=True)
                    with trace_manager.start_action("upload_file", {
                        "field_key": field_key,
                        "selector_used": selector_used,
                        "selector_type": selector_type,
                        "attempt": attempt + 1
                    }):
                        element.send_keys(local_path)
                    break
                except StaleElementReferenceException:
                    if attempt == 1:
                        raise
                    time.sleep(0.5)

    def submit_form(self, driver: webdriver.Remote | webdriver.Chrome, trace_manager: TraceManager) -> None:
        """
        Finds the submit button and clicks it.
        """
        # Find submit button
        submit_xpath_candidates = [
            "//button[@type='submit']",
            "//input[@type='submit']",
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'submit')]",
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply')]",
            "//input[contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'submit')]",
            "//input[contains(translate(@value, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply')]"
        ]
        
        element = None
        selector_used = None

        for xpath in submit_xpath_candidates:
            try:
                element = driver.find_element(By.XPATH, xpath)
                selector_used = xpath
                break
            except NoSuchElementException:
                continue

        if not element:
            raise NoSuchElementException("Could not locate form submit button on page")

        with trace_manager.start_action("submit_form", {"selector_used": selector_used}):
            human_click(driver, element)

    def verify_success(self, driver: webdriver.Remote | webdriver.Chrome, trace_manager: TraceManager) -> bool:
        """
        Checks success indicators.
        """
        success_indicators = ["submitted", "success", "thank you", "received", "confirmation"]
        end_time = time.time() + 10.0
        while time.time() < end_time:
            try:
                current_url = driver.current_url.lower()
                body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
                
                for indicator in success_indicators:
                    if indicator in body_text or indicator in current_url:
                        logger.info("integrations.generic.success_matched", indicator=indicator)
                        return True
            except Exception as e:
                logger.warning("integrations.generic.success_check_error", error=str(e))
                
            time.sleep(0.5)
            
        return False

    def _find_field_element(
        self,
        driver: webdriver.Remote | webdriver.Chrome,
        field_key: str,
        is_file: bool = False
    ) -> Tuple[WebElement, str, str]:
        """
        Locates the HTML element corresponding to the field key.
        Returns a tuple: (WebElement, selector_string_used, selector_type).
        """
        # 1. Custom locators check
        locator = self.field_selectors.get_locator(field_key)
        if locator:
            loc_str = f"{locator[0]}:{locator[1]}"
            return driver.find_element(*locator), loc_str, "custom"

        # 2. Match patterns across elements
        patterns = self.field_selectors.patterns.get(field_key, [field_key])
        
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
                        return element, f"attribute:{term_lower}", "matched_attribute"

                # Check labels pointing to this element ID
                if elem_id:
                    try:
                        labels = driver.find_elements(By.XPATH, f"//label[@for='{elem_id}']")
                        for label in labels:
                            label_text = label.text.lower()
                            for term in patterns:
                                if term.lower() in label_text:
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
                    return element, xpath, "fallback_xpath"
                except NoSuchElementException:
                    continue

        raise NoSuchElementException(f"Could not locate form element for field key: '{field_key}'")
