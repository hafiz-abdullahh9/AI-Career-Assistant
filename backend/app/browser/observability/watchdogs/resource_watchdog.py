import time
import structlog
from typing import Optional
from selenium.common.exceptions import WebDriverException

logger = structlog.get_logger(__name__)

class BrowserResourceWatchdog:
    """
    Monitors browser liveness, session duration limits, and tab responsiveness.
    Enforces policies to prevent runaway Chrome processes and hung execution states.
    """

    def __init__(self, max_duration_sec: float = 120.0) -> None:
        self.max_duration_sec = max_duration_sec
        self.start_time = time.time()

    def check_health(self, driver) -> bool:
        """
        Executes a series of light diagnostics to verify the driver and browser state.
        Returns True if healthy; raises ValueError or WebDriverException on watchdog violation.
        """
        if not driver:
            logger.warning("observability.watchdog.no_driver")
            return False

        # 1. Session Duration Check
        elapsed = time.time() - self.start_time
        if elapsed > self.max_duration_sec:
            logger.error("observability.watchdog.duration_exceeded", elapsed=elapsed, max_limit=self.max_duration_sec)
            raise ValueError(f"Browser session exceeded max allowed duration of {self.max_duration_sec}s (Elapsed: {elapsed:.2f}s)")

        # 2. Chromedriver Liveness Check
        try:
            # Check the process state if it is a local service process
            service = getattr(driver, "service", None)
            if service and service.process:
                poll_result = service.process.poll()
                if poll_result is not None and isinstance(poll_result, int):
                    logger.error("observability.watchdog.chromedriver_dead", exit_code=poll_result)
                    raise WebDriverException(f"Chromedriver service process exited unexpectedly with code {poll_result}")
        except AttributeError:
            pass

        # 3. Browser Responsiveness Check (runs lightweight JS check)
        start_check = time.time()
        try:
            # We set a script timeout for this lightweight call, but wait, driver.execute_script
            # is blocking. Since script timeout is 30s, let's run it.
            result = driver.execute_script("return document.readyState")
            check_duration = time.time() - start_check
            logger.info("observability.watchdog.responsiveness_check", doc_ready=result, duration_sec=check_duration)
            if result != "complete":
                # ReadyState might not be complete if the page is still loading, that's fine,
                # but if it fails to respond at all it throws an exception.
                pass
        except Exception as e:
            logger.error("observability.watchdog.unresponsive", error=str(e))
            raise WebDriverException(f"Browser tab is unresponsive: {e}")

        return True
