from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional

class EmailAttachment(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    content: bytes
    mime_type: str = Field(..., min_length=3, max_length=100)


class EmailMetadata(BaseModel):
    application_id: Optional[str] = None
    user_id: Optional[str] = None
    job_id: Optional[str] = None
    provider: Optional[str] = None


class EmailRequest(BaseModel):
    to_email: EmailStr
    subject: str = Field(..., min_length=1, max_length=500)
    body_text: str = Field(..., min_length=1)
    body_html: Optional[str] = None
    attachments: List[EmailAttachment] = Field(default_factory=list)
    metadata: EmailMetadata = Field(default_factory=EmailMetadata)


class EmailResponse(BaseModel):
    success: bool = True
    message_id: Optional[str] = None
    message: str
    provider: str
    latency_ms: float
    timestamp: float


class EmailFailure(BaseModel):
    success: bool = False
    error_code: str
    error_message: str
    provider: str
    retryable: bool
    latency_ms: float
    timestamp: float
