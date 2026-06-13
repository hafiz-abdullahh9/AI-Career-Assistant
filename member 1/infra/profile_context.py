import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy import Column, String, JSON, Float, DateTime, Integer, ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import Base
from core.config import settings
from core.exceptions import CacheException, DatabaseException

# ── Pydantic Schemas for Serialization ──────────────────────────

class ProfileData(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    experience: List[Dict[str, Any]] = Field(default_factory=list)
    education: List[Dict[str, Any]] = Field(default_factory=list)
    raw_cv_text: str

class JobItem(BaseModel):
    job_id: str
    company_name: str
    job_title: str
    description: str
    location: str
    salary: Optional[str] = None
    url: str
    verified_status: str = "pending"  # pending | verified | rejected | flagged_for_review
    match_score: Optional[float] = None
    match_reasoning: Optional[str] = None

class ApplicationItem(BaseModel):
    application_id: str
    job_id: str
    method: str  # email | web-form
    status: str  # applied | review | interview | rejected | accepted
    resume_path: Optional[str] = None
    cover_letter_path: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ProfileContext(BaseModel):
    user_id: str
    profile_data: ProfileData
    job_search_filters: Dict[str, Any] = Field(default_factory=dict)
    job_queue: List[JobItem] = Field(default_factory=list)
    active_applications: List[ApplicationItem] = Field(default_factory=list)
    pipeline_state: str = "IDLE"
    last_updated: datetime = Field(default_factory=datetime.utcnow)


# ── SQLAlchemy Models for Relational Storage ───────────────────

class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    skills = Column(JSON, nullable=False)  # List[str]
    experience = Column(JSON, nullable=False)  # List[Dict]
    education = Column(JSON, nullable=False)  # List[Dict]
    raw_cv_text = Column(String, nullable=False)
    search_filters = Column(JSON, nullable=False)  # Dict
    pipeline_state = Column(String, default="IDLE")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Job(Base):
    __tablename__ = "jobs"

    job_id = Column(String, primary_key=True, index=True)
    company_name = Column(String, nullable=False)
    job_title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    location = Column(String, nullable=False)
    salary = Column(String, nullable=True)
    url = Column(String, nullable=False)
    verified_status = Column(String, default="pending")
    match_score = Column(Float, nullable=True)
    match_reasoning = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ApplicationRecord(Base):
    __tablename__ = "applications"

    application_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("user_profiles.user_id"), nullable=False)
    job_id = Column(String, ForeignKey("jobs.job_id"), nullable=False)
    method = Column(String, nullable=False)
    status = Column(String, default="applied")
    resume_path = Column(String, nullable=True)
    cover_letter_path = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

class PipelineAuditLog(Base):
    __tablename__ = "pipeline_audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    event_name = Column(String, nullable=False)
    from_state = Column(String, nullable=False)
    to_state = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    details = Column(JSON, nullable=True)


# ── Profile Context Manager & State Synchronization ────────────

class ProfileContextManager:
    @staticmethod
    def _redis_key(user_id: str) -> str:
        return f"profile_context:{user_id}"

    async def load_context(self, user_id: str, db: AsyncSession, redis_client) -> Optional[ProfileContext]:
        """Loads ProfileContext from Redis. Falls back to PostgreSQL if Redis is wiped."""
        key = self._redis_key(user_id)
        
        # 1. Attempt loading from Redis Cache
        try:
            cached_data = await redis_client.get(key)
            if cached_data:
                data_dict = json.loads(cached_data)
                return ProfileContext.parse_obj(data_dict)
        except Exception as e:
            # Non-blocking warning: Cache failure shouldn't crash the pipeline load
            pass

        # 2. Redis Cache Miss / Crash Recovery: Rebuild context from PostgreSQL
        try:
            profile = await db.get(UserProfile, user_id)
            if not profile:
                return None

            # Reconstruct context metadata
            p_data = ProfileData(
                name=profile.name,
                email=profile.email,
                phone=profile.phone,
                skills=profile.skills,
                experience=profile.experience,
                education=profile.education,
                raw_cv_text=profile.raw_cv_text
            )

            # Load user's application history
            app_query = await db.execute(
                select(ApplicationRecord).where(ApplicationRecord.user_id == user_id)
            )
            app_records = app_query.scalars().all()
            apps = [
                ApplicationItem(
                    application_id=r.application_id,
                    job_id=r.job_id,
                    method=r.method,
                    status=r.status,
                    resume_path=r.resume_path,
                    cover_letter_path=r.cover_letter_path,
                    timestamp=r.timestamp
                )
                for r in app_records
            ]

            # Reconstruct transient context (transient job queue remains empty until re-discovery)
            context = ProfileContext(
                user_id=user_id,
                profile_data=p_data,
                job_search_filters=profile.search_filters,
                job_queue=[],
                active_applications=apps,
                pipeline_state=profile.pipeline_state,
                last_updated=datetime.utcnow()
            )

            # 3. Restore cached data back to Redis
            try:
                await redis_client.setex(
                    key,
                    settings.PROFILE_CONTEXT_TTL_SECONDS,
                    context.json()
                )
            except Exception:
                pass

            return context
        except Exception as e:
            raise DatabaseException(f"Failed to restore profile context from PostgreSQL: {str(e)}")

    async def save_context(self, context: ProfileContext, db: AsyncSession, redis_client) -> None:
        """Saves ProfileContext to Redis (transient cache) and updates core tables in PostgreSQL."""
        key = self._redis_key(context.user_id)
        
        # 1. Update transient Redis state cache (24h TTL)
        try:
            await redis_client.setex(
                key,
                settings.PROFILE_CONTEXT_TTL_SECONDS,
                context.json()
            )
        except Exception as e:
            raise CacheException(f"Failed to write state context cache to Redis: {str(e)}")

        # 2. Update PostgreSQL (Durable workflow authoritative state)
        try:
            # Upsert User Profile data
            profile = await db.get(UserProfile, context.user_id)
            if profile:
                profile.name = context.profile_data.name
                profile.email = context.profile_data.email
                profile.phone = context.profile_data.phone
                profile.skills = context.profile_data.skills
                profile.experience = context.profile_data.experience
                profile.education = context.profile_data.education
                profile.raw_cv_text = context.profile_data.raw_cv_text
                profile.search_filters = context.job_search_filters
                # Log state transition if changed
                if profile.pipeline_state != context.pipeline_state:
                    audit = PipelineAuditLog(
                        user_id=context.user_id,
                        event_name="STATE_TRANSITION",
                        from_state=profile.pipeline_state,
                        to_state=context.pipeline_state,
                        details={"timestamp": datetime.utcnow().isoformat()}
                    )
                    db.add(audit)
                    profile.pipeline_state = context.pipeline_state
            else:
                profile = UserProfile(
                    user_id=context.user_id,
                    name=context.profile_data.name,
                    email=context.profile_data.email,
                    phone=context.profile_data.phone,
                    skills=context.profile_data.skills,
                    experience=context.profile_data.experience,
                    education=context.profile_data.education,
                    raw_cv_text=context.profile_data.raw_cv_text,
                    search_filters=context.job_search_filters,
                    pipeline_state=context.pipeline_state
                )
                db.add(profile)
                
                audit = PipelineAuditLog(
                    user_id=context.user_id,
                    event_name="STATE_INITIALIZED",
                    from_state="NONE",
                    to_state=context.pipeline_state,
                    details={"timestamp": datetime.utcnow().isoformat()}
                )
                db.add(audit)

            # Persist job listings cache
            for job in context.job_queue:
                job_record = await db.get(Job, job.job_id)
                if job_record:
                    job_record.verified_status = job.verified_status
                    job_record.match_score = job.match_score
                    job_record.match_reasoning = job.match_reasoning
                else:
                    new_job = Job(
                        job_id=job.job_id,
                        company_name=job.company_name,
                        job_title=job.job_title,
                        description=job.description,
                        location=job.location,
                        salary=job.salary,
                        url=job.url,
                        verified_status=job.verified_status,
                        match_score=job.match_score,
                        match_reasoning=job.match_reasoning
                    )
                    db.add(new_job)

            # Persist application records
            for app in context.active_applications:
                app_record = await db.get(ApplicationRecord, app.application_id)
                if app_record:
                    app_record.status = app.status
                    app_record.resume_path = app.resume_path
                    app_record.cover_letter_path = app.cover_letter_path
                else:
                    new_app = ApplicationRecord(
                        application_id=app.application_id,
                        user_id=context.user_id,
                        job_id=app.job_id,
                        method=app.method,
                        status=app.status,
                        resume_path=app.resume_path,
                        cover_letter_path=app.cover_letter_path,
                        timestamp=app.timestamp
                    )
                    db.add(new_app)

            await db.commit()
        except Exception as e:
            await db.rollback()
            raise DatabaseException(f"Failed to persist state context to PostgreSQL database: {str(e)}")
