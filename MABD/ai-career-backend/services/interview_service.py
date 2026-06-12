from sqlmodel import Session
from models.models import User, Job, InterviewSession
from services.llm import generate_interview_questions, evaluate_interview_transcript
from fastapi import HTTPException

def start_interview_session(session: Session, user_id: int, job_id: int) -> InterviewSession:
    # 1. Fetch user and job
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
        
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID {job_id} not found")

    # 2. Generate 5 interview questions from the job description
    questions = generate_interview_questions(job.title, job.description)
    
    # 3. Create session in DB, pre-filling response list with empty strings
    db_session = InterviewSession(
        user_id=user_id,
        job_id=job_id,
        question_set=questions,
        responses=[""] * len(questions),
        feedback={},
        score=None,
        status="started"
    )
    
    session.add(db_session)
    session.commit()
    session.refresh(db_session)
    
    return db_session


def submit_interview_response(session: Session, session_id: int, question_index: int, answer: str) -> InterviewSession:
    # 1. Fetch session
    db_session = session.get(InterviewSession, session_id)
    if not db_session:
        raise HTTPException(status_code=404, detail=f"Interview session {session_id} not found")
        
    if db_session.status != "started":
        raise HTTPException(status_code=400, detail="Cannot submit responses to a completed or evaluated session")

    # 2. Check bounds
    if question_index < 0 or question_index >= len(db_session.question_set):
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid question index {question_index}. Session contains {len(db_session.question_set)} questions."
        )

    # 3. Update responses (assign new list to trigger SQLAlchemy JSON mutability tracking)
    updated_responses = list(db_session.responses)
    # Ensure list is long enough (in case responses weren't initialized)
    while len(updated_responses) < len(db_session.question_set):
        updated_responses.append("")
    updated_responses[question_index] = answer
    
    db_session.responses = updated_responses
    
    session.add(db_session)
    session.commit()
    session.refresh(db_session)
    
    return db_session


def evaluate_interview_session(session: Session, session_id: int) -> InterviewSession:
    # 1. Fetch session
    db_session = session.get(InterviewSession, session_id)
    if not db_session:
        raise HTTPException(status_code=404, detail=f"Interview session {session_id} not found")
        
    # 2. Evaluate using LLM
    evaluation_result = evaluate_interview_transcript(
        questions=db_session.question_set,
        responses=db_session.responses
    )
    
    # 3. Update session status and score
    db_session.feedback = evaluation_result
    db_session.score = evaluation_result.get("overall_score", 0)
    db_session.status = "evaluated"
    
    session.add(db_session)
    session.commit()
    session.refresh(db_session)
    
    return db_session
