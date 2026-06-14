"""
Pydantic schemas for structured job data and verification results validation.
"""

from pydantic import BaseModel, Field
from typing import List, Optional

class ScrapedJobSchema(BaseModel):
    """Schema for a standardised raw scraped job record."""
    job_id: str
    platform: str
    title: str
    company: str
    description: str
    required_skills: List[str] = Field(default_factory=list)
    location: str
    salary: Optional[str] = ""
    job_type: Optional[str] = ""
    date_posted: Optional[str] = ""
    application_deadline: Optional[str] = ""
    contact_info: Optional[str] = ""
    apply_link: str
    source_url: str
    scraped_at: str

class JobEnhancement(BaseModel):
    """Schema for LLM-enhanced job properties."""
    required_skills: List[str]
    salary_range: Optional[str] = None
    experience_level: str
    job_category: str
    is_remote: bool

class JobVerificationLLMOutput(BaseModel):
    """Schema for LLM-based verification decisions."""
    is_legitimate: bool
    confidence: float
    verdict: str
    explanation: str

class CompanyVerificationSchema(BaseModel):
    """Schema for company legitimacy metrics."""
    company_name: str
    is_verified: bool
    confidence: float
    flags: List[str]
    verification_method: str

class ExpiryCheckSchema(BaseModel):
    """Schema for expiry check output."""
    is_expired: bool
    expiry_reason: str
    days_since_posted: Optional[int] = None
    days_until_deadline: Optional[int] = None

class SuspicionCheckSchema(BaseModel):
    """Schema for suspicion analysis output."""
    is_suspicious: bool
    suspicion_score: float
    flags: List[str]

class VerificationDetailsSchema(BaseModel):
    """Combined validation details structure."""
    company_verification: CompanyVerificationSchema
    expiry_check: ExpiryCheckSchema
    suspicion_check: SuspicionCheckSchema
    is_duplicate: bool
    duplicate_of: str
    duplicate_reason: str
    llm_analysis: Optional[JobVerificationLLMOutput] = None
    llm_used: Optional[bool] = False
    error: Optional[str] = None
    note: Optional[str] = None

class VerifiedJobSchema(BaseModel):
    """Complete verified job structure."""
    job_id: str
    platform: str
    title: str
    company: str
    description: str
    required_skills: List[str]
    location: str
    salary: Optional[str] = ""
    job_type: Optional[str] = ""
    date_posted: Optional[str] = ""
    application_deadline: Optional[str] = ""
    contact_info: Optional[str] = ""
    apply_link: str
    source_url: str
    scraped_at: str
    verified_status: str  # "verified" | "rejected" | "flagged_for_review"
    verification_details: VerificationDetailsSchema
