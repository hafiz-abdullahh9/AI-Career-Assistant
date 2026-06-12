import json
import logging
from typing import List, Dict, Any
from services.config import settings

logger = logging.getLogger(__name__)

# Initialize LLM Clients lazily
def get_gemini_client():
    if not settings.GEMINI_API_KEY or "your_gemini" in settings.GEMINI_API_KEY:
        return None
    try:
        from google import genai
        return genai.Client(api_key=settings.GEMINI_API_KEY)
    except Exception as e:
        logger.error(f"Failed to configure Gemini Client: {e}")
        return None

def get_openai_client():
    if not settings.OPENAI_API_KEY or "your_openai" in settings.OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception as e:
        logger.error(f"Failed to configure OpenAI: {e}")
        return None

def call_llm(prompt: str, json_response: bool = True) -> str:
    """Helper to dispatch LLM calls to either Gemini or OpenAI, or fallback to mock."""
    provider = settings.LLM_PROVIDER.lower()
    
    # 1. Try Gemini
    if provider == "gemini":
        gemini_client = get_gemini_client()
        if gemini_client:
            try:
                config = {"response_mime_type": "application/json"} if json_response else None
                response = gemini_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=config
                )
                return response.text.strip()
            except Exception as e:
                logger.error(f"Gemini call failed, checking fallback: {e}")

    # 2. Try OpenAI
    openai_client = get_openai_client()
    if openai_client:
        try:
            model = "gpt-4o-mini"
            messages = [{"role": "user", "content": prompt}]
            response_format = {"type": "json_object"} if json_response else None
            response = openai_client.chat.completions.create(
                model=model,
                messages=messages,
                response_format=response_format
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI call failed: {e}")

    # 3. Fallback/Mock return
    logger.warning("No working LLM provider API keys configured. Using Mock fallback.")
    return ""


# ================= Business Specific Prompt Wrappers =================

def generate_skill_gap_analysis(user_skills: List[Dict[str, Any]], job_title: str, job_description: str) -> Dict[str, Any]:
    """Generates skill gap analysis, roadmaps, and course suggestions."""
    skills_str = ", ".join([f"{s['skill_name']} ({s['proficiency_level']})" for s in user_skills])
    
    prompt = f"""
    You are an expert AI Career Coach. 
    Analyze the gap between a candidate's skills and the requirements of a specific job.
    
    Candidate Skills: {skills_str}
    Job Title: {job_title}
    Job Description: {job_description}
    
    You must output a JSON object with the following structure:
    {{
        "missing_skills": [
            {{"skill_name": "Skill Name", "priority": "High/Medium/Low"}}
        ],
        "proficiency_gap": [
            {{"skill_name": "Skill Name", "user_level": "User Level", "required_level": "Required Level", "description": "What they need to learn"}}
        ],
        "learning_roadmap": [
            {{
                "phase": "Phase 1: Foundations",
                "skills": ["Skill 1", "Skill 2"],
                "duration": "2 weeks",
                "resources": [
                    {{"name": "Course Title or Doc Name", "type": "Course/Book/Documentation", "url": "https://example.com/learn"}}
                ]
            }}
        ],
        "salary_projection": 15.5
    }}
    Note: salary_projection should be an estimated percentage increase (float) in the user's market value if they acquire these missing skills.
    
    Provide ONLY the raw JSON string. Do not wrap in markdown blocks like ```json.
    """
    
    raw_response = call_llm(prompt, json_response=True)
    if raw_response:
        try:
            return json.loads(raw_response)
        except Exception as e:
            logger.error(f"Failed to parse LLM JSON response: {e}. Raw: {raw_response}")
            
    # Mock fallback
    return {
        "missing_skills": [
            {"skill_name": "Docker & Kubernetes", "priority": "High"},
            {"skill_name": "CI/CD Pipelines (GitHub Actions)", "priority": "High"},
            {"skill_name": "System Design", "priority": "Medium"}
        ],
        "proficiency_gap": [
            {"skill_name": "System Design", "user_level": "None", "required_level": "Intermediate", "description": "Needs basic microservices design and API gateway patterns."},
            {"skill_name": "Docker", "user_level": "Beginner", "required_level": "Intermediate", "description": "Familiar with writing basic Dockerfiles, but needs multi-stage builds and compose configurations."}
        ],
        "learning_roadmap": [
            {
                "phase": "Phase 1: Containerization Fundamentals",
                "skills": ["Docker", "Docker Compose"],
                "duration": "2 weeks",
                "resources": [
                    {"name": "Docker for Beginners (Docker Docs)", "type": "Documentation", "url": "https://docs.docker.com/get-started/"},
                    {"name": "Docker Crash Course (YouTube)", "type": "Course", "url": "https://www.youtube.com/results?search_query=docker+crash+course"}
                ]
            },
            {
                "phase": "Phase 2: CI/CD & Deployment",
                "skills": ["GitHub Actions", "Kubernetes Basics"],
                "duration": "3 weeks",
                "resources": [
                    {"name": "GitHub Actions Learning Path", "type": "Documentation", "url": "https://docs.github.com/en/actions"}
                ]
            }
        ],
        "salary_projection": 20.0
    }

def generate_interview_questions(job_title: str, job_description: str) -> List[str]:
    """Generates 5 contextually relevant interview questions."""
    prompt = f"""
    You are an expert technical interviewer.
    Generate exactly 5 interview questions for the job role '{job_title}' based on the job description below.
    The questions should be a mix of technical (core skills), behavioral (scenario-based), and HR fit.
    
    Job Description: {job_description}
    
    You must output a JSON object containing a list of strings:
    {{
        "questions": [
            "Question 1",
            "Question 2",
            "Question 3",
            "Question 4",
            "Question 5"
        ]
    }}
    Provide ONLY the raw JSON string. Do not wrap in markdown blocks.
    """
    
    raw_response = call_llm(prompt, json_response=True)
    if raw_response:
        try:
            parsed = json.loads(raw_response)
            if "questions" in parsed:
                return parsed["questions"][:5]
        except Exception as e:
            logger.error(f"Failed to parse interview questions response: {e}. Raw: {raw_response}")
            
    # Mock fallback
    return [
        "How do you design a highly scalable microservice using FastAPI?",
        "Can you explain your experience with containerization, particularly Docker multi-stage builds?",
        "How do you troubleshoot a performance bottleneck in a database query?",
        "Describe a time when you had to learn a complex new technology quickly. What was your process?",
        "What are the benefits of using a caching layer like Redis in a backend application?"
    ]

def evaluate_interview_transcript(questions: List[str], responses: List[str]) -> Dict[str, Any]:
    """Evaluates the candidate's answers against the questions."""
    qa_list = []
    for i, q in enumerate(questions):
        ans = responses[i] if i < len(responses) else "No response provided."
        qa_list.append({"question": q, "answer": ans})
        
    qa_str = json.dumps(qa_list, indent=2)
    
    prompt = f"""
    You are an expert interviewer evaluating a candidate's mock interview responses.
    Evaluate the following list of questions and the candidate's answers:
    
    Transcript:
    {qa_str}
    
    For each answer, calculate a score (0 to 100) and provide details on strengths, weaknesses, and suggestions for improvement.
    Also generate an overall feedback summary and an overall average score.
    
    You must output a JSON object with this structure:
    {{
        "questions_feedback": [
            {{
                "question": "Question text",
                "response": "Answer text",
                "score": 85,
                "strengths": "Strengths detail",
                "weaknesses": "Weaknesses detail",
                "improvement_suggestions": "Suggestions detail"
            }}
        ],
        "overall_feedback": "Overall summary of the candidate's performance",
        "overall_score": 75
    }}
    Provide ONLY the raw JSON string. Do not wrap in markdown blocks.
    """
    
    raw_response = call_llm(prompt, json_response=True)
    if raw_response:
        try:
            return json.loads(raw_response)
        except Exception as e:
            logger.error(f"Failed to parse evaluation response: {e}. Raw: {raw_response}")
            
    # Mock fallback
    feedback_list = []
    overall_sum = 0
    for qa in qa_list:
        ans_len = len(qa['answer'])
        score = 80 if ans_len > 25 else (40 if ans_len < 10 else 60)
        overall_sum += score
        feedback_list.append({
            "question": qa["question"],
            "response": qa["answer"],
            "score": score,
            "strengths": "The response was direct and clear." if score >= 60 else "Attempted to answer.",
            "weaknesses": "Could benefit from more technical depth and concrete examples." if score < 80 else "Minor structural improvements needed.",
            "improvement_suggestions": "Try using the STAR method (Situation, Task, Action, Result) to structure behavioral answers."
        })
        
    return {
        "questions_feedback": feedback_list,
        "overall_feedback": "The candidate demonstrates solid fundamental knowledge but needs to provide more specific examples and elaborate more deeply on system design patterns.",
        "overall_score": int(overall_sum / len(questions)) if questions else 0
    }
