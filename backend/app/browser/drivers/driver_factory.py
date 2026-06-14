import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import structlog

logger = structlog.get_logger(__name__)

class BrowserDriverFactory:
    """
    Factory for producing standard Chrome WebDriver instances.
    """

    @staticmethod
    def build_chrome_options(headless: bool = True, window_size: str = "1920,1080") -> Options:
        options = Options()
        
        if headless:
            options.add_argument("--headless=new")
            
        options.add_argument(f"--window-size={window_size}")
        
        # Performance/stability settings
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-blink-features=AutomationControlled")
        
        return options

    @staticmethod
    def create_driver(
        headless: bool = True, 
        window_size: str = "1920,1080", 
        grid_url: str = None
    ) -> webdriver.Remote | webdriver.Chrome:
        """
        Creates and returns a Chrome WebDriver instance.
        If grid_url is provided, connects to a Selenium Grid via webdriver.Remote.
        Otherwise, downloads and uses a local Chrome WebDriver via webdriver-manager.
        """
        options = BrowserDriverFactory.build_chrome_options(headless=headless, window_size=window_size)
        
        if grid_url:
            logger.info("browser.driver.creating_remote", grid_url=grid_url)
            driver = webdriver.Remote(
                command_executor=grid_url,
                options=options
            )
        else:
            logger.info("browser.driver.creating_local")
            import time
            start_time = time.time()
            raw_path = ChromeDriverManager().install()
            driver_path = raw_path
            
            # webdriver-manager sometimes returns text files (like THIRD_PARTY_NOTICES) or directories.
            # We resolve the actual chromedriver executable path under the resolved folder.
            exe_name = "chromedriver.exe" if os.name == "nt" else "chromedriver"
            if not raw_path.lower().endswith(exe_name):
                # If it's a file, try checking its parent folder for chromedriver.exe
                if os.path.isfile(raw_path):
                    parent_dir = os.path.dirname(raw_path)
                else:
                    parent_dir = raw_path
                
                candidate = os.path.join(parent_dir, exe_name)
                if os.path.exists(candidate):
                    driver_path = candidate
                else:
                    # Look recursively in parent directories
                    found = False
                    for root, _, files in os.walk(parent_dir):
                        if exe_name in files:
                            driver_path = os.path.join(root, exe_name)
                            found = True
                            break
                    if not found:
                        logger.warning("browser.driver.executable_not_found_in_parent", parent_dir=parent_dir)
            
            logger.info(
                "browser.driver.resolved_path", 
                path=driver_path, 
                headless=headless, 
                window_size=window_size,
                arguments=options.arguments
            )
            
            service = Service(executable_path=driver_path)
            
            try:
                driver = webdriver.Chrome(service=service, options=options)
                startup_duration = time.time() - start_time
                logger.info("browser.driver.started", duration_sec=startup_duration)
            except Exception as e:
                logger.error("browser.driver.failed_startup", error=str(e))
                raise
            
        # Set explicit and safe timeouts
        driver.set_page_load_timeout(30)
        driver.set_script_timeout(30)
        driver.implicitly_wait(0)  # Standard: 0 implicit wait to avoid query latency bottlenecks
        
        return driver
