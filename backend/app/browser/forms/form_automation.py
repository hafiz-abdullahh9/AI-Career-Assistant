import random
import time
from selenium import webdriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import Select
import structlog

logger = structlog.get_logger(__name__)

def human_type(element: WebElement, text: str, min_delay: float = 0.05, max_delay: float = 0.15) -> None:
    """
    Clears the input element and types the text character-by-character with random delays.
    """
    element.clear()
    time.sleep(0.1)
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(min_delay, max_delay))

def human_click(driver: webdriver.Remote | webdriver.Chrome, element: WebElement) -> None:
    """
    Scrolls the element into view, pauses briefly to simulate user hesitation/reading, and clicks it.
    """
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    time.sleep(random.uniform(0.3, 0.8))
    element.click()
    time.sleep(random.uniform(0.2, 0.5))

def select_dropdown_value(element: WebElement, value: str) -> None:
    """
    Selects a value in a standard HTML dropdown select element.
    """
    select = Select(element)
    try:
        select.select_by_value(value)
    except Exception:
        try:
            select.select_by_visible_text(value)
        except Exception as e:
            logger.warning("browser.form.dropdown_select_failed", value=value, error=str(e))
            raise
