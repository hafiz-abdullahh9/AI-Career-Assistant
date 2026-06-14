"""
Unit tests for Job Scraping Agent and Job Verification Agent.

Test Plan (>= 10 cases per agent):
  - Job Scraping Agent: 12 test cases
  - Job Verification Agent: 14 test cases
  Total: 26 test cases

All tests validate:
  - Valid JSON output for all inputs
  - No unhandled exceptions
  - Correct field extraction and standardisation
  - Duplicate detection accuracy across LinkedIn + Indeed mixed datasets
  - >= 95% accuracy filtering invalid listings (per SRS 5.3)
  - Environment variables used for credentials — no hardcoded keys
"""

import pytest
import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

# ── Imports from project ──
from tools.scraping_tools import (
    _clean_html,
    _normalize_relative_date,
    _parse_job_type,
    _generate_job_id,
    _standardise_job_record,
    _is_valid_url,
    _extract_salary,
    _extract_deadline,
    _extract_contact_info,
    _extract_required_skills,
    _canonical_indeed_url,
    _build_indeed_search_url,
    _parse_indeed_search_results,
    _has_indeed_next_page,
)
from tools.verification_tools import (
    verify_company,
    detect_duplicates,
    check_expired_posting,
    flag_suspicious_listing,
)
from agents.job_scraping_agent import JobScrapingAgent
from agents.job_verification_agent import JobVerificationAgent


# ═══════════════════════════════════════════════════════════════════
#  FIXTURES — Sample job data
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_indeed_job():
    """A valid Indeed job listing."""
    return {
        "job_id": "abc123def456",
        "platform": "indeed",
        "title": "Senior Python Developer",
        "company": "TechCorp Pakistan",
        "description": (
            "We are looking for an experienced Python developer with 5+ years of experience. "
            "Required skills: Python, Django, REST API, PostgreSQL, Docker. "
            "Salary: PKR 200,000 - 350,000/month. "
            "Deadline: December 31, 2026. "
            "Contact: hr@techcorp.pk"
        ),
        "required_skills": ["Python", "Django", "REST API", "PostgreSQL", "Docker"],
        "location": "Lahore, Pakistan",
        "salary": "PKR 200,000 - 350,000/month",
        "job_type": "Full-time",
        "date_posted": (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d"),
        "application_deadline": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
        "contact_info": "hr@techcorp.pk",
        "apply_link": "https://pk.indeed.com/viewjob?jk=abc123",
        "source_url": "https://pk.indeed.com/viewjob?jk=abc123",
        "scraped_at": datetime.now().isoformat(),
    }


@pytest.fixture
def sample_linkedin_job():
    """A valid LinkedIn job listing."""
    return {
        "job_id": "xyz789ghi012",
        "platform": "linkedin",
        "title": "Senior Python Developer",
        "company": "TechCorp Pakistan",
        "description": (
            "Looking for a senior Python developer. Must know Python, Django, and databases. "
            "Competitive salary offered."
        ),
        "required_skills": ["Python", "Django"],
        "location": "Lahore, Pakistan",
        "salary": "",
        "job_type": "Full-time",
        "date_posted": (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d"),
        "application_deadline": "",
        "contact_info": "",
        "apply_link": "https://www.linkedin.com/jobs/view/123456",
        "source_url": "https://www.linkedin.com/jobs/view/123456",
        "scraped_at": datetime.now().isoformat(),
    }


@pytest.fixture
def suspicious_job():
    """A suspicious job listing that should be flagged."""
    return {
        "job_id": "sus001",
        "platform": "indeed",
        "title": "EARN $5000 PER WEEK - No Experience Needed!!!",
        "company": "",
        "description": (
            "GUARANTEED INCOME!!! Send money via wire transfer to start. "
            "Processing fee of $200 required. NO EXPIRIENCE NEEDED! "
            "Upfront payment for training materials. Contact us NOW!!!"
        ),
        "required_skills": [],
        "location": "",
        "salary": "$5000/week",
        "job_type": "",
        "date_posted": "",
        "application_deadline": "",
        "contact_info": "scammer@gmail.com",
        "apply_link": "javascript:alert('xss')",
        "source_url": "https://pk.indeed.com/viewjob?jk=fake123",
        "scraped_at": datetime.now().isoformat(),
    }


@pytest.fixture
def expired_job():
    """An expired job listing."""
    return {
        "job_id": "exp001",
        "platform": "indeed",
        "title": "Data Analyst",
        "company": "Analytics Corp",
        "description": "Looking for a data analyst.",
        "required_skills": [],
        "location": "Karachi",
        "salary": "",
        "job_type": "Full-time",
        "date_posted": (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d"),
        "application_deadline": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
        "contact_info": "",
        "apply_link": "https://example.com/apply",
        "source_url": "https://pk.indeed.com/viewjob?jk=old123",
        "scraped_at": datetime.now().isoformat(),
    }


@pytest.fixture
def mixed_platform_jobs(sample_indeed_job, sample_linkedin_job):
    """A mixed dataset with an Indeed and LinkedIn duplicate."""
    return [sample_indeed_job, sample_linkedin_job]


# ═══════════════════════════════════════════════════════════════════
#  JOB SCRAPING AGENT — 12 TEST CASES
# ═══════════════════════════════════════════════════════════════════

class TestJobScrapingAgent:
    """Tests for the Job Scraping Agent."""

    # ── Test 1: Agent initialisation ──
    def test_agent_initialises_correctly(self):
        """Agent should initialise with model set to gpt-4o-mini."""
        agent = JobScrapingAgent()
        assert agent.MODEL == "gpt-4o-mini"
        assert agent.scrape_history == []

    # ── Test 2: Clean HTML removes tags ──
    def test_clean_html_strips_tags(self):
        """_clean_html should strip all HTML tags and decode entities."""
        raw = '<div class="test"><b>Hello</b> &amp; <em>World</em></div>'
        assert _clean_html(raw) == "Hello & World"

    # ── Test 3: Clean HTML preserves newlines ──
    def test_clean_html_preserves_newlines(self):
        """_clean_html with keep_newlines=True should preserve <br> as newlines."""
        raw = "Line1<br>Line2<br/>Line3"
        result = _clean_html(raw, keep_newlines=True)
        assert "\n" in result

    # ── Test 4: Normalise relative date ──
    def test_normalize_relative_date_just_posted(self):
        """'Just posted' should normalise to today's date."""
        result = _normalize_relative_date("Just posted")
        assert result == datetime.now().strftime("%Y-%m-%d")

    def test_normalize_relative_date_days_ago(self):
        """'5 days ago' should normalise to 5 days before today."""
        result = _normalize_relative_date("5 days ago")
        expected = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        assert result == expected

    # ── Test 5: Generate unique job IDs ──
    def test_generate_job_id_is_deterministic(self):
        """Same platform + URL should produce the same job_id."""
        id1 = _generate_job_id("indeed", "https://pk.indeed.com/viewjob?jk=abc123")
        id2 = _generate_job_id("indeed", "https://pk.indeed.com/viewjob?jk=abc123")
        assert id1 == id2

    def test_generate_job_id_differs_by_platform(self):
        """Different platforms for the same URL should produce different job_ids."""
        id1 = _generate_job_id("indeed", "https://example.com/job/1")
        id2 = _generate_job_id("linkedin", "https://example.com/job/1")
        assert id1 != id2

    # ── Test 6: Standardise job record ──
    def test_standardise_job_record_has_all_fields(self):
        """Standardised record should have all required fields."""
        raw = {
            "title": "Python Dev",
            "company": "TestCo",
            "description": "A test job posting",
            "location": "Lahore",
            "detail_url": "https://pk.indeed.com/viewjob?jk=test1",
        }
        result = _standardise_job_record(raw, "indeed")
        required_fields = [
            "job_id", "platform", "title", "company", "description",
            "required_skills", "location", "salary", "job_type",
            "date_posted", "application_deadline", "contact_info",
            "apply_link", "source_url", "scraped_at",
        ]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"

    # ── Test 7: URL validation ──
    def test_valid_url_accepts_http(self):
        """Valid URLs should be accepted."""
        assert _is_valid_url("https://example.com/apply") is True

    def test_valid_url_rejects_javascript(self):
        """javascript: URLs should be rejected."""
        assert _is_valid_url("javascript:alert('xss')") is False

    def test_valid_url_accepts_mailto(self):
        """mailto: links should be accepted."""
        assert _is_valid_url("mailto:hr@example.com") is True

    # ── Test 8: Parse job type ──
    def test_parse_job_type_detects_fulltime(self):
        """Should detect 'Full-time' in text."""
        result = _parse_job_type("This is a full-time position")
        assert "Full-time" in result

    # ── Test 9: Indeed URL canonicalisation ──
    def test_canonical_indeed_url_extracts_jobkey(self):
        """Should canonicalise redirect URLs to viewjob format."""
        url = "https://pk.indeed.com/rc/clk?jk=abc123&fccid=xyz"
        result = _canonical_indeed_url(url)
        assert result == "https://pk.indeed.com/viewjob?jk=abc123"

    # ── Test 10: JSON output is always valid ──
    def test_to_json_always_returns_valid_json(self):
        """to_json should always return valid JSON, even with unusual data."""
        agent = JobScrapingAgent()
        jobs = [{"title": "Test", "date": datetime.now()}]
        result = agent.to_json(jobs)
        parsed = json.loads(result)  # Should not raise
        assert isinstance(parsed, list)

    # ── Test 11: Skill extraction ──
    def test_extract_required_skills(self):
        """Should extract known skills from description."""
        desc = "Must know Python, Django, and PostgreSQL. Experience with Docker is a plus."
        skills = _extract_required_skills(desc)
        assert "Python" in skills
        assert "Django" in skills
        assert "Postgresql" in skills

    # ── Test 12: Build Indeed search URL ──
    def test_build_indeed_search_url(self):
        """Should build correct Indeed search URL with parameters."""
        url = _build_indeed_search_url("python", location="Lahore", job_type="internship")
        assert "q=python" in url
        assert "l=Lahore" in url
        assert "jt=internship" in url


# ═══════════════════════════════════════════════════════════════════
#  JOB VERIFICATION AGENT — 14 TEST CASES
# ═══════════════════════════════════════════════════════════════════

class TestJobVerificationAgent:
    """Tests for the Job Verification Agent."""

    # ── Test 1: Agent initialisation ──
    def test_agent_initialises_correctly(self):
        """Agent should initialise with correct model and empty stats."""
        agent = JobVerificationAgent()
        assert agent.MODEL == "gpt-4o-mini"
        assert agent.verification_stats["total_processed"] == 0

    # ── Test 2: Valid job gets verified status ──
    def test_valid_job_is_verified(self, sample_indeed_job):
        """A clean, complete job listing should be marked as 'verified'."""
        agent = JobVerificationAgent()
        result = agent.verify_jobs([sample_indeed_job])
        assert len(result) == 1
        assert result[0]["verified_status"] == "verified"

    # ── Test 3: Suspicious job gets flagged or rejected ──
    def test_suspicious_job_is_flagged(self, suspicious_job):
        """A job with multiple red flags should be rejected or flagged."""
        agent = JobVerificationAgent()
        result = agent.verify_jobs([suspicious_job])
        assert result[0]["verified_status"] in ("rejected", "flagged_for_review")

    # ── Test 4: Expired job gets rejected ──
    def test_expired_job_is_rejected(self, expired_job):
        """A job past its deadline should be rejected."""
        agent = JobVerificationAgent()
        result = agent.verify_jobs([expired_job])
        assert result[0]["verified_status"] == "rejected"

    # ── Test 5: Duplicate detection — exact URL ──
    def test_duplicate_detection_exact_url(self, sample_indeed_job):
        """Two jobs with the same source_url should be flagged as duplicates."""
        job1 = sample_indeed_job.copy()
        job2 = sample_indeed_job.copy()
        job2["job_id"] = "duplicate_001"
        jobs = detect_duplicates([job1, job2])
        assert jobs[1].get("is_duplicate") is True

    # ── Test 6: Duplicate detection — cross-platform ──
    def test_duplicate_detection_cross_platform(self, mixed_platform_jobs):
        """Same job on Indeed and LinkedIn should be detected as duplicate."""
        jobs = detect_duplicates(mixed_platform_jobs)
        dup_count = sum(1 for j in jobs if j.get("is_duplicate", False))
        assert dup_count >= 1  # At least one duplicate detected

    # ── Test 7: Company verification — valid company ──
    def test_company_verification_valid(self):
        """A legitimate company name should pass verification."""
        result = verify_company("TechCorp Pakistan")
        assert result["is_verified"] is True
        assert result["confidence"] >= 0.5

    # ── Test 8: Company verification — empty company ──
    def test_company_verification_empty(self):
        """Empty company name should fail verification."""
        result = verify_company("")
        assert result["is_verified"] is False
        assert result["confidence"] == 0.0

    # ── Test 9: Company verification — generic name ──
    def test_company_verification_generic(self):
        """Generic company names like 'N/A' should fail."""
        result = verify_company("N/A")
        assert result["is_verified"] is False

    # ── Test 10: Suspicious listing — payment keywords ──
    def test_suspicious_payment_keywords(self):
        """Jobs mentioning wire transfer / upfront payment should be flagged."""
        job = {
            "title": "Amazing Job",
            "company": "TestCo",
            "description": "Send upfront payment via wire transfer to start working.",
            "apply_link": "https://example.com",
            "contact_info": "",
        }
        result = flag_suspicious_listing(job)
        assert result["is_suspicious"] is True
        assert result["suspicion_score"] > 0

    # ── Test 11: Suspicious listing — invalid apply link ──
    def test_suspicious_invalid_apply_link(self):
        """Jobs with javascript: apply links should be flagged."""
        job = {
            "title": "Test Job",
            "company": "TestCo",
            "description": "A normal job description.",
            "apply_link": "javascript:void(0)",
            "contact_info": "",
        }
        result = flag_suspicious_listing(job)
        assert result["is_suspicious"] is True

    # ── Test 12: Check expired posting — future deadline ──
    def test_not_expired_future_deadline(self):
        """A job with a future deadline should not be expired."""
        job = {
            "date_posted": datetime.now().strftime("%Y-%m-%d"),
            "application_deadline": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
        }
        result = check_expired_posting(job)
        assert result["is_expired"] is False

    # ── Test 13: Check expired posting — past deadline ──
    def test_expired_past_deadline(self):
        """A job with a past deadline should be expired."""
        job = {
            "date_posted": (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d"),
            "application_deadline": (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d"),
        }
        result = check_expired_posting(job)
        assert result["is_expired"] is True

    # ── Test 14: All outputs are valid JSON ──
    def test_verification_output_is_valid_json(self, sample_indeed_job, suspicious_job, expired_job):
        """All verification outputs should be serialisable to valid JSON."""
        agent = JobVerificationAgent()
        jobs = agent.verify_jobs([sample_indeed_job, suspicious_job, expired_job])
        json_str = agent.to_json(jobs)
        parsed = json.loads(json_str)
        assert isinstance(parsed, list)
        assert len(parsed) == 3

    # ── Test 15: Verification report ──
    def test_generate_report(self, sample_indeed_job, suspicious_job):
        """Report should contain correct counts."""
        agent = JobVerificationAgent()
        jobs = agent.verify_jobs([sample_indeed_job, suspicious_job])
        report = agent.generate_report(jobs)
        assert report["total_processed"] == 2
        assert report["verified"] + report["rejected"] + report["flagged_for_review"] == 2

    # ── Test 16: No hardcoded API keys ──
    def test_no_hardcoded_api_keys(self):
        """Agents should use environment variables for credentials, not hardcoded keys."""
        agent = JobScrapingAgent()
        assert agent.api_key == os.environ.get("OPENAI_API_KEY", "")

        vagent = JobVerificationAgent()
        assert vagent.api_key == os.environ.get("OPENAI_API_KEY", "")


# ═══════════════════════════════════════════════════════════════════
#  ACCURACY TEST — SRS 5.3 compliance (>= 95%)
# ═══════════════════════════════════════════════════════════════════

class TestVerificationAccuracy:
    """Tests that verification accuracy meets the >= 95% threshold (SRS 5.3)."""

    def test_accuracy_on_mixed_dataset(self):
        """
        Build a dataset of 20 jobs: 14 valid, 3 suspicious, 3 expired/duplicate.
        The agent should correctly classify >= 95% of them.
        """
        agent = JobVerificationAgent()
        jobs = []

        # 14 valid jobs
        job_titles = [
            "Software Engineer", "Data Scientist", "Product Manager", "DevOps Engineer",
            "Frontend Developer", "Backend Developer", "Full Stack Engineer", "QA Tester",
            "System Administrator", "Cloud Architect", "UI/UX Designer", "Mobile Developer",
            "Security Analyst", "Database Administrator"
        ]
        companies = [
            "TechCorp", "DataSystems", "Innovate LLC", "CloudNet",
            "WebWorks", "ServerPros", "StackBuilders", "QualityFirst",
            "AdminSolutions", "ArchitectsInc", "DesignStudio", "AppMakers",
            "SecureIT", "DataStore"
        ]

        for i in range(14):
            jobs.append({
                "job_id": f"valid_{i:03d}",
                "platform": "indeed",
                "title": job_titles[i],
                "company": companies[i],
                "description": f"A real job posting for {job_titles[i]} at {companies[i]}. Requires technical and communication skills.",
                "location": "Lahore",
                "salary": "PKR 100,000/month",
                "job_type": "Full-time",
                "date_posted": (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d"),
                "application_deadline": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
                "contact_info": f"hr{i}@validcorp.com",
                "apply_link": f"https://validcorp{i}.com/apply",
                "source_url": f"https://pk.indeed.com/viewjob?jk=valid{i:03d}",
                "scraped_at": datetime.now().isoformat(),
                "required_skills": ["Python"],
            })

        # 3 suspicious jobs
        for i in range(3):
            jobs.append({
                "job_id": f"sus_{i:03d}",
                "platform": "indeed",
                "title": f"EARN $10000 PER WEEK #{i}",
                "company": "",
                "description": "Send wire transfer upfront payment processing fee guaranteed income!!!",
                "location": "",
                "salary": "",
                "job_type": "",
                "date_posted": "",
                "application_deadline": "",
                "contact_info": f"scam{i}@gmail.com",
                "apply_link": "javascript:alert(1)",
                "source_url": f"https://pk.indeed.com/viewjob?jk=sus{i:03d}",
                "scraped_at": datetime.now().isoformat(),
                "required_skills": [],
            })

        # 3 expired jobs
        for i in range(3):
            jobs.append({
                "job_id": f"exp_{i:03d}",
                "platform": "indeed",
                "title": f"Old Position #{i}",
                "company": f"OldCorp {i}",
                "description": "This job posting is very old.",
                "location": "Karachi",
                "salary": "",
                "job_type": "Contract",
                "date_posted": (datetime.now() - timedelta(days=90 + i)).strftime("%Y-%m-%d"),
                "application_deadline": (datetime.now() - timedelta(days=30 + i)).strftime("%Y-%m-%d"),
                "contact_info": "",
                "apply_link": f"https://oldcorp{i}.com/apply",
                "source_url": f"https://pk.indeed.com/viewjob?jk=exp{i:03d}",
                "scraped_at": datetime.now().isoformat(),
                "required_skills": [],
            })

        # Run verification
        verified_jobs = agent.verify_jobs(jobs)

        # Count correct classifications
        correct = 0
        total = len(verified_jobs)

        for job in verified_jobs:
            jid = job["job_id"]
            status = job["verified_status"]

            if jid.startswith("valid_") and status == "verified":
                correct += 1
            elif jid.startswith("sus_") and status in ("rejected", "flagged_for_review"):
                correct += 1
            elif jid.startswith("exp_") and status == "rejected":
                correct += 1

        accuracy = correct / total
        assert accuracy >= 0.95, (
            f"Verification accuracy {accuracy:.2%} is below 95% threshold. "
            f"Correct: {correct}/{total}"
        )


# ═══════════════════════════════════════════════════════════════════
#  EDGE CASE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Edge case tests for robustness."""

    def test_empty_job_list(self):
        """Agents should handle empty lists gracefully."""
        agent = JobVerificationAgent()
        result = agent.verify_jobs([])
        assert result == []

    def test_none_fields(self):
        """Jobs with None values should not crash."""
        agent = JobVerificationAgent()
        job = {
            "job_id": "none_test",
            "title": None,
            "company": None,
            "description": None,
            "apply_link": None,
            "contact_info": None,
            "date_posted": None,
            "application_deadline": None,
            "source_url": "https://example.com/job",
        }
        result = agent.verify_jobs([job])
        assert len(result) == 1
        assert result[0]["verified_status"] in ("verified", "rejected", "flagged_for_review")

    def test_very_long_description(self):
        """Should handle very long descriptions without crashing."""
        job = {
            "title": "Test",
            "company": "TestCo",
            "description": "Lorem ipsum dolor sit amet. " * 10000,
            "apply_link": "https://example.com",
            "contact_info": "",
        }
        result = flag_suspicious_listing(job)
        assert isinstance(result, dict)
        assert "is_suspicious" in result

    def test_special_characters_in_title(self):
        """Should handle special characters without crashing."""
        result = _clean_html('<b>Job™ — "Senior" Developer (Remote) ≥ 5 years</b>')
        assert "Senior" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
