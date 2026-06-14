import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from agents.career_orchestrator import CareerOrchestrator
from infra.profile_context import ProfileContext, ProfileData, JobItem, ApplicationItem
from core.exceptions import AgentExecutionError, IntegrityCheckFailed

@pytest.mark.asyncio
async def test_run_discovery_stage_success():
    """Verifies successful discovery stage flow and transition to STATE_MATCHING."""
    db = AsyncMock()
    redis = AsyncMock()

    async def mock_scrape(keywords, location):
        return {
            "jobs": [
                {
                    "job_id": "job-101",
                    "company_name": "Acme Corp",
                    "job_title": "Software Engineer",
                    "description": "Write code",
                    "location": "Remote",
                    "url": "https://acme.com/jobs/1"
                }
            ]
        }

    async def mock_verify(company_name):
        return {"verified_status": True}

    profile = ProfileData(
        name="Alice Smith",
        email="alice@smith.com",
        skills=["Python", "SQL"],
        experience=[],
        education=[],
        raw_cv_text="Alice's CV content"
    )
    context = ProfileContext(user_id="usr-99", profile_data=profile, pipeline_state="IDLE")

    cm = AsyncMock()
    cm.load_context.return_value = context
    cm.save_context = AsyncMock()

    orchestrator = CareerOrchestrator(context_manager=cm)
    res = await orchestrator.run_discovery_stage("usr-99", db, redis, mock_scrape, mock_verify)

    assert res.pipeline_state == "STATE_MATCHING"
    assert len(res.job_queue) == 1
    assert res.job_queue[0].company_name == "Acme Corp"
    assert res.job_queue[0].verified_status == "verified"
    cm.save_context.assert_called()

@pytest.mark.asyncio
async def test_run_discovery_stage_failure():
    """Verifies that an error in scraper routes state to STATE_DISCOVERY_FAILED."""
    db = AsyncMock()
    redis = AsyncMock()

    async def mock_scrape_fail(keywords, location):
        raise RuntimeError("API Timeout")

    async def mock_verify(company_name):
        return {"verified_status": True}

    profile = ProfileData(
        name="Alice Smith",
        email="alice@smith.com",
        skills=["Python"],
        experience=[],
        education=[],
        raw_cv_text="Alice's CV content"
    )
    context = ProfileContext(user_id="usr-99", profile_data=profile, pipeline_state="IDLE")

    cm = AsyncMock()
    cm.load_context.return_value = context
    cm.save_context = AsyncMock()

    orchestrator = CareerOrchestrator(context_manager=cm)
    
    with pytest.raises(AgentExecutionError):
        await orchestrator.run_discovery_stage("usr-99", db, redis, mock_scrape_fail, mock_verify)

    assert context.pipeline_state == "STATE_DISCOVERY_FAILED"

@pytest.mark.asyncio
async def test_run_matching_stage_success():
    """Verifies compatibility ranking logic and transition to STATE_SELECTION_WAIT."""
    db = AsyncMock()
    redis = AsyncMock()

    async def mock_match(profile_skills, profile_experience, job_requirements):
        return {"compatibility_score": 90.0, "reasoning": "Strong match"}

    profile = ProfileData(
        name="Alice Smith",
        email="alice@smith.com",
        skills=["Python"],
        experience=[],
        education=[],
        raw_cv_text="Alice's CV"
    )
    job = JobItem(
        job_id="job-1",
        company_name="Acme",
        job_title="Dev",
        description="Python",
        location="Remote",
        url="https://acme.com"
    )
    context = ProfileContext(
        user_id="usr-99",
        profile_data=profile,
        job_queue=[job],
        pipeline_state="STATE_VERIFICATION"
    )

    cm = AsyncMock()
    cm.load_context.return_value = context
    cm.save_context = AsyncMock()

    orchestrator = CareerOrchestrator(context_manager=cm)
    res = await orchestrator.run_matching_stage("usr-99", db, redis, mock_match)

    assert res.pipeline_state == "STATE_SELECTION_WAIT"
    assert res.job_queue[0].match_score == 90.0
    assert res.job_queue[0].match_reasoning == "Strong match"

@pytest.mark.asyncio
async def test_run_customization_stage_guardrail_breach():
    """Verifies that a guardrail breach routes state to STATE_GUARDRAIL_BREACH."""
    db = AsyncMock()
    redis = AsyncMock()

    async def mock_resume(profile_data, job_details):
        return {"pdf_path": "/storage/resumes/alice_acme.pdf"}

    async def mock_cover(profile_data, job_details):
        return {"pdf_path": "/storage/cover_letters/alice_acme.pdf"}

    async def mock_integrity_fail(original_profile, tailored_resume_path):
        # Mismatch found
        return {"factual_integrity_verified": False}

    profile = ProfileData(
        name="Alice",
        email="alice@smith.com",
        skills=["Python"],
        experience=[],
        education=[],
        raw_cv_text="Alice's CV"
    )
    job = JobItem(
        job_id="job-1",
        company_name="Acme",
        job_title="Dev",
        description="Python",
        location="Remote",
        url="https://acme.com",
        match_score=90.0
    )
    context = ProfileContext(
        user_id="usr-99",
        profile_data=profile,
        job_queue=[job],
        pipeline_state="STATE_SELECTION_WAIT"
    )

    cm = AsyncMock()
    cm.load_context.return_value = context
    cm.save_context = AsyncMock()

    orchestrator = CareerOrchestrator(context_manager=cm)

    with pytest.raises(AgentExecutionError):
        await orchestrator.run_customization_stage(
            user_id="usr-99",
            job_id="job-1",
            db=db,
            redis_client=redis,
            resume_func=mock_resume,
            cover_letter_func=mock_cover,
            integrity_func=mock_integrity_fail
        )

    assert context.pipeline_state == "STATE_GUARDRAIL_BREACH"
