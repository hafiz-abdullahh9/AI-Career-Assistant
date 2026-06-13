import pytest
from agents import Runner, interview_agent
from tools.interview_tools import run_mock_interview

@pytest.mark.asyncio
async def test_run_mock_interview_signature():
    """Verifies that the run_mock_interview tool returns correct structure."""
    result = await run_mock_interview(
        job_description="Kubernetes Backend Engineer role. Strong Docker and CI/CD required.",
        question_index=0,
        user_response="I build multi-stage Dockerfiles and write GitHub Action workflows."
    )
    
    assert result["status"] in ("SUCCESS", "ERROR")
    if result["status"] == "SUCCESS":
        assert "data" in result
        assert "evaluation_score" in result["data"]
        assert "feedback" in result["data"]
        assert "suggested_answer" in result["data"]
        assert "timestamp" in result

@pytest.mark.asyncio
async def test_interview_agent_execution():
    """Verifies that the InterviewPreparationAgent compiles and executes under the Runner."""
    runner_res = await Runner.run(
        agent=interview_agent,
        input_str="Evaluate response to question index 0 for Kubernetes Engineer: 'I write Dockerfiles.'"
    )
    
    assert runner_res.final_output is not None
    assert len(runner_res.history) > 0
