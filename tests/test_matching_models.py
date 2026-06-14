"""
Member 3 — Model Validation Tests
Tests all Pydantic models for correct validation, serialization, and edge cases.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from models.matching_models import (
    ATSCompatibilityResult,
    AgentErrorResponse,
    CompanyInfo,
    CoverLetterOutput,
    EducationEntry,
    ExperienceEntry,
    FactualAccuracyResult,
    KeywordReport,
    MatchResult,
    MatchWeightConfig,
    MatchingBatchRequest,
    MatchingBatchResponse,
    ResumeOutput,
    SkillMatch,
    UserProfile,
    VerifiedJobListing,
)


class TestMatchResult:
    """Tests for MatchResult model."""

    def test_match_result_valid(self, profile_full, job_swe):
        """M1: Create MatchResult with valid data."""
        result = MatchResult(
            user_id=profile_full.user_id,
            job_id=job_swe.job_id,
            overall_score=85.5,
            skill_match_score=90.0,
            experience_match_score=80.0,
            location_match_score=100.0,
            education_match_score=75.0,
            preference_match_score=85.0,
            matched_skills=["Python", "AWS"],
            missing_skills=["Docker"],
            partial_matches=[],
            recommendation_rank=1,
            recommendation_reason="Strong skill match",
        )
        assert result.overall_score == 85.5
        assert result.user_id == "user-001"
        assert result.job_id == "job-001"

    def test_match_result_score_bounds_low(self):
        """M2a: Score below 0 should raise ValidationError."""
        with pytest.raises(ValidationError):
            MatchResult(
                user_id="u1", job_id="j1",
                overall_score=-1.0,
                skill_match_score=0.0, experience_match_score=0.0,
                location_match_score=0.0, education_match_score=0.0,
                preference_match_score=0.0,
                recommendation_rank=1,
            )

    def test_match_result_score_bounds_high(self):
        """M2b: Score above 100 should raise ValidationError."""
        with pytest.raises(ValidationError):
            MatchResult(
                user_id="u1", job_id="j1",
                overall_score=101.0,
                skill_match_score=0.0, experience_match_score=0.0,
                location_match_score=0.0, education_match_score=0.0,
                preference_match_score=0.0,
                recommendation_rank=1,
            )

    def test_match_result_serialization(self, profile_full, job_swe):
        """M3: Serialize/deserialize to JSON — round-trip matches."""
        result = MatchResult(
            user_id=profile_full.user_id,
            job_id=job_swe.job_id,
            overall_score=75.0,
            skill_match_score=80.0, experience_match_score=70.0,
            location_match_score=60.0, education_match_score=85.0,
            preference_match_score=90.0,
            matched_skills=["Python"],
            missing_skills=["Docker"],
            recommendation_rank=1,
            recommendation_reason="Good fit",
        )
        json_str = result.model_dump_json()
        restored = MatchResult.model_validate_json(json_str)
        assert restored.overall_score == result.overall_score
        assert restored.user_id == result.user_id
        assert restored.matched_skills == result.matched_skills


class TestSkillMatch:
    """Tests for SkillMatch model."""

    def test_skill_match_valid_types(self):
        """M4: All three match types accepted."""
        for mt in ["exact", "similar", "related"]:
            sm = SkillMatch(
                user_skill="Python", job_skill="Python",
                match_type=mt, confidence=0.8,
            )
            assert sm.match_type == mt

    def test_skill_match_invalid_type(self):
        """M5: Invalid match_type string raises ValidationError."""
        with pytest.raises(ValidationError):
            SkillMatch(
                user_skill="Python", job_skill="Python",
                match_type="unknown", confidence=0.8,
            )

    def test_skill_match_confidence_bounds(self):
        """Confidence outside 0-1 should raise ValidationError."""
        with pytest.raises(ValidationError):
            SkillMatch(
                user_skill="Python", job_skill="Python",
                match_type="exact", confidence=1.5,
            )


class TestResumeOutput:
    """Tests for ResumeOutput model."""

    def test_resume_output_required_fields(self):
        """M6: Missing required fields raises ValidationError."""
        with pytest.raises(ValidationError):
            ResumeOutput(
                user_id="u1",
                # missing: job_id, resume_file_path, ats_compatibility_score, keyword_incorporation_report
            )

    def test_resume_output_valid(self):
        """Valid ResumeOutput with all required fields."""
        report = KeywordReport(
            total_job_keywords=10, incorporated_keywords=8,
            incorporation_percentage=80.0,
            keywords_added=["Python", "AWS"],
            keywords_not_applicable=["Go"],
        )
        output = ResumeOutput(
            user_id="u1", job_id="j1",
            resume_file_path="/outputs/resumes/u1_j1.pdf",
            ats_compatibility_score=95.0,
            keyword_incorporation_report=report,
            sections_modified=["Summary", "Experience"],
        )
        assert output.factual_accuracy_verified is True
        assert output.ats_compatibility_score == 95.0


class TestCoverLetterOutput:
    """Tests for CoverLetterOutput model."""

    def test_cover_letter_output_valid(self):
        """M7: All fields populated correctly."""
        output = CoverLetterOutput(
            user_id="u1", job_id="j1",
            cover_letter_file_path="/outputs/cover_letters/u1_j1.pdf",
            tone="professional",
            keyword_match_percentage=85.0,
            personalization_score=70.0,
            company_info_used=True,
        )
        assert output.tone == "professional"
        assert output.company_info_used is True


class TestKeywordReport:
    """Tests for KeywordReport model."""

    def test_keyword_report_percentage(self):
        """M8: Calculate incorporation percentage."""
        report = KeywordReport(
            total_job_keywords=10,
            incorporated_keywords=8,
            incorporation_percentage=80.0,
            keywords_added=["Python", "AWS", "Docker", "SQL", "REST", "Git", "Agile", "Cloud"],
            keywords_not_applicable=["Go", "Rust"],
        )
        assert report.incorporation_percentage == 80.0
        assert len(report.keywords_added) == 8


class TestUserProfile:
    """Tests for UserProfile model."""

    def test_user_profile_optional_fields(self):
        """M9: Profile with only required fields validates."""
        profile = UserProfile(
            user_id="u1",
            full_name="Test User",
            email="test@example.com",
            location="Anywhere",
        )
        assert profile.phone is None
        assert profile.summary is None
        assert profile.skills == []

    def test_user_profile_invalid_job_type(self):
        """Invalid job type raises ValidationError."""
        with pytest.raises(ValidationError):
            UserProfile(
                user_id="u1", full_name="Test",
                email="t@t.com", location="A",
                preferred_job_types=["invalid_type"],
            )


class TestVerifiedJobListing:
    """Tests for VerifiedJobListing model."""

    def test_verified_job_listing_status(self):
        """M10: All three verified_status values accepted."""
        for status in ["verified", "rejected", "flagged_for_review"]:
            listing = VerifiedJobListing(
                job_id="j1", company_name="Co", job_title="SWE",
                description="Test", location="NYC",
                posted_date="2026-01-01", verified_status=status,
                source_platform="linkedin",
            )
            assert listing.verified_status == status

    def test_verified_job_listing_invalid_status(self):
        """Invalid verified_status raises ValidationError."""
        with pytest.raises(ValidationError):
            VerifiedJobListing(
                job_id="j1", company_name="Co", job_title="SWE",
                description="Test", location="NYC",
                posted_date="2026-01-01", verified_status="invalid",
                source_platform="linkedin",
            )


class TestMatchWeightConfig:
    """Tests for MatchWeightConfig model."""

    def test_match_weight_config_defaults(self):
        """M11: Default weights sum to 1.0."""
        config = MatchWeightConfig()
        assert abs(config.total_weight() - 1.0) < 1e-9

    def test_match_weight_config_invalid_sum(self):
        """Weights that don't sum to 1.0 raise ValidationError."""
        with pytest.raises(ValidationError):
            MatchWeightConfig(
                skill_weight=0.5,
                experience_weight=0.5,
                location_weight=0.5,
                education_weight=0.5,
                preference_weight=0.5,
            )


class TestExperienceEntry:
    """Tests for ExperienceEntry model."""

    def test_experience_entry_current_job(self):
        """M12: end_date = None for current position validates."""
        entry = ExperienceEntry(
            title="Engineer", company="Corp",
            start_date="2022-01-01", end_date=None,
            description="Working here currently.",
        )
        assert entry.end_date is None


class TestFactualAccuracyResult:
    """Tests for FactualAccuracyResult model."""

    def test_factual_accuracy_result_pass(self):
        """M13a: Passing accuracy state."""
        result = FactualAccuracyResult(
            is_accurate=True,
            total_claims_checked=10, verified_claims=10,
            accuracy_percentage=100.0,
        )
        assert result.is_accurate is True
        assert result.flagged_claims == []

    def test_factual_accuracy_result_fail(self):
        """M13b: Failing accuracy state."""
        result = FactualAccuracyResult(
            is_accurate=False,
            total_claims_checked=10, verified_claims=8,
            flagged_claims=["Invented skill: Kubernetes", "Invented cert: PMP"],
            accuracy_percentage=80.0,
        )
        assert result.is_accurate is False
        assert len(result.flagged_claims) == 2


class TestATSCompatibilityResult:
    """Tests for ATSCompatibilityResult model."""

    def test_ats_compatibility_result(self):
        """M14: Score + issues list validates."""
        result = ATSCompatibilityResult(
            score=85.0,
            is_compatible=False,
            issues_found=["Multi-column layout detected", "Image found on page 1"],
            recommendations=["Use single-column layout", "Remove all images"],
        )
        assert result.score == 85.0
        assert len(result.issues_found) == 2


class TestCompanyInfo:
    """Tests for CompanyInfo model."""

    def test_company_info_optional(self):
        """M15: CompanyInfo with all fields optional except name."""
        info = CompanyInfo(name="TestCorp")
        assert info.industry is None
        assert info.size is None
        assert info.culture_values is None

    def test_company_info_full(self):
        """CompanyInfo with all fields populated."""
        info = CompanyInfo(
            name="TechCo", industry="Technology", size="enterprise",
            mission="To innovate", recent_news="Series D funded",
            culture_values=["Innovation", "Teamwork"], website="https://techco.com",
        )
        assert info.name == "TechCo"
        assert len(info.culture_values) == 2
