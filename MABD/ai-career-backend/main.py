from contextlib import asynccontextmanager
from fastapi import FastAPI
from routes.skill_gap import router as skill_router
from routes.interview import router as interview_router
from database.db import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="AI Career Assistant Backend",
    description="Backend API for managing Skill Gaps, Interview Prep, CV Optimization, and Job Matching.",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(skill_router)
app.include_router(interview_router)

@app.get("/")
def home():
    return {"message": "AI Career Assistant is running"}