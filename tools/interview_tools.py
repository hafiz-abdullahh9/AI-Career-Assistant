import json
import logging
from datetime import datetime
from openai import AsyncOpenAI
from google import genai
from core.config import settings

logger = logging.getLogger("tools.interview_tools")

async def run_mock_interview(
    job_description: str,
    question_index: int,
    user_response: str
) -> dict:
    """
    Evaluates a single mock interview response from the user
    based on the job requirements and returns a score, feedback, and a model answer.
    """
    logger.info(f"Running mock interview evaluation for question index {question_index}.")
    
    # 1. Check for API keys and provider
    provider = settings.LLM_PROVIDER.lower()
    openai_key = settings.OPENAI_API_KEY
    gemini_key = settings.GEMINI_API_KEY
    
    # Force mock fallback if placeholder keys are found or MOCK_LLM is set
    import os
    is_mock = (
        (provider == "gemini" and (not gemini_key or "your_gemini" in gemini_key)) or
        (provider == "openai" and (not openai_key or "mock-key" in openai_key or "your_openai" in openai_key)) or
        os.getenv("MOCK_LLM", "false").lower() == "true"
    )
    
    if is_mock:
        logger.warning("No live LLM key configured. Running simulated fallback for mock interview.")
        return get_mock_interview_evaluation(question_index, user_response)
        
    prompt = f"""
    You are an expert technical and HR interviewer.
    Evaluate the candidate's response to question index {question_index} for a job with the following description:
    
    Job Description: {job_description}
    Candidate Response: {user_response}
    
    Please evaluate the quality of this response on a scale of 0.0 to 10.0.
    Provide constructive feedback explaining strengths and weaknesses (suggesting structural improvements like the STAR method if applicable).
    Provide a high-quality suggested model answer.
    
    You must output a JSON object matching this structure EXACTLY:
    {{
      "evaluation_score": 8.5,
      "feedback": "Feedback details...",
      "suggested_answer": "Model answer details..."
    }}
    Provide ONLY the raw JSON string. Do not wrap in markdown blocks.
    """
    
    try:
        raw_response = ""
        if provider == "gemini":
            client = genai.Client(api_key=gemini_key)
            config = {"response_mime_type": "application/json"}
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=config
                )
            )
            raw_response = response.text.strip()
        else:
            client = AsyncOpenAI(api_key=openai_key)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            raw_response = response.choices[0].message.content.strip()
            
        data = json.loads(raw_response)
        
        return {
            "status": "SUCCESS",
            "data": {
                "evaluation_score": float(data.get("evaluation_score", 5.0)),
                "feedback": data.get("feedback", "No feedback provided."),
                "suggested_answer": data.get("suggested_answer", "No model answer provided.")
            },
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error(f"Failed to execute mock interview tool: {e}")
        return {
            "status": "ERROR",
            "error": {
                "code": "API_UNAVAILABLE",
                "message": f"LLM execution failed: {str(e)}",
                "retryable": True,
                "recovery_action": "RETRY_WITH_BACKOFF"
            },
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

def get_mock_interview_evaluation(question_index: int, user_response: str) -> dict:
    """Generates standard mocked interview evaluation data conforming to the envelope spec."""
    score = 8.0 if len(user_response) > 30 else 5.0
    
    return {
        "status": "SUCCESS",
        "data": {
            "evaluation_score": score,
            "feedback": "The response was direct. For behavioral questions, remember to use the STAR method: state the Situation, the Task, the Action you took, and the Result achieved.",
            "suggested_answer": "In my previous role, I optimized database queries by adding composite indexes and caching slow queries with Redis, which reduced API response time by 40%."
        },
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
