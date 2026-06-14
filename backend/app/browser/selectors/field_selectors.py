from typing import Dict, List, Optional, Tuple
from selenium.webdriver.common.by import By

class FieldSelectors:
    """
    Encapsulates selector mapping strategy for form field auto-discovery.
    Supports high-priority custom selectors and fallback dynamic patterns.
    """

    DEFAULT_PATTERNS: Dict[str, List[str]] = {
        "first_name": ["first_name", "firstname", "fname", "given_name"],
        "last_name":  ["last_name", "lastname", "lname", "family_name"],
        "full_name":  ["name", "fullname", "full_name", "applicant_name", "your_name"],
        "email":      ["email", "email_address", "applicant_email"],
        "phone":      ["phone", "telephone", "mobile", "phone_number"],
        "resume_file":["resume", "cv", "resume_file", "attachment", "document"],
        "cover_letter":["cover_letter", "coverletter", "message", "letter", "personal_statement"],
        "linkedin":   ["linkedin", "linkedin_url", "linkedin_profile"],
        "portfolio":  ["portfolio", "website", "github", "personal_website"],
    }

    def __init__(self, custom_selectors: Optional[Dict[str, str]] = None) -> None:
        """
        Args:
            custom_selectors: Dict mapping standard field keys to locator strings,
                              e.g., {"email": "css:#input-email", "resume_file": "xpath://input[@name='resume']"}
        """
        self.custom_selectors = custom_selectors or {}
        self.patterns = self.DEFAULT_PATTERNS.copy()

    def get_locator(self, field_key: str) -> Optional[Tuple[By, str]]:
        """
        Returns a Selenium locator tuple (By, selector_string) if a custom selector is configured.
        """
        locator_str = self.custom_selectors.get(field_key)
        if not locator_str:
            return None
            
        if locator_str.startswith("css:"):
            return By.CSS_SELECTOR, locator_str[4:]
        elif locator_str.startswith("xpath:"):
            return By.XPATH, locator_str[6:]
        elif locator_str.startswith("id:"):
            return By.ID, locator_str[3:]
        elif locator_str.startswith("name:"):
            return By.NAME, locator_str[5:]
        
        # Default fallback to CSS
        return By.CSS_SELECTOR, locator_str
