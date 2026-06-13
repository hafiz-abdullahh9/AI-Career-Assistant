import os
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
import structlog

from app.browser.observability.tracing.trace_tracker import TraceManager
from app.browser.forms.form_automation import human_type, human_click, select_dropdown_value

logger = structlog.get_logger(__name__)

class BaseIntegrationAdapter(ABC):
    """
    Abstract Base class for all integration adapters.
    Enforces a strict deny-by-default execution policy.
    """
    
    @property
    @abstractmethod
    def supported_domains(self) -> List[str]:
        """
        List of domains this adapter is designed to support.
        e.g., ["greenhouse.io"]
        """
        pass

    @property
    @abstractmethod
    def profile_name(self) -> str:
        """
        The key name of the profile config JSON (e.g. 'greenhouse')
        """
        pass

    def __init__(self) -> None:
        self.profile = self.load_profile()

    def load_profile(self) -> Dict[str, Any]:
        """
        Loads the data-driven profile configuration for this domain.
        """
        if not self.profile_name:
            return {}
        
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        profile_path = os.path.join(base_dir, "profiles", f"{self.profile_name}.json")
        
        if not os.path.exists(profile_path):
            logger.warning("integrations.adapter.profile_missing", path=profile_path)
            return {}
            
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("integrations.adapter.profile_load_failed", path=profile_path, error=str(e))
            return {}

    def get_selector(self, field_key: str) -> Optional[Tuple[str, str]]:
        """
        Resolves selector strategy and locator string for a given field key from the profile.
        Returns (By.CSS_SELECTOR/By.XPATH, selector_string) or None.
        """
        selectors = self.profile.get("selectors", {})
        selector_info = selectors.get(field_key)
        if not selector_info:
            return None
            
        # Supports both simple string "css:#id" or dict {"type": "css", "value": "#id"}
        if isinstance(selector_info, dict):
            sel_type = selector_info.get("type", "css").lower()
            sel_val = selector_info.get("value", "")
        elif isinstance(selector_info, str) and ":" in selector_info:
            sel_type, sel_val = selector_info.split(":", 1)
        else:
            return None

        by_type = By.CSS_SELECTOR if sel_type == "css" else By.XPATH
        return by_type, sel_val

    @abstractmethod
    def fill_fields(self, driver: webdriver.Remote | webdriver.Chrome, field_data: Dict[str, Any], trace_manager: TraceManager) -> None:
        """
        Fills the form inputs using the loaded profile or custom logic.
        """
        pass

    @abstractmethod
    def upload_files(self, driver: webdriver.Remote | webdriver.Chrome, file_uploads: Dict[str, str], trace_manager: TraceManager) -> None:
        """
        Uploads required files (e.g. resumes, cover letters).
        """
        pass

    @abstractmethod
    def submit_form(self, driver: webdriver.Remote | webdriver.Chrome, trace_manager: TraceManager) -> None:
        """
        Locates and triggers form submission.
        """
        pass

    @abstractmethod
    def verify_success(self, driver: webdriver.Remote | webdriver.Chrome, trace_manager: TraceManager) -> bool:
        """
        Verifies that form was submitted successfully.
        """
        pass
