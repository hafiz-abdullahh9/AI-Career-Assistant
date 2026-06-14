from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def wait_for_element_visible(
    driver: webdriver.Remote | webdriver.Chrome, 
    locator: tuple, 
    timeout: float = 10.0
) -> WebElement:
    """
    Waits until the element located by locator is visible on the page.
    """
    return WebDriverWait(driver, timeout).until(EC.visibility_of_element_located(locator))

def wait_for_element_clickable(
    driver: webdriver.Remote | webdriver.Chrome, 
    locator: tuple, 
    timeout: float = 10.0
) -> WebElement:
    """
    Waits until the element located by locator is clickable.
    """
    return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable(locator))
