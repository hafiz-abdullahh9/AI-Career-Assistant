import os
import time
from typing import Optional, List, Dict, Any

class ScreenshotStore:
    """
    Manages capturing, logging, and rotating screenshots during form automation tasks.
    Maintains a maximum limit of screenshots, rotating out the oldest to control storage growth.
    """
    def __init__(self, base_dir: Optional[str] = None, max_screenshots: int = 20) -> None:
        if base_dir is None:
            # Check environment or default to a directory in current folder
            base_dir = os.environ.get("ANTIGRAVITY_ARTIFACTS_DIR") or os.path.join(os.getcwd(), "screenshots")
        self.base_dir = os.path.abspath(base_dir)
        self.max_screenshots = max_screenshots
        self.captured_logs: List[Dict[str, Any]] = []

        # Ensure directory exists
        os.makedirs(self.base_dir, exist_ok=True)

    def capture(self, driver: Any, session_id: str, trigger: str) -> str:
        """
        Captures a screenshot, saves it to disk, and updates the tracking log.
        Rotates oldest screenshots if max_screenshots limit is reached.
        """
        timestamp = int(time.time() * 1000)
        filename = f"{session_id}_{timestamp}_{trigger}.png"
        filepath = os.path.join(self.base_dir, filename)

        try:
            driver.save_screenshot(filepath)
        except Exception as e:
            # If the driver cannot save the screenshot (e.g. session closed), raise or handle
            raise e

        log_entry = {
            "session_id": session_id,
            "trigger": trigger,
            "timestamp": timestamp,
            "path": filepath
        }
        self.captured_logs.append(log_entry)

        # Enforce rotation limits
        while len(self.captured_logs) > self.max_screenshots:
            oldest = self.captured_logs.pop(0)
            old_path = oldest.get("path")
            if old_path and os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except Exception:
                    pass

        return filepath
