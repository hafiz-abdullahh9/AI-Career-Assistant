"""
Member 3 — Pydantic Data Models
All data models for Job Matching, Resume Optimization, and Cover Letter Generation.

Models are organized into:
  - Input Models (consumed from Member 1 & Member 2)
  - Output Models (produced by Member 3 agents)
  - Configuration Models
  - Error Models
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# Input Models — consumed from upstream members
# ============================================================================


class ExperienceEntry(BaseModel):
    """A single work experience entry from the user's profile."""
    title: str
    company: str
    location: Optional[str] = None
    start_date: str                          # ISO format
    end_date: Optional[str] = None           # None if current position
    description: str
    skills_used: List[str] = Field(default_factory=list)


class EducationEntry(BaseModel):
    """A single education entry from the user's profile."""
    degree: str
    institution: str
    field_of_study: str
    start_date: str
    end_date: Optional[str] = None
    gpa: Optional[float] = Field(default=None, ge=0.0, le=4.0)


class UserProfile(BaseModel):
    """
    User profile consumed from Member 1's Profile Context.
    Contains all user data needed for matching, resume, and cover letter generation.
    """
    user_id: str
    full_name: str
    email: str
    phone: Optional[str] = None
    location: str
    summary: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    experience: List[ExperienceEntry] = Field(default_factory=list)
    education: List[EducationEntry] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    goals: Optional[str] = None
    preferred_locations: List[str] = Field(default_factory=list)
    preferred_job_types: List[str] = Field(default_factory=list)
    resume_raw_text: Optional[str] = None
    resume_file_path: Optional[str] = None

    @field_validator("preferred_job_types", mode="before")
    @classmethod
    def validate_job_types(cls, v: List[str]) -> List[str]:
        allowed = {"full-time", "part-time", "contract", "internship", "remote"}
        for jt in v:
            if jt.lower() not in allowed:
                raise ValueError(
                    f"Invalid job type '{jt}'. Allowed: {allowed}"
                )
        return [jt.lower() for jt in v]


class VerifiedJobListing(BaseModel):
    """
    Verified job listing consumed from Member 2's output.
    Only listings with verified_status='verified' are used for matching.
    """
    job_id: str
    company_name: str
    job_title: str
    description: str
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: Optional[List[str]] = None
    location: str
    salary: Optional[str] = None
    job_type: Optional[str] = None            # full-time, part-time, contract, internship
    experience_level: Optional[str] = None    # entry, mid, senior
    application_deadline: Optional[str] = None
    contact_info: Optional[str] = None
    application_url: Optional[str] = None
    posted_date: str
    verified_status: str = "verified"
    source_platform: str = "linkedin"

    @field_validator("verified_status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"verified", "rejected", "flagged_for_review"}
        if v not in allowed:
            raise ValueError(
                f"Invalid verified_status '{v}'. Allowed: {allowed}"
            )
        return v


# ============================================================================
# Output Models — produced by Member 3 agents
# ============================================================================


class SkillMatch(BaseModel):
    """A single skill match result between a user skill and a job skill."""
    user_skill: str
    job_skill: str
    match_type: str                           # "exact" | "similar" | "related"
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("match_type")
    @classmethod
    def validate_match_type(cls, v: str) -> str:
        allowed = {"exact", "similar", "related"}
        if v not in allowed:
            raise ValueError(
                f"Invalid match_type '{v}'. Allowed: {allowed}"
            )
        return v


class MatchResult(BaseModel):
    """
    Result of matching a user profile against a single job listing.
    Contains overall score, sub-component scores, and skill breakdown.
    """
    user_id: str
    job_id: str
    overall_score: float = Field(ge=0.0, le=100.0)
    skill_match_score: float = Field(ge=0.0, le=100.0)
    experience_match_score: float = Field(ge=0.0, le=100.0)
    location_match_score: float = Field(ge=0.0, le=100.0)
    education_match_score: float = Field(ge=0.0, le=100.0)
    preference_match_score: float = Field(ge=0.0, le=100.0)
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    partial_matches: List[SkillMatch] = Field(default_factory=list)
    recommendation_rank: int = Field(ge=1)
    recommendation_reason: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MatchWeightConfig(BaseModel):
    """
    Configurable weights for the job matching scoring algorithm.
    All weights must sum to 1.0.
    """
    skill_weight: float = Field(default=0.40, ge=0.0, le=1.0)
    experience_weight: float = Field(default=0.25, ge=0.0, le=1.0)
    location_weight: float = Field(default=0.15, ge=0.0, le=1.0)
    education_weight: float = Field(default=0.10, ge=0.0, le=1.0)
    preference_weight: float = Field(default=0.10, ge=0.0, le=1.0)

    def total_weight(self) -> float:
        return (
            self.skill_weight
            + self.experience_weight
            + self.location_weight
            + self.education_weight
            + self.preference_weight
        )

    @field_validator("preference_weight")
    @classmethod
    def validate_weights_sum(cls, v: float, info) -> float:
        """Validate after all fields are set — weights must sum to 1.0."""
        data = info.data
        total = (
            data.get("skill_weight", 0.40)
            + data.get("experience_weight", 0.25)
            + data.get("location_weight", 0.15)
            + data.get("education_weight", 0.10)
            + v
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"Weights must sum to 1.0, got {total:.6f}"
            )
        return v


class KeywordReport(BaseModel):
    """Report on keyword incorporation into a generated document."""
    total_job_keywords: int = Field(ge=0)
    incorporated_keywords: int = Field(ge=0)
    incorporation_percentage: float = Field(ge=0.0, le=100.0)
    keywords_added: List[str] = Field(default_factory=list)
    keywords_not_applicable: List[str] = Field(default_factory=list)


class ResumeOutput(BaseModel):
    """
    Output of the Resume Optimization Agent.
    Contains the generated resume file path and quality metrics.
    """
    user_id: str
    job_id: str
    resume_file_path: str
    ats_compatibility_score: float = Field(ge=0.0, le=100.0)
    keyword_incorporation_report: KeywordReport
    sections_modified: List[str] = Field(default_factory=list)
    factual_accuracy_verified: bool = True     # MUST always be True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CoverLetterOutput(BaseModel):
    """
    Output of the Cover Letter Agent.
    Contains the generated cover letter file path and quality metrics.
    """
    user_id: str
    job_id: str
    cover_letter_file_path: str
    tone: str = "professional"
    keyword_match_percentage: float = Field(ge=0.0, le=100.0)
    personalization_score: float = Field(ge=0.0, le=100.0)
    company_info_used: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CompanyInfo(BaseModel):
    """Optional company information for cover letter personalization."""
    name: str
    industry: Optional[str] = None
    size: Optional[str] = None               # "startup", "mid", "enterprise"
    mission: Optional[str] = None
    recent_news: Optional[str] = None
    culture_values: Optional[List[str]] = None
    website: Optional[str] = None


# ============================================================================
# Error / Result Models
# ============================================================================


class FactualAccuracyResult(BaseModel):
    """Result of factual accuracy verification on generated content."""
    is_accurate: bool
    total_claims_checked: int = Field(ge=0)
    verified_claims: int = Field(ge=0)
    flagged_claims: List[str] = Field(default_factory=list)
    accuracy_percentage: float = Field(ge=0.0, le=100.0)
    details: Optional[str] = None


class ATSCompatibilityResult(BaseModel):
    """Result of ATS compatibility check on a generated document."""
    score: float = Field(ge=0.0, le=100.0)
    is_compatible: bool = True
    issues_found: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class AgentErrorResponse(BaseModel):
    """Structured error response format conforming to Tool Interface Spec."""
    success: bool = False
    error_code: str
    message: str
    details: Optional[Dict] = None
    retryable: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# Batch / Ranking Models
# ============================================================================


class MatchingBatchRequest(BaseModel):
    """Request for batch matching a user against multiple jobs."""
    user_profile: UserProfile
    job_listings: List[VerifiedJobListing]
    weight_config: Optional[MatchWeightConfig] = None
    top_n: int = Field(default=10, ge=1, le=100)


class MatchingBatchResponse(BaseModel):
    """Response for batch matching — ranked list of match results."""
    user_id: str
    total_jobs_evaluated: int
    total_verified_jobs: int
    results: List[MatchResult]
    created_at: datetime = Field(default_factory=datetime.utcnow)
