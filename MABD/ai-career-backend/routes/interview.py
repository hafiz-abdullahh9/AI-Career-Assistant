from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from database.db import get_session
from models.models import InterviewSession, InterviewStartRequest, AnswerSubmitRequest
from services.interview_service import (
    start_interview_session, 
    submit_interview_response, 
    evaluate_interview_session
)

router = APIRouter(tags=["Mock Interview Prep"])

@router.post("/interview/start", response_model=InterviewSession, status_code=201)
def start_interview(request: InterviewStartRequest, session: Session = Depends(get_session)):
    return start_interview_session(
        session=session,
        user_id=request.user_id,
        job_id=request.job_id
    )

@router.post("/interview/{session_id}/answer", response_model=InterviewSession)
def submit_answer(session_id: int, request: AnswerSubmitRequest, session: Session = Depends(get_session)):
    return submit_interview_response(
        session=session,
        session_id=session_id,
        question_index=request.question_index,
        answer=request.answer
    )

@router.post("/interview/{session_id}/evaluate", response_model=InterviewSession)
def evaluate_interview(session_id: int, session: Session = Depends(get_session)):
    return evaluate_interview_session(
        session=session,
        session_id=session_id
    )

@router.get("/interview/{session_id}", response_model=InterviewSession)
def get_interview_session(session_id: int, session: Session = Depends(get_session)):
    db_session = session.get(InterviewSession, session_id)
    if not db_session:
        raise HTTPException(status_code=404, detail="Interview session not found")
    return db_session