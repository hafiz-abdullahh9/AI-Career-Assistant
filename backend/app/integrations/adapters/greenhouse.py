import time
from typing import Dict, Any, List
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
import structlog
import re

from app.integrations.adapters.base_adapter import BaseIntegrationAdapter
from app.browser.forms.form_automation import human_type, human_click, select_dropdown_value
from app.browser.observability.tracing.trace_tracker import TraceManager

logger = structlog.get_logger(__name__)

class GreenhouseAdapter(BaseIntegrationAdapter):
    """
    Integration adapter tailored for greenhouse.io forms.
    """

    @property
    def supported_domains(self) -> List[str]:
        return ["greenhouse.io", "boards.greenhouse.io"]

    @property
    def profile_name(self) -> str:
        return "greenhouse"

    def fill_fields(self, driver: webdriver.Remote | webdriver.Chrome, field_data: Dict[str, Any], trace_manager: TraceManager) -> None:
        """
        Fills the fields defined in field_data by resolving selectors from greenhouse.json profile.
        """
        for field_key, value in field_data.items():
            if value is None:
                continue

            with trace_manager.start_action("fill_field", {"field_key": field_key, "value": value}):
                resolved = self.get_selector(field_key)
                element = None
                selector_used = None
                selector_type = "profile"

                if resolved:
                    by_type, selector_val = resolved
                    try:
                        element = driver.find_element(by_type, selector_val)
                        selector_used = f"{by_type}:{selector_val}"
                    except NoSuchElementException:
                        logger.warning("integrations.greenhouse.profile_selector_not_found", field_key=field_key, selector=selector_val)

                # Fallback heuristics for Greenhouse forms
                if not element:
                    # Look for input with matching id, name, placeholder, or label
                    candidates = driver.find_elements(By.XPATH, "//input | //textarea | //select")
                    for cand in candidates:
                        try:
                            elem_id = (cand.get_attribute("id") or "").lower()
                            elem_name = (cand.get_attribute("name") or "").lower()
                            elem_type = (cand.get_attribute("type") or "").lower()

                            if elem_type in ["hidden", "submit", "button", "image", "file"]:
                                continue

                            # Standard field name matching
                            if field_key.lower() in elem_id or field_key.lower() in elem_name:
                                element = cand
                                selector_used = f"heuristic:{cand.get_attribute('name') or cand.get_attribute('id')}"
                                selector_type = "heuristic"
                                break
                        except StaleElementReferenceException:
                            continue

                if not element:
                    # If field is not found and it's not marked as required, skip. Otherwise raise error.
                    required_fields = self.profile.get("required_fields", [])
                    if field_key in required_fields:
                        raise NoSuchElementException(f"Required Greenhouse field '{field_key}' could not be located.")
                    logger.info("integrations.greenhouse.field_skipped", field_key=field_key)
                    continue

                # Interact with the element
                tag_name = element.tag_name.lower()
                elem_type = (element.get_attribute("type") or "").lower()

                if tag_name == "select":
                    select_dropdown_value(element, str(value))
                elif elem_type == "checkbox":
                    is_selected = element.is_selected()
                    if (value and not is_selected) or (not value and is_selected):
                        human_click(driver, element)
                else:
                    human_type(element, str(value))

    def upload_files(self, driver: webdriver.Remote | webdriver.Chrome, file_uploads: Dict[str, str], trace_manager: TraceManager) -> None:
        """
        Uploads files to file-input elements.
        """
        for field_key, local_path in file_uploads.items():
            if not local_path:
                continue

            with trace_manager.start_action("upload_file", {"field_key": field_key, "path": local_path}):
                resolved = self.get_selector(field_key)
                element = None

                if resolved:
                    by_type, selector_val = resolved
                    try:
                        element = driver.find_element(by_type, selector_val)
                    except NoSuchElementException:
                        logger.warning("integrations.greenhouse.profile_file_selector_not_found", field_key=field_key, selector=selector_val)

                if not element:
                    # Look for input[type="file"] elements with IDs containing the field_key
                    file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")
                    for file_in in file_inputs:
                        try:
                            elem_id = (file_in.get_attribute("id") or "").lower()
                            elem_name = (file_in.get_attribute("name") or "").lower()
                            if field_key.lower() in elem_id or field_key.lower() in elem_name:
                                element = file_in
                                break
                        except StaleElementReferenceException:
                            continue

                if not element:
                    # Fallback to any input[type='file'] containing field_key in label or wrapper
                    raise NoSuchElementException(f"Could not locate file input for Greenhouse field '{field_key}'")

                element.send_keys(local_path)
                time.sleep(1.0) # wait for upload animation / processing

    def submit_form(self, driver: webdriver.Remote | webdriver.Chrome, trace_manager: TraceManager) -> None:
        """
        Locates the Greenhouse submit button and clicks it.
        """
        submit_sel = self.profile.get("submit_button", "css:#submit_app")
        by_type = By.CSS_SELECTOR if submit_sel.startswith("css:") else By.XPATH
        selector_val = submit_sel.split(":", 1)[1] if ":" in submit_sel else submit_sel

        with trace_manager.start_action("submit_form", {"selector": submit_sel}):
            element = driver.find_element(by_type, selector_val)
            human_click(driver, element)

    def verify_success(self, driver: webdriver.Remote | webdriver.Chrome, trace_manager: TraceManager) -> bool:
        """
        Checks success indicators in the page source or URL.
        """
        success_indicators = self.profile.get("success_indicators", [])
        end_time = time.time() + 10.0
        
        while time.time() < end_time:
            try:
                body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
                current_url = driver.current_url.lower()

                for indicator in success_indicators:
                    if indicator.lower() in body_text or indicator.lower() in current_url:
                        logger.info("integrations.greenhouse.success_matched", indicator=indicator)
                        return True
            except Exception as e:
                logger.warning("integrations.greenhouse.success_check_error", error=str(e))
                
            time.sleep(0.5)

        return False
