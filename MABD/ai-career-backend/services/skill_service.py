from sqlmodel import Session, select
from models.models import User, Job, UserSkill, SkillGapAnalysis
from services.llm import generate_skill_gap_analysis
from fastapi import HTTPException

def analyze_skill_gap(session: Session, user_id: int, job_id: int) -> SkillGapAnalysis:
    # 1. Fetch user and verify existence
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
        
    # 2. Fetch job and verify existence
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID {job_id} not found")

    # 3. Retrieve user's skills
    user_skills_query = select(UserSkill).where(UserSkill.user_id == user_id)
    user_skills = session.exec(user_skills_query).all()
    
    # Format skills for LLM
    skills_data = [
        {
            "skill_name": skill.skill_name,
            "proficiency_level": skill.proficiency_level,
            "years_experience": skill.years_experience
        }
        for skill in user_skills
    ]
    
    # 4. Generate gap analysis using LLM
    analysis_result = generate_skill_gap_analysis(
        user_skills=skills_data,
        job_title=job.title,
        job_description=job.description
    )
    
    # 5. Create and save analysis record
    db_analysis = SkillGapAnalysis(
        user_id=user_id,
        job_id=job_id,
        missing_skills=analysis_result.get("missing_skills", []),
        proficiency_gap=analysis_result.get("proficiency_gap", []),
        learning_roadmap=analysis_result.get("learning_roadmap", []),
        salary_projection=analysis_result.get("salary_projection", 0.0)
    )
    
    session.add(db_analysis)
    session.commit()
    session.refresh(db_analysis)
    
    return db_analysis
