import os
import time
import json
import structlog
from typing import Dict, Any, Optional, List
from app.browser.observability.schemas.trace_schemas import BrowserActionTrace, BrowserSessionTelemetry

logger = structlog.get_logger(__name__)

class ActionContext:
    """
    Context manager that automatically tracks starting/ending time,
    duration, outcome status, and selector context for a single browser step.
    """
    def __init__(self, manager: "TraceManager", action_name: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self.manager = manager
        self.action_name = action_name
        self.metadata = metadata or {}
        self.start_time = 0.0

    def __enter__(self) -> "ActionContext":
        self.start_time = time.time()
        # Trigger hooks if configured
        self.manager.trigger_hooks("step_start", self.action_name, metadata=self.metadata)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        end_time = time.time()
        duration_ms = (end_time - self.start_time) * 1000
        status = "success" if exc_type is None else "failed"
        err_msg = str(exc_val) if exc_val else None

        trace = BrowserActionTrace(
            session_id=self.manager.session_id,
            task_id=self.manager.task_id,
            action_name=self.action_name,
            selector_used=self.metadata.get("selector_used"),
            selector_type=self.metadata.get("selector_type"),
            start_time=self.start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            status=status,
            error_context=err_msg,
            metadata=self.metadata
        )
        self.manager.record_action(trace)

        if status == "success":
            self.manager.trigger_hooks("step_success", self.action_name, duration_ms=duration_ms, metadata=self.metadata)
        else:
            self.manager.trigger_hooks("step_failure", self.action_name, error_message=err_msg, metadata=self.metadata)


class TraceManager:
    """
    Manages browser session tracing, structured metrics logging, and debug artifact persistence.
    """

    def __init__(self, session_id: str, task_id: Optional[str] = None, base_dir: Optional[str] = None) -> None:
        self.session_id = session_id
        self.task_id = task_id
        if not base_dir:
            artifacts_env = os.environ.get("ANTIGRAVITY_ARTIFACTS_DIR")
            if artifacts_env:
                base_dir = os.path.join(artifacts_env, "traces")
            else:
                base_dir = os.path.join(os.getcwd(), "storage", "traces")
        self.base_dir = os.path.abspath(base_dir)
        self.telemetry = BrowserSessionTelemetry(
            session_id=session_id,
            task_id=task_id,
            start_time=time.time()
        )
        self._hooks: Dict[str, List[Any]] = {
            "step_start": [],
            "step_success": [],
            "step_failure": []
        }
        os.makedirs(self.base_dir, exist_ok=True)

    def start_action(self, action_name: str, metadata: Optional[Dict[str, Any]] = None) -> ActionContext:
        """
        Returns a context manager to instrument a single browser step.
        """
        return ActionContext(self, action_name, metadata)

    def record_action(self, trace: BrowserActionTrace) -> None:
        """
        Appends an action trace, updates session-level status, and increments selector fallback counts.
        """
        self.telemetry.actions.append(trace)
        if trace.selector_type == "fallback_xpath":
            self.telemetry.fallback_selectors_count += 1
        if trace.status == "failed":
            self.telemetry.success = False
            self.telemetry.error_reason = trace.error_context

    def register_hook(self, event_type: str, callback: Any) -> None:
        """
        Registers a callback callable for a given lifecycle event type.
        """
        if event_type in self._hooks:
            self._hooks[event_type].append(callback)

    def trigger_hooks(self, event_type: str, action_name: str, **kwargs) -> None:
        """
        Executes all hooks registered to the given event type.
        """
        for callback in self._hooks.get(event_type, []):
            try:
                callback(action_name, **kwargs)
            except Exception as e:
                logger.warning("observability.trace.hook_error", event_type=event_type, error=str(e))

    def save_debug_report(self, driver, html_source: Optional[str] = None) -> str:
        """
        Saves structured telemetry trace (.json) and current page source (.html) to the persistence store.
        """
        self.telemetry.end_time = time.time()
        self.telemetry.total_duration_ms = (self.telemetry.end_time - self.telemetry.start_time) * 1000

        # Attempt to capture current state from driver
        if driver:
            if not html_source:
                try:
                    html_source = driver.page_source
                except Exception:
                    pass
            # Fetch page details for context
            try:
                self.telemetry.system_metrics["current_url"] = driver.current_url
                self.telemetry.system_metrics["page_title"] = driver.title
            except Exception:
                pass

        report_id = f"trace_{self.session_id}_{int(self.telemetry.start_time)}"
        json_path = os.path.join(self.base_dir, f"{report_id}.json")

        try:
            # Save Telemetry Trace
            with open(json_path, "w", encoding="utf-8") as f:
                f.write(self.telemetry.model_dump_json(indent=2))

            # Save Page Source Dump
            if html_source:
                html_path = os.path.join(self.base_dir, f"{report_id}.html")
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_source)
                logger.info("observability.trace.debug_report_saved", json=json_path, html=html_path)
            else:
                logger.info("observability.trace.debug_report_saved", json=json_path)
                
            return json_path
        except Exception as e:
            logger.error("observability.trace.save_report_failed", error=str(e))
            raise
