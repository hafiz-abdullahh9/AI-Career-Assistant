import os
import tempfile
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, WebDriverException

from app.browser.drivers.driver_factory import BrowserDriverFactory
from app.browser.sessions.session_manager import BrowserManager
from app.browser.selectors.field_selectors import FieldSelectors
from app.browser.uploads.upload_handler import UploadHandler
from app.browser.services.browser_service import FormAutomationService
from app.browser.schemas.browser_schemas import AutomationOutcome
from app.core.exceptions import InvalidAttachmentError

# --- Basic Foundation & Factory Tests ---

def test_driver_factory_build_chrome_options():
    options = BrowserDriverFactory.build_chrome_options(headless=True, window_size="1280,720")
    assert "--headless=new" in options.arguments
    assert "--window-size=1280,720" in options.arguments
    assert "--no-sandbox" in options.arguments
    assert "--disable-gpu" in options.arguments

def test_field_selectors_default_patterns():
    selectors = FieldSelectors()
    assert "firstname" in selectors.patterns["first_name"]
    assert "lname" in selectors.patterns["last_name"]
    assert "cv" in selectors.patterns["resume_file"]

def test_field_selectors_custom_locator():
    custom = {
        "email": "css:#special-email",
        "phone": "xpath://input[@type='tel']",
        "first_name": "id:first-name-input",
        "last_name": "name:lname_field",
        "portfolio": "normal-css-selector"
    }
    selectors = FieldSelectors(custom_selectors=custom)
    
    assert selectors.get_locator("email") == (By.CSS_SELECTOR, "#special-email")
    assert selectors.get_locator("phone") == (By.XPATH, "//input[@type='tel']")
    assert selectors.get_locator("first_name") == (By.ID, "first-name-input")
    assert selectors.get_locator("last_name") == (By.NAME, "lname_field")
    assert selectors.get_locator("portfolio") == (By.CSS_SELECTOR, "normal-css-selector")
    assert selectors.get_locator("non_existent") is None

# --- Session Manager Tests ---

def test_session_manager_lifecycle():
    manager = BrowserManager(headless=True)
    
    # Assert start session works
    driver = manager.start_session()
    assert driver is not None
    assert manager.is_healthy() is True
    
    # Close session
    manager.close_session()
    assert manager.is_healthy() is False
    assert manager._driver is None

def test_session_manager_recovery():
    manager = BrowserManager(headless=True)
    driver1 = manager.start_session()
    assert driver1 is not None
    
    # Recover session restarts driver
    driver2 = manager.recover_session()
    assert driver2 is not None
    assert driver1 != driver2
    
    manager.close_session()

# --- Upload Handler Tests ---

@pytest.mark.asyncio
async def test_upload_handler_download_and_validation():
    handler = UploadHandler()
    
    # Mock download file
    mock_pdf_content = b"%PDF-1.4 mock pdf content metadata sample content"
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_response = MagicMock()
        mock_response.content = mock_pdf_content
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        # Test download valid PDF
        local_path = await handler.download_file("https://storage/resume.pdf", "resume.pdf")
        assert os.path.exists(local_path)
        assert local_path.endswith("resume.pdf")
        
        # Test validation fails on invalid mime / invalid content
        with pytest.raises(InvalidAttachmentError):
            await handler.download_file("https://storage/resume.docx", "resume.docx")
            
        # Cleanup should clean up downloaded temp files
        handler.cleanup()
        assert not os.path.exists(local_path)

# --- Service Form Automation Sandbox Tests ---

@pytest.mark.asyncio
async def test_automate_form_sandbox_success():
    manager = BrowserManager(headless=True)
    service = FormAutomationService(manager)
    
    # Construct offline local sandbox page file:// URL
    sandbox_path = os.path.abspath("tests/resources/sandbox_form.html")
    sandbox_url = f"file:///{sandbox_path.replace(os.sep, '/')}"
    
    # Setup test input data
    field_data = {
        "first_name": "Jane",
        "last_name": "Smith",
        "email": "jane.smith@example.com",
        "phone": "+1987654321",
        "linkedin": "https://linkedin.com/in/janesmith",
        "portfolio": "https://janesmith.github.io",
        "gender": "female",
        "terms": True,
        "cover_letter": "I would love to join your amazing team and build awesome features."
    }
    
    # Mock resume file download content
    mock_pdf_content = b"%PDF-1.4 mock pdf content metadata sample content for test"
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_response = MagicMock()
        mock_response.content = mock_pdf_content
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        file_uploads = {
            "resume_file": {
                "url": "https://mock-storage/jane_cv.pdf",
                "filename": "jane_cv.pdf"
            }
        }
        
        # Execute automated submission
        outcome = await service.automate_form(
            url=sandbox_url,
            field_data=field_data,
            file_uploads=file_uploads,
            success_indicators=["Application Submitted"]
        )
        
        # Verify outcome
        assert outcome.success is True
        assert outcome.confirmation_id is not None
        assert outcome.confirmation_id.startswith("CONF-")
        assert outcome.message == "Form submitted successfully"
        assert outcome.screenshot_url is not None
        assert os.path.exists(outcome.screenshot_url)
        assert outcome.latency_ms > 0
        
        # Verify screenshot is cleaned up or persists
        if os.path.exists(outcome.screenshot_url):
            try:
                os.remove(outcome.screenshot_url)
            except OSError:
                pass

@pytest.mark.asyncio
async def test_automate_form_sandbox_missing_element():
    manager = BrowserManager(headless=True)
    service = FormAutomationService(manager)
    
    sandbox_path = os.path.abspath("tests/resources/sandbox_form.html")
    sandbox_url = f"file:///{sandbox_path.replace(os.sep, '/')}"
    
    # Provide data for a field key that has no match in form mapping
    field_data = {
        "non_existent_field_key": "some value"
    }
    
    outcome = await service.automate_form(
        url=sandbox_url,
        field_data=field_data,
        file_uploads={},
        success_indicators=["Application Submitted"]
    )
    
    assert outcome.success is False
    assert "Could not locate form element for field key" in outcome.message
    assert outcome.screenshot_url is not None
    assert os.path.exists(outcome.screenshot_url)
    
    if os.path.exists(outcome.screenshot_url):
        try:
            os.remove(outcome.screenshot_url)
        except OSError:
            pass
