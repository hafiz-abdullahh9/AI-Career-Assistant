import pytest
from unittest.mock import AsyncMock
from agents.career_orchestrator import CareerOrchestrator
from infra.profile_context import ProfileContext, ProfileData

@pytest.mark.asyncio
async def test_full_pipeline_orchestration_contract():
    """
    Integration Contract Test: Simulates the complete sequence from Discovery to Customization.
    This skeleton verifies that the ProfileContext correctly propagates across all specialist interfaces
    without executing actual external business logic.
    """
    db = AsyncMock()
    redis = AsyncMock()

    # 1. Setup mock inputs mimicking other team members' tools (Member 2, 3 contracts)
    async def mock_scrape(keywords, location):
        return {
            "jobs": [
                {
                    "job_id": "li-123",
                    "company_name": "Google",
                    "job_title": "SWE",
                    "description": "Python developer",
                    "location": "Remote",
                    "url": "https://google.com"
                }
            ]
        }

    async def mock_verify(company_name):
        return {"verified_status": True}

    async def mock_match(profile_skills, profile_experience, job_requirements):
        return {"compatibility_score": 95.0, "reasoning": "Perfect fit"}

    async def mock_resume(profile_data, job_details):
        return {"pdf_path": "/storage/resumes/alice_google.pdf"}

    async def mock_cover(profile_data, job_details):
        return {"pdf_path": "/storage/cover_letters/alice_google.pdf"}

    async def mock_integrity_check(original_profile, tailored_resume_path):
        return {"factual_integrity_verified": True}

    # 2. Initialize ProfileContext
    profile = ProfileData(
        name="Alice",
        email="alice@google.com",
        skills=["Python", "SQL"],
        experience=[{"title": "Engineer", "duration_years": 3}],
        education=[],
        raw_cv_text="CV Text"
    )
    context = ProfileContext(user_id="usr-integration", profile_data=profile, pipeline_state="IDLE")

    # Mock Database Context Manager
    cm = AsyncMock()
    cm.load_context.return_value = context
    cm.save_context = AsyncMock()

    orchestrator = CareerOrchestrator(context_manager=cm)

    # 3. Step 1: Run Discovery Stage (Discovery -> Verification -> Matching state)
    context = await orchestrator.run_discovery_stage(
        user_id="usr-integration",
        db=db,
        redis_client=redis,
        scrape_func=mock_scrape,
        verify_func=mock_verify
    )
    assert context.pipeline_state == "STATE_MATCHING"
    assert len(context.job_queue) == 1
    assert context.job_queue[0].company_name == "Google"

    # 4. Step 2: Run Matching Stage (Matching -> Selection Wait state)
    context = await orchestrator.run_matching_stage(
        user_id="usr-integration",
        db=db,
        redis_client=redis,
        match_func=mock_match
    )
    assert context.pipeline_state == "STATE_SELECTION_WAIT"
    assert context.job_queue[0].match_score == 95.0

    # 5. Step 3: Run Customization Stage (Selection Wait -> Guardrail Check -> Application state)
    context = await orchestrator.run_customization_stage(
        user_id="usr-integration",
        job_id="li-123",
        db=db,
        redis_client=redis,
        resume_func=mock_resume,
        cover_letter_func=mock_cover,
        integrity_func=mock_integrity_check
    )
    assert context.pipeline_state == "STATE_APPLICATION"
    assert len(context.active_applications) == 1
    assert context.active_applications[0].resume_path == "/storage/resumes/alice_google.pdf"
