from selenium import webdriver
from app.browser.drivers.driver_factory import BrowserDriverFactory
import structlog

logger = structlog.get_logger(__name__)

class BrowserManager:
    """
    Manages browser session lifecycle: startup, teardown, timeouts, cleanup, and crash recovery.
    """

    def __init__(self, headless: bool = True, window_size: str = "1920,1080", grid_url: str = None) -> None:
        self.headless = headless
        self.window_size = window_size
        self.grid_url = grid_url
        self._driver: webdriver.Remote | webdriver.Chrome | None = None

    def start_session(self) -> webdriver.Remote | webdriver.Chrome:
        """
        Starts a new Chrome WebDriver session.
        If a session is already active and healthy, returns it.
        """
        if self._driver:
            if self.is_healthy():
                return self._driver
            else:
                logger.warning("browser.session.unhealthy", message="Recycling unhealthy browser session")
                self.close_session()

        try:
            self._driver = BrowserDriverFactory.create_driver(
                headless=self.headless,
                window_size=self.window_size,
                grid_url=self.grid_url
            )
            return self._driver
        except Exception as e:
            logger.error("browser.session.startup_failed", error=str(e))
            self._driver = None
            raise

    def close_session(self) -> None:
        """
        Safely shuts down the current WebDriver session.
        """
        if self._driver:
            try:
                self._driver.quit()
            except Exception as e:
                logger.warning("browser.session.teardown_error", error=str(e))
            finally:
                self._driver = None
                logger.info("browser.session.closed")

    def is_healthy(self) -> bool:
        """
        Checks if the browser session is still active and responsive.
        """
        if not self._driver:
            return False
        try:
            # Simple query to check if the driver responds
            _ = self._driver.current_url
            return True
        except Exception:
            return False

    def recover_session(self) -> webdriver.Remote | webdriver.Chrome:
        """
        Force-quits the current session and starts a new one.
        """
        logger.info("browser.session.recovering")
        self.close_session()
        return self.start_session()
