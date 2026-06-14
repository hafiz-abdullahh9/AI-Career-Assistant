from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class BrowserActionTrace(BaseModel):
    """
    Structured trace for a single browser interaction (action).
    """
    session_id: str
    task_id: Optional[str] = None
    action_name: str  # e.g., "click", "type", "upload", "navigate", "select"
    selector_used: Optional[str] = None
    selector_type: Optional[str] = None  # "custom", "matched_attribute", "matched_label", "fallback_xpath"
    start_time: float
    end_time: Optional[float] = None
    duration_ms: float = 0.0
    status: str  # "success", "failed"
    error_context: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class BrowserSessionTelemetry(BaseModel):
    """
    Aggregated telemetry for an entire browser automation session.
    """
    session_id: str
    task_id: Optional[str] = None
    start_time: float
    end_time: Optional[float] = None
    total_duration_ms: float = 0.0
    actions: List[BrowserActionTrace] = Field(default_factory=list)
    success: bool = True
    error_reason: Optional[str] = None
    fallback_selectors_count: int = 0
    screenshots: List[Dict[str, Any]] = Field(default_factory=list)  # List of {"path": str, "trigger": str, "timestamp": float}
    system_metrics: Dict[str, Any] = Field(default_factory=dict)
