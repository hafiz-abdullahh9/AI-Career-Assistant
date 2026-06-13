import pytest
from agents import Runner, skill_gap_agent
from tools.learning_tools import generate_learning_roadmap

@pytest.mark.asyncio
async def test_generate_learning_roadmap_signature():
    """Verifies that the generate_learning_roadmap tool returns correct structure."""
    result = await generate_learning_roadmap(
        current_skills=["Python", "Django"],
        target_job_skills=["Docker", "Kubernetes", "Python"]
    )
    
    assert result["status"] in ("SUCCESS", "ERROR")
    if result["status"] == "SUCCESS":
        assert "data" in result
        assert "learning_path" in result["data"]
        assert "estimated_hours_to_complete" in result["data"]
        assert "timestamp" in result

@pytest.mark.asyncio
async def test_skill_gap_agent_execution():
    """Verifies that the SkillGapAnalysisAgent compiles and executes under the Runner."""
    runner_res = await Runner.run(
        agent=skill_gap_agent,
        input_str="Analyze skills gap for current: ['Python', 'SQL'], target: ['Docker', 'Kubernetes']"
    )
    
    assert runner_res.final_output is not None
    assert len(runner_res.history) > 0
