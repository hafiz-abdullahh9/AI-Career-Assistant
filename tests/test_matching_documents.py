"""
Member 3 — Job Matching Agent and Tools Tests
Tests all matching logic, scoring algorithms, and the Job Matching Agent.
"""

import os
import pytest
import pytest_asyncio
from datetime import datetime
from unittest.mock import patch, MagicMock

from models.matching_models import (
    SkillMatch,
    MatchResult,
    UserProfile,
    VerifiedJobListing,
    MatchWeightConfig,
    ResumeOutput,
)
from tools.document_tools import (
    find_skill_matches,
    extract_job_keywords,
    calculate_match_score,
    FactualAccuracyError,
)
from agents.job_matching_agent import match_jobs


# ============================================================================
# Tool Function Tests (T1 - T7, T14 - T20)
# ============================================================================

class TestSkillMatchingTools:
    """T1 - T7: Tests for find_skill_matches and keyword extraction."""

    def test_find_skill_matches_exact(self):
        """T1: Exact skill matches with confidence 1.0."""
        user_skills = ["Python", "Docker"]
        job_skills = ["Python"]
        matches = find_skill_matches(user_skills, job_skills)
        assert len(matches) == 1
        assert matches[0].user_skill == "Python"
        assert matches[0].job_skill == "Python"
        assert matches[0].match_type == "exact"
        assert matches[0].confidence == 1.0

    def test_find_skill_matches_synonyms(self):
        """T2: Synonym matches (JS/JavaScript) with confidence 0.8."""
        user_skills = ["JS"]
        job_skills = ["JavaScript"]
        matches = find_skill_matches(user_skills, job_skills)
        assert len(matches) == 1
        assert matches[0].user_skill == "JS"
        assert matches[0].job_skill == "JavaScript"
        assert matches[0].match_type == "similar"
        assert matches[0].confidence == 0.8

    def test_find_skill_matches_related(self):
        """T3: Related skills (React/Frontend Development) with confidence 0.5."""
        user_skills = ["React"]
        job_skills = ["Frontend Development"]
        matches = find_skill_matches(user_skills, job_skills)
        assert len(matches) == 1
        assert matches[0].user_skill == "React"
        assert matches[0].job_skill == "Frontend Development"
        assert matches[0].match_type == "related"
        assert matches[0].confidence == 0.5

    def test_find_skill_matches_no_match(self):
        """T4: Completely unrelated skills return empty list."""
        user_skills = ["Accounting"]
        job_skills = ["Python"]
        matches = find_skill_matches(user_skills, job_skills)
        assert len(matches) == 0

    def test_find_skill_matches_case_insensitive(self):
        """T5: Case-insensitive match ("python" vs "Python")."""
        user_skills = ["python"]
        job_skills = ["Python"]
        matches = find_skill_matches(user_skills, job_skills)
        assert len(matches) == 1
        assert matches[0].match_type == "exact"
        assert matches[0].confidence == 1.0

    def test_extract_job_keywords(self):
        """T6: Extract keywords from description."""
        desc = "Looking for a Python developer with AWS and Docker experience."
        keywords = extract_job_keywords(desc)
        # Should detect Python, AWS, Docker from our taxonomy
        assert "Python" in keywords
        assert "AWS" in keywords
        assert "Docker" in keywords

    def test_extract_job_keywords_empty(self):
        """T7: Empty description returns empty list."""
        keywords = extract_job_keywords("")
        assert keywords == []


class TestMatchScoreCalculatorTools:
    """T14 - T20: Tests for calculate_match_score tool."""

    def test_calculate_match_score_weights(self, profile_full, job_swe):
        """T14: Custom weights config is reflected in the final score."""
        custom_weights = MatchWeightConfig(
            skill_weight=0.80,
            experience_weight=0.05,
            location_weight=0.05,
            education_weight=0.05,
            preference_weight=0.05
        )
        res = calculate_match_score(profile_full, job_swe, custom_weights)
        assert res.overall_score > 0.0

    def test_calculate_match_score_perfect(self, profile_senior, job_senior_manager):
        """T15: Near perfect match scenario."""
        res = calculate_match_score(profile_senior, job_senior_manager)
        assert res.overall_score >= 80.0

    def test_calculate_match_score_zero(self, profile_career_changer, job_senior_manager):
        """T16: Very low match scenario (unrelated fields)."""
        res = calculate_match_score(profile_career_changer, job_senior_manager)
        assert res.overall_score < 50.0

    def test_calculate_match_score_partial(self, profile_full, job_swe):
        """T17: Partial match score is calculated correctly."""
        res = calculate_match_score(profile_full, job_swe)
        assert 50.0 <= res.overall_score <= 100.0

    def test_calculate_match_score_experience(self, profile_full, job_swe):
        """T18: Experience scoring calculation."""
        res = calculate_match_score(profile_full, job_swe)
        assert res.experience_match_score > 0.0

    def test_calculate_match_score_location(self, profile_full, job_swe):
        """T19: Location scoring calculation."""
        # Sarah is in San Francisco, CA. Job is in San Francisco, CA. Should be 100
        res = calculate_match_score(profile_full, job_swe)
        assert res.location_match_score == 100.0

    def test_calculate_match_score_education(self, profile_full, job_swe):
        """T20: Education scoring calculation."""
        # Sarah has BS in CS.
        res = calculate_match_score(profile_full, job_swe)
        assert res.education_match_score == 90.0  # BS (80) + CS relevant (10) = 90


# ============================================================================
# Job Matching Agent Tests (JM1 - JM15)
# ============================================================================

@pytest.mark.asyncio
class TestJobMatchingAgent:
    """JM1 - JM15: Tests for the Job Matching Agent & match_jobs batch function."""

    async def test_matching_valid_profile_valid_jobs(self, profile_full, jobs_batch):
        """JM1: Full profile matched against verified jobs returns list of results."""
        resp = await match_jobs(profile_full, jobs_batch[:5])
        assert resp.total_jobs_evaluated == 5
        assert len(resp.results) > 0
        assert isinstance(resp.results[0], MatchResult)

    async def test_matching_returns_ranked_results(self, profile_full, jobs_batch):
        """JM2: Results are sorted in descending order of overall_score."""
        resp = await match_jobs(profile_full, jobs_batch)
        scores = [r.overall_score for r in resp.results]
        assert scores == sorted(scores, reverse=True)
        assert resp.results[0].recommendation_rank == 1

    async def test_matching_exact_skill_match(self, profile_minimal, job_swe):
        """JM3: Exact skill match check."""
        resp = await match_jobs(profile_minimal, [job_swe])
        res = resp.results[0]
        assert "Python" in res.matched_skills

    async def test_matching_similar_skill_match(self, profile_full, job_devops):
        """JM4: Synonym/similar skill match check."""
        # User has "React", "Node.js", "Docker", "AWS", etc.
        # Job requires DevOps/Docker etc.
        resp = await match_jobs(profile_full, [job_devops])
        res = resp.results[0]
        # user has AWS, Docker, Git, REST API, etc.
        assert len(res.matched_skills) > 0

    async def test_matching_related_skill_match(self, profile_full, job_frontend):
        """JM5: Related skill match check."""
        resp = await match_jobs(profile_full, [job_frontend])
        res = resp.results[0]
        assert len(res.partial_matches) > 0

    async def test_matching_empty_profile_error(self, profile_empty_skills, job_swe):
        """JM6: Profile with no skills/experience raises ValueError."""
        # Note: profile_empty_skills has empty skills AND empty experience list
        with pytest.raises(ValueError):
            await match_jobs(profile_empty_skills, [job_swe])

    async def test_matching_no_verified_jobs(self, profile_full):
        """JM7: Empty job listing list returns empty results."""
        resp = await match_jobs(profile_full, [])
        assert resp.total_jobs_evaluated == 0
        assert len(resp.results) == 0

    async def test_matching_score_range_0_100(self, profile_full, jobs_batch):
        """JM8: All calculated scores are between 0 and 100."""
        resp = await match_jobs(profile_full, jobs_batch)
        for res in resp.results:
            assert 0.0 <= res.overall_score <= 100.0
            assert 0.0 <= res.skill_match_score <= 100.0
            assert 0.0 <= res.experience_match_score <= 100.0

    async def test_matching_precision_threshold(self, profile_senior, jobs_batch):
        """JM9: known correct matches rank highly. Precision@10 is satisfied."""
        resp = await match_jobs(profile_senior, jobs_batch)
        # Principal engineer Michael Rodriguez should match VP of Engineering or Cloud Architect best
        top_jobs = [r.job_id for r in resp.results]
        # job-003 is VP of Engineering. It should be in the top 3
        assert "job-003" in top_jobs[:3]

    async def test_matching_location_remote_preference(self, profile_full, job_frontend):
        """JM10: User with remote preference matching remote job."""
        # job_frontend location is Remote. profile_full preferred_job_types has remote.
        resp = await match_jobs(profile_full, [job_frontend])
        assert resp.results[0].location_match_score == 100.0

    async def test_matching_top_n_filtering(self, profile_full, jobs_batch):
        """JM11: Requests top N from a larger set."""
        resp = await match_jobs(profile_full, jobs_batch, top_n=5)
        assert len(resp.results) <= 5

    async def test_matching_score_breakdown_present(self, profile_full, job_swe):
        """JM12: Each match result contains all score breakdown sub-components."""
        resp = await match_jobs(profile_full, [job_swe])
        res = resp.results[0]
        assert res.skill_match_score >= 0.0
        assert res.experience_match_score >= 0.0
        assert res.location_match_score >= 0.0
        assert res.education_match_score >= 0.0
        assert res.preference_match_score >= 0.0

    async def test_matching_missing_skills_listed(self, profile_minimal, job_swe):
        """JM13: Missing skills are accurately listed."""
        # profile_minimal only has "Python". job_swe requires ["Python", "AWS", "Docker", "PostgreSQL", "REST API"].
        resp = await match_jobs(profile_minimal, [job_swe])
        res = resp.results[0]
        assert "AWS" in res.missing_skills
        assert "Docker" in res.missing_skills

    async def test_matching_api_failure_retry(self, profile_full, job_swe):
        """JM14: Fallback is activated when OpenAI API call fails."""
        # By patching OpenAI API call to raise an exception, we verify it falls back gracefully without crashing.
        with patch("openai.resources.chat.completions.Completions.create", side_effect=Exception("API Error")):
            resp = await match_jobs(profile_full, [job_swe])
            assert len(resp.results) == 1
            assert "match score" in resp.results[0].recommendation_reason

    async def test_matching_only_verified_jobs(self, profile_full, job_swe, job_rejected, job_flagged):
        """JM15: Mix of verified, rejected, and flagged jobs. Only verified are matched."""
        listings = [job_swe, job_rejected, job_flagged]
        resp = await match_jobs(profile_full, listings)
        assert resp.total_jobs_evaluated == 3
        assert resp.total_verified_jobs == 1
        assert len(resp.results) == 1
        assert resp.results[0].job_id == job_swe.job_id


# ============================================================================
# Resume Optimization Agent Tests (R1 - R15)
# ============================================================================

@pytest.mark.asyncio
class TestResumeAgent:
    """R1 - R15: Tests for the Resume Optimization Agent & generate_resume tool."""

    async def test_resume_generates_pdf(self, profile_full, job_swe):
        """R1: Tailored resume compiles successfully to PDF file."""
        from tools.document_tools import calculate_match_score
        from agents.resume_agent import optimize_resume
        import os
        
        match_result = calculate_match_score(profile_full, job_swe)
        output = await optimize_resume(profile_full, job_swe, match_result)
        
        assert os.path.exists(output.resume_file_path)
        assert output.resume_file_path.endswith(".pdf")

    async def test_resume_no_invented_skills(self, profile_full, job_swe):
        """R2: No skills are fabricated in the optimized resume."""
        from tools.document_tools import calculate_match_score, verify_factual_accuracy
        from agents.resume_agent import optimize_resume
        import pypdf
        
        match_result = calculate_match_score(profile_full, job_swe)
        output = await optimize_resume(profile_full, job_swe, match_result)
        
        reader = pypdf.PdfReader(output.resume_file_path)
        text = "\n".join(page.extract_text() for page in reader.pages)
        
        fact_check = verify_factual_accuracy(text, profile_full)
        assert fact_check.is_accurate is True
        assert len(fact_check.flagged_claims) == 0

    async def test_resume_no_invented_experience(self, profile_full, job_swe):
        """R3: Generated resume only references experiences present in profile."""
        from tools.document_tools import calculate_match_score, verify_factual_accuracy
        from agents.resume_agent import optimize_resume
        import pypdf
        
        match_result = calculate_match_score(profile_full, job_swe)
        output = await optimize_resume(profile_full, job_swe, match_result)
        
        reader = pypdf.PdfReader(output.resume_file_path)
        text = "\n".join(page.extract_text() for page in reader.pages)
        
        assert "FakeCorp" not in text
        assert "Stanford" in text or "TechCorp" in text

    async def test_resume_no_invented_achievements(self, profile_full, job_swe):
        """R4: No fabricated achievements or metrics."""
        from tools.document_tools import calculate_match_score
        from agents.resume_agent import optimize_resume
        import pypdf
        
        match_result = calculate_match_score(profile_full, job_swe)
        output = await optimize_resume(profile_full, job_swe, match_result)
        
        reader = pypdf.PdfReader(output.resume_file_path)
        text = "\n".join(page.extract_text() for page in reader.pages)
        
        assert "budget of $10M" not in text

    async def test_resume_no_invented_certifications(self, profile_full, job_swe):
        """R5: Certifications are constrained to those in the user profile."""
        from tools.document_tools import calculate_match_score
        from agents.resume_agent import optimize_resume
        import pypdf
        
        match_result = calculate_match_score(profile_full, job_swe)
        output = await optimize_resume(profile_full, job_swe, match_result)
        
        reader = pypdf.PdfReader(output.resume_file_path)
        text = "\n".join(page.extract_text() for page in reader.pages)
        
        assert "AWS Certified Developer Associate" in text
        assert "Certified Kubernetes Administrator" not in text

    async def test_resume_ats_no_images(self, profile_full, job_swe):
        """R6: PDF has no embedded images for ATS safety."""
        from tools.document_tools import calculate_match_score, check_ats_compatibility
        from agents.resume_agent import optimize_resume
        
        match_result = calculate_match_score(profile_full, job_swe)
        output = await optimize_resume(profile_full, job_swe, match_result)
        
        ats_res = check_ats_compatibility(output.resume_file_path)
        assert ats_res.score >= 90.0
        assert not any("image" in issue.lower() for issue in ats_res.issues_found)

    async def test_resume_ats_no_multicolumn(self, profile_full, job_swe):
        """R7: ATS checker validates single-column structure."""
        from tools.document_tools import calculate_match_score, check_ats_compatibility
        from agents.resume_agent import optimize_resume
        
        match_result = calculate_match_score(profile_full, job_swe)
        output = await optimize_resume(profile_full, job_swe, match_result)
        
        docx_path = output.resume_file_path.replace(".pdf", ".docx")
        ats_res = check_ats_compatibility(docx_path)
        assert not any("column" in issue.lower() for issue in ats_res.issues_found)

    async def test_resume_ats_standard_font(self, profile_full, job_swe):
        """R8: Fonts used are standard for ATS compliance."""
        from tools.document_tools import calculate_match_score, check_ats_compatibility
        from agents.resume_agent import optimize_resume
        
        match_result = calculate_match_score(profile_full, job_swe)
        output = await optimize_resume(profile_full, job_swe, match_result)
        
        ats_res = check_ats_compatibility(output.resume_file_path)
        assert not any("font" in issue.lower() for issue in ats_res.issues_found)

    async def test_resume_keyword_incorporation(self, profile_full, job_swe):
        """R9: Target job keywords are incorporated into the tailored summary."""
        from tools.document_tools import calculate_match_score
        from agents.resume_agent import optimize_resume
        
        match_result = calculate_match_score(profile_full, job_swe)
        output = await optimize_resume(profile_full, job_swe, match_result)
        
        report = output.keyword_incorporation_report
        assert report.total_job_keywords > 0
        assert "Python" in report.keywords_added
        assert report.incorporation_percentage > 0.0

    async def test_resume_keyword_report_accurate(self, profile_full, job_swe):
        """R10: Keyword incorporation report metrics are correct."""
        from tools.document_tools import calculate_match_score
        from agents.resume_agent import optimize_resume
        
        match_result = calculate_match_score(profile_full, job_swe)
        output = await optimize_resume(profile_full, job_swe, match_result)
        
        report = output.keyword_incorporation_report
        assert report.incorporated_keywords + len(report.keywords_not_applicable) == report.total_job_keywords

    async def test_resume_sections_present(self, profile_full, job_swe):
        """R11: Standard ATS resume sections are present."""
        from tools.document_tools import calculate_match_score
        from agents.resume_agent import optimize_resume
        import pypdf
        
        match_result = calculate_match_score(profile_full, job_swe)
        output = await optimize_resume(profile_full, job_swe, match_result)
        
        reader = pypdf.PdfReader(output.resume_file_path)
        text = "\n".join(page.extract_text() for page in reader.pages)
        
        assert "Summary" in text
        assert "Experience" in text
        assert "Education" in text
        assert "Skills" in text

    async def test_resume_section_reordering(self, profile_full, job_swe):
        """R12: Tailored summary is placed at the top."""
        from tools.document_tools import calculate_match_score
        from agents.resume_agent import optimize_resume
        import pypdf
        
        match_result = calculate_match_score(profile_full, job_swe)
        output = await optimize_resume(profile_full, job_swe, match_result)
        
        reader = pypdf.PdfReader(output.resume_file_path)
        text = "\n".join(page.extract_text() for page in reader.pages)
        
        assert text.find("Summary") < text.find("Experience")

    async def test_resume_minimal_profile(self, profile_minimal, job_swe):
        """R13: Optimization succeeds even with minimal profile info."""
        from tools.document_tools import calculate_match_score
        from agents.resume_agent import optimize_resume
        import os
        
        match_result = calculate_match_score(profile_minimal, job_swe)
        output = await optimize_resume(profile_minimal, job_swe, match_result)
        
        assert os.path.exists(output.resume_file_path)
        assert output.ats_compatibility_score >= 80.0

    async def test_resume_missing_cv_error(self, profile_empty_skills, job_swe):
        """R14: Empty profile raises ValueError when trying to optimize."""
        from tools.document_tools import calculate_match_score
        from agents.resume_agent import optimize_resume
        
        with pytest.raises(ValueError):
            match_result = calculate_match_score(profile_empty_skills, job_swe)
            await optimize_resume(profile_empty_skills, job_swe, match_result)

    async def test_resume_pdf_render_failure_fallback(self, profile_full, job_swe):
        """R15: Render failure gracefully falls back to docx output path."""
        from tools.document_tools import calculate_match_score
        from agents.resume_agent import optimize_resume
        
        match_result = calculate_match_score(profile_full, job_swe)
        with patch("tools.document_tools.render_pdf", side_effect=ValueError("Render Error")):
            output = await optimize_resume(profile_full, job_swe, match_result)
            assert output.resume_file_path.endswith(".docx")
            assert os.path.exists(output.resume_file_path)


# ============================================================================
# Cover Letter Agent Tests (CL1 - CL15)
# ============================================================================

@pytest.mark.asyncio
class TestCoverLetterAgent:
    """CL1 - CL15: Tests for the Cover Letter Agent & generate_cover_letter tool."""

    async def test_cover_letter_generates_file(self, profile_full, job_swe):
        """CL1: Valid inputs generate cover letter file at output path."""
        from tools.document_tools import calculate_match_score, generate_resume
        from agents.cover_letter_agent import optimize_cover_letter
        
        match_res = calculate_match_score(profile_full, job_swe)
        res_output = generate_resume(profile_full, job_swe, match_res)
        
        output = await optimize_cover_letter(profile_full, job_swe, match_res, res_output)
        
        assert os.path.exists(output.cover_letter_file_path)
        assert output.cover_letter_file_path.endswith(".pdf")

    async def test_cover_letter_personalized_with_company(self, profile_full, job_swe):
        """CL2: Cover letter is personalized with company info when provided."""
        from tools.document_tools import calculate_match_score, generate_resume
        from agents.cover_letter_agent import optimize_cover_letter
        from models.matching_models import CompanyInfo
        import pypdf
        
        match_res = calculate_match_score(profile_full, job_swe)
        res_output = generate_resume(profile_full, job_swe, match_res)
        
        company = CompanyInfo(
            name="TechCorp Solutions",
            mission="Empower engineers to build robust software systems",
            culture_values=["integrity", "continuous learning"],
            industry="Software Engineering"
        )
        
        output = await optimize_cover_letter(profile_full, job_swe, match_res, res_output, company_info=company)
        
        assert output.company_info_used is True
        assert output.personalization_score > 70.0
        
        reader = pypdf.PdfReader(output.cover_letter_file_path)
        text = "\n".join(page.extract_text() for page in reader.pages)
        
        assert "TechCorp Solutions" in text
        assert "Empower engineers" in text or "continuous learning" in text or "integrity" in text

    async def test_cover_letter_generic_without_company(self, profile_full, job_swe):
        """CL3: Cover letter degrades gracefully to generic letter without company info."""
        from tools.document_tools import calculate_match_score, generate_resume
        from agents.cover_letter_agent import optimize_cover_letter
        import pypdf
        
        match_res = calculate_match_score(profile_full, job_swe)
        res_output = generate_resume(profile_full, job_swe, match_res)
        
        output = await optimize_cover_letter(profile_full, job_swe, match_res, res_output, company_info=None)
        
        assert output.company_info_used is False
        assert output.personalization_score <= 75.0
        
        reader = pypdf.PdfReader(output.cover_letter_file_path)
        text = "\n".join(page.extract_text() for page in reader.pages)
        
        assert job_swe.company_name in text
        assert "mission" not in text.lower()

    async def test_cover_letter_keyword_inclusion(self, profile_full, job_swe):
        """CL4: Verify that cover letter keyword inclusion percentage is >= 80%."""
        from tools.document_tools import calculate_match_score, generate_resume
        from agents.cover_letter_agent import optimize_cover_letter
        
        # Modify job to only require skills candidate has, to achieve >= 80% keyword match
        job_matched = job_swe.model_copy()
        job_matched.required_skills = ["Python", "AWS", "Docker"]
        job_matched.preferred_skills = []
        job_matched.description = "We are looking for a Python developer with AWS and Docker experience."
        
        match_res = calculate_match_score(profile_full, job_matched)
        res_output = generate_resume(profile_full, job_matched, match_res)
        
        output = await optimize_cover_letter(profile_full, job_matched, match_res, res_output)
        
        assert output.keyword_match_percentage >= 80.0

    async def test_cover_letter_professional_tone_tech(self, profile_full, job_swe):
        """CL5: Cover letter tone is appropriate for technology industry roles."""
        from tools.document_tools import calculate_match_score, generate_resume
        from agents.cover_letter_agent import optimize_cover_letter
        import pypdf
        
        match_res = calculate_match_score(profile_full, job_swe)
        res_output = generate_resume(profile_full, job_swe, match_res)
        
        output = await optimize_cover_letter(profile_full, job_swe, match_res, res_output)
        
        reader = pypdf.PdfReader(output.cover_letter_file_path)
        text = "\n".join(page.extract_text() for page in reader.pages)
        
        assert output.tone == "professional"
        assert "strong interest" in text or "contribution" in text

    async def test_cover_letter_professional_tone_finance(self, profile_full, job_swe):
        """CL6: Tone is formal/professional for a finance/management listing."""
        from tools.document_tools import calculate_match_score, generate_resume
        from agents.cover_letter_agent import optimize_cover_letter
        import pypdf
        
        job_fin = job_swe.model_copy()
        job_fin.job_title = "Finance Manager"
        job_fin.company_name = "Goldman Sachs"
        
        match_res = calculate_match_score(profile_full, job_fin)
        res_output = generate_resume(profile_full, job_fin, match_res)
        
        output = await optimize_cover_letter(profile_full, job_fin, match_res, res_output)
        
        reader = pypdf.PdfReader(output.cover_letter_file_path)
        text = "\n".join(page.extract_text() for page in reader.pages)
        
        assert "Dear Hiring Team" in text or "Sincerely" in text

    async def test_cover_letter_no_resume_duplication(self, profile_full, job_swe):
        """CL7: Cover letter does not duplicate the resume summary word-for-word."""
        from tools.document_tools import calculate_match_score, generate_resume
        from agents.cover_letter_agent import optimize_cover_letter
        import pypdf
        
        match_res = calculate_match_score(profile_full, job_swe)
        res_output = generate_resume(profile_full, job_swe, match_res)
        
        output = await optimize_cover_letter(profile_full, job_swe, match_res, res_output)
        
        reader = pypdf.PdfReader(output.cover_letter_file_path)
        text = "\n".join(page.extract_text() for page in reader.pages)
        
        assert text != profile_full.summary
        assert len(text) > len(profile_full.summary or "")

    async def test_cover_letter_structure_complete(self, profile_full, job_swe):
        """CL8: Cover letter structure contains all standard elements."""
        from tools.document_tools import calculate_match_score, generate_resume
        from agents.cover_letter_agent import optimize_cover_letter
        import pypdf
        
        match_res = calculate_match_score(profile_full, job_swe)
        res_output = generate_resume(profile_full, job_swe, match_res)
        
        output = await optimize_cover_letter(profile_full, job_swe, match_res, res_output)
        
        reader = pypdf.PdfReader(output.cover_letter_file_path)
        text = "\n".join(page.extract_text() for page in reader.pages)
        
        assert profile_full.full_name in text
        assert profile_full.email in text
        assert "Dear" in text
        assert "Sincerely" in text or "Thank you" in text

    async def test_cover_letter_factual_accuracy(self, profile_full, job_swe):
        """CL9: Assert cover letter is 100% factually accurate, referencing only true facts."""
        from tools.document_tools import calculate_match_score, generate_resume, verify_factual_accuracy
        from agents.cover_letter_agent import optimize_cover_letter
        import pypdf
        
        match_res = calculate_match_score(profile_full, job_swe)
        res_output = generate_resume(profile_full, job_swe, match_res)
        
        output = await optimize_cover_letter(profile_full, job_swe, match_res, res_output)
        
        reader = pypdf.PdfReader(output.cover_letter_file_path)
        text = "\n".join(page.extract_text() for page in reader.pages)
        
        fact_check = verify_factual_accuracy(text, profile_full)
        assert fact_check.is_accurate is True
        assert len(fact_check.flagged_claims) == 0

    async def test_cover_letter_contact_info_present(self, profile_full, job_swe):
        """CL10: Candidate's contact info is present in the cover letter header."""
        from tools.document_tools import calculate_match_score, generate_resume
        from agents.cover_letter_agent import optimize_cover_letter
        import pypdf
        
        match_res = calculate_match_score(profile_full, job_swe)
        res_output = generate_resume(profile_full, job_swe, match_res)
        
        output = await optimize_cover_letter(profile_full, job_swe, match_res, res_output)
        
        reader = pypdf.PdfReader(output.cover_letter_file_path)
        text = "\n".join(page.extract_text() for page in reader.pages)
        
        assert profile_full.full_name in text
        assert profile_full.email in text
        if profile_full.phone:
            assert profile_full.phone in text

    async def test_cover_letter_job_title_referenced(self, profile_full, job_swe):
        """CL11: Specifically references the job title in the opening block."""
        from tools.document_tools import calculate_match_score, generate_resume
        from agents.cover_letter_agent import optimize_cover_letter
        import pypdf
        
        match_res = calculate_match_score(profile_full, job_swe)
        res_output = generate_resume(profile_full, job_swe, match_res)
        
        output = await optimize_cover_letter(profile_full, job_swe, match_res, res_output)
        
        reader = pypdf.PdfReader(output.cover_letter_file_path)
        text = "\n".join(page.extract_text() for page in reader.pages)
        
        assert job_swe.job_title in text

    async def test_cover_letter_minimal_profile(self, profile_minimal, job_swe):
        """CL12: Minimal profile does not crash generation and returns valid cover letter."""
        from tools.document_tools import calculate_match_score, generate_resume
        from agents.cover_letter_agent import optimize_cover_letter
        
        match_res = calculate_match_score(profile_minimal, job_swe)
        res_output = generate_resume(profile_minimal, job_swe, match_res)
        
        output = await optimize_cover_letter(profile_minimal, job_swe, match_res, res_output)
        
        assert os.path.exists(output.cover_letter_file_path)
        assert output.cover_letter_file_path.endswith(".pdf")

    async def test_cover_letter_coordinates_with_resume(self, profile_full, job_swe):
        """CL13: Cover letter references coordinates (such as match score) from resume/matching output."""
        from tools.document_tools import calculate_match_score, generate_resume
        from agents.cover_letter_agent import optimize_cover_letter
        import pypdf
        
        match_res = calculate_match_score(profile_full, job_swe)
        res_output = generate_resume(profile_full, job_swe, match_res)
        
        output = await optimize_cover_letter(profile_full, job_swe, match_res, res_output)
        
        reader = pypdf.PdfReader(output.cover_letter_file_path)
        text = "\n".join(page.extract_text() for page in reader.pages)
        
        assert f"{match_res.overall_score:.1f}%" in text or f"{match_res.overall_score:.0f}%" in text

    async def test_cover_letter_api_failure_retry(self, profile_full, job_swe):
        """CL14: When API fails, falls back gracefully to rule-based generation."""
        from tools.document_tools import calculate_match_score, generate_resume
        from agents.cover_letter_agent import optimize_cover_letter
        
        match_res = calculate_match_score(profile_full, job_swe)
        res_output = generate_resume(profile_full, job_swe, match_res)
        
        with patch("openai.resources.chat.completions.Completions.create", side_effect=Exception("API Call Failed")):
            output = await optimize_cover_letter(profile_full, job_swe, match_res, res_output)
            assert os.path.exists(output.cover_letter_file_path)
            assert output.keyword_match_percentage >= 0.0

    async def test_cover_letter_low_keyword_regenerate(self, profile_full, job_swe):
        """CL15: Triggers regeneration when first generation is missing keywords."""
        from tools.document_tools import calculate_match_score, generate_resume
        from agents.cover_letter_agent import optimize_cover_letter
        
        # Prepare job with simple keywords
        job_matched = job_swe.model_copy()
        job_matched.required_skills = ["Python", "AWS", "Docker"]
        job_matched.preferred_skills = []
        job_matched.description = "Looking for Python, AWS, and Docker developer."
        
        match_res = calculate_match_score(profile_full, job_matched)
        res_output = generate_resume(profile_full, job_matched, match_res)
        
        mock_choice_keywords = MagicMock()
        mock_choice_keywords.message.content = '["Python", "AWS", "Docker"]'
        mock_resp_keywords = MagicMock()
        mock_resp_keywords.choices = [mock_choice_keywords]
        
        mock_choice_1 = MagicMock()
        mock_choice_1.message.content = "Dear Hiring Team,\n\nI am applying for Software Engineer. I am a programmer. Sincerely, Sarah."
        mock_resp_1 = MagicMock()
        mock_resp_1.choices = [mock_choice_1]
        
        mock_choice_2 = MagicMock()
        mock_choice_2.message.content = (
            "Dear Hiring Team at TechCorp,\n\nI am applying for Software Engineer. "
            "I have experience with Python, AWS, Docker. Sincerely, Sarah."
        )
        mock_resp_2 = MagicMock()
        mock_resp_2.choices = [mock_choice_2]
        
        mock_choice_fact = MagicMock()
        mock_choice_fact.message.content = '{"is_accurate": true, "total_claims_checked": 5, "verified_claims": 5, "flagged_claims": []}'
        mock_resp_fact = MagicMock()
        mock_resp_fact.choices = [mock_choice_fact]
        
        with patch("tools.document_tools.OPENAI_API_KEY", "mock-key"):
            with patch("openai.resources.chat.completions.Completions.create", side_effect=[mock_resp_keywords, mock_resp_1, mock_resp_2, mock_resp_fact]) as mock_openai:
                output = await optimize_cover_letter(profile_full, job_matched, match_res, res_output)
                assert mock_openai.call_count == 4
                assert output.keyword_match_percentage >= 80.0
