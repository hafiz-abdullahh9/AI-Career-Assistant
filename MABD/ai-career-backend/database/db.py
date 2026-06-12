import os
from dotenv import load_dotenv
from sqlmodel import SQLModel, create_engine, Session

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./career_assistant.db")

# For SQLite, we need connect_args={"check_same_thread": False}
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)

def init_db():
    """Create all tables in the database."""
    # Importing models inside function to prevent circular imports
    from models.models import User, UserSkill, Job, SkillGapAnalysis, InterviewSession
    SQLModel.metadata.create_all(engine)

def get_session():
    """Dependency for obtaining a database session."""
    with Session(engine) as session:
        yield session
