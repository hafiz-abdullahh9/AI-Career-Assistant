from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship, Column, JSON

# ================= Database Models =================

class User(SQLModel, table=True):
    __tablename__ = "users"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    first_name: str
    last_name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    skills: List["UserSkill"] = Relationship(back_populates="user", cascade_delete=True)
    analyses: List["SkillGapAnalysis"] = Relationship(back_populates="user", cascade_delete=True)
    interviews: List["InterviewSession"] = Relationship(back_populates="user", cascade_delete=True)


class UserSkill(SQLModel, table=True):
    __tablename__ = "user_skills"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    skill_name: str = Field(index=True)
    proficiency_level: str  # Beginner, Intermediate, Expert
    years_experience: float = Field(default=0.0)

    # Relationships
    user: Optional[User] = Relationship(back_populates="skills")


class Job(SQLModel, table=True):
    __tablename__ = "jobs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    company_name: str = Field(index=True)
    description: str
    # Stored as JSON list of required skills (e.g. ["Python", "FastAPI", "Docker"])
    required_skills: List[str] = Field(default=[], sa_column=Column(JSON))
    location: str
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    analyses: List["SkillGapAnalysis"] = Relationship(back_populates="job", cascade_delete=True)
    interviews: List["InterviewSession"] = Relationship(back_populates="job", cascade_delete=True)


class SkillGapAnalysis(SQLModel, table=True):
    __tablename__ = "skill_gap_analyses"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    job_id: int = Field(foreign_key="jobs.id")
    # Store lists and dicts as JSON columns
    missing_skills: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    proficiency_gap: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    learning_roadmap: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    salary_projection: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    user: Optional[User] = Relationship(back_populates="analyses")
    job: Optional[Job] = Relationship(back_populates="analyses")


class InterviewSession(SQLModel, table=True):
    __tablename__ = "interview_sessions"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    job_id: int = Field(foreign_key="jobs.id")
    # Lists of questions and responses
    question_set: List[str] = Field(default=[], sa_column=Column(JSON))
    responses: List[str] = Field(default=[], sa_column=Column(JSON))
    # Detailed feedback for each response and overall stats
    feedback: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    score: Optional[int] = None
    status: str = Field(default="started")  # started, completed, evaluated
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    user: Optional[User] = Relationship(back_populates="interviews")
    job: Optional[Job] = Relationship(back_populates="interviews")


# ================= API Schemas (Pydantic) =================

class UserCreate(SQLModel):
    email: str
    first_name: str
    last_name: str

class SkillCreate(SQLModel):
    skill_name: str
    proficiency_level: str
    years_experience: float

class JobCreate(SQLModel):
    title: str
    company_name: str
    description: str
    required_skills: List[str]
    location: str
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None

class SkillGapRequest(SQLModel):
    user_id: int
    job_id: int

class InterviewStartRequest(SQLModel):
    user_id: int
    job_id: int

class AnswerSubmitRequest(SQLModel):
    question_index: int
    answer: str
