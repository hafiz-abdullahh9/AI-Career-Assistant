from pydantic import BaseModel, Field
from typing import Dict, Optional

class FormFieldMapping(BaseModel):
    """
    Schema for mapping standard application fields to site-specific CSS/XPath selectors.
    """
    custom_selectors: Dict[str, str] = Field(
        default_factory=dict,
        description="Dict mapping field names (e.g. email) to selectors (e.g. 'css:#email')"
    )

class AutomationOutcome(BaseModel):
    """
    Result returned by the form automation service.
    """
    success: bool
    confirmation_id: Optional[str] = None
    message: str
    screenshot_url: Optional[str] = None
    latency_ms: float
