import json
import logging
from datetime import datetime
from openai import AsyncOpenAI
from google import genai
from core.config import settings

logger = logging.getLogger("tools.learning_tools")

async def generate_learning_roadmap(
    current_skills: list[str],
    target_job_skills: list[str]
) -> dict:
    """
    Compares current_skills and target_job_skills to identify the gap,
    and returns a structured roadmap with recommended resources.
    """
    logger.info(f"Generating learning roadmap for {len(current_skills)} current skills vs {len(target_job_skills)} target skills.")
    
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
        logger.warning("No live LLM key configured. Running simulated fallback for learning roadmap.")
        return get_mock_learning_roadmap(current_skills, target_job_skills)
        
    prompt = f"""
    You are an expert AI Career Coach.
    Compare the candidate's current skills against the target job skills.
    
    Current Skills: {current_skills}
    Target Job Skills: {target_job_skills}
    
    Generate a learning path listing the missing skills, priority level (HIGH/MEDIUM/LOW),
    and recommended course titles or resources for each.
    Also estimate the total learning duration in hours.
    
    You must output a JSON object matching this structure EXACTLY:
    {{
      "learning_path": [
        {{
          "skill": "Skill Name",
          "priority": "HIGH",
          "courses": [
            "Recommended Course 1",
            "Recommended Course 2"
          ]
        }}
      ],
      "estimated_hours_to_complete": 40
    }}
    Provide ONLY the raw JSON string. Do not wrap in markdown blocks.
    """
    
    try:
        raw_response = ""
        if provider == "gemini":
            client = genai.Client(api_key=gemini_key)
            config = {"response_mime_type": "application/json"}
            # Execute in threadpool to keep it async-friendly if synchronous genai client is used
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
                "learning_path": data.get("learning_path", []),
                "estimated_hours_to_complete": data.get("estimated_hours_to_complete", 40)
            },
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error(f"Failed to generate learning roadmap: {e}")
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

def get_mock_learning_roadmap(current_skills: list[str], target_job_skills: list[str]) -> dict:
    """Generates standard mocked learning roadmap data conforming to the envelope spec."""
    missing = [s for s in target_job_skills if s.lower() not in [cs.lower() for cs in current_skills]]
    if not missing:
        missing = ["Kubernetes", "Docker"]
        
    path = []
    for s in missing:
        priority = "HIGH" if s.lower() in ("kubernetes", "docker", "ci/cd") else "MEDIUM"
        path.append({
            "skill": s,
            "priority": priority,
            "courses": [
                f"{s} and Cloud Architecture (Coursera)",
                f"Mastering {s} in Production (Udemy)"
            ]
        })
        
    return {
        "status": "SUCCESS",
        "data": {
            "learning_path": path,
            "estimated_hours_to_complete": len(missing) * 20
        },
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
