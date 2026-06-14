import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from core.exceptions import CareerAssistantException, OrchestrationError, AgentExecutionError, IntegrityCheckFailed
from infra.profile_context import ProfileContext, ProfileContextManager, PipelineAuditLog

logger = logging.getLogger("career_orchestrator")

class CareerOrchestrator:
    def __init__(self, context_manager: Optional[ProfileContextManager] = None):
        """Initializes the coordinator with a schema manager for session states."""
        self.context_manager = context_manager or ProfileContextManager()

    async def transition_state(
        self,
        context: ProfileContext,
        next_state: str,
        event_name: str,
        db: AsyncSession,
        redis_client,
        details: Optional[dict] = None
    ) -> None:
        """Transitions state, adds transactional audit logging, and persists results."""
        old_state = context.pipeline_state
        context.pipeline_state = next_state
        context.last_updated = datetime.utcnow()

        logger.info(
            f"Pipeline state transition for user {context.user_id}: "
            f"{old_state} -> {next_state} (Event: {event_name})"
        )

        # Persistence of context updates state in PostgreSQL & Redis
        await self.context_manager.save_context(context, db, redis_client)

    async def run_discovery_stage(
        self,
        user_id: str,
        db: AsyncSession,
        redis_client,
        scrape_func,      # Injected placeholder tool (Member 2 logic)
        verify_func       # Injected placeholder tool (Member 2 logic)
    ) -> ProfileContext:
        """Executes the Job Discovery and Company Verification sequence."""
        context = await self.context_manager.load_context(user_id, db, redis_client)
        if not context:
            raise OrchestrationError(f"ProfileContext not found for user: {user_id}")

        await self.transition_state(context, "STATE_DISCOVERY", "TRIGGER_DISCOVERY", db, redis_client)

        try:
            # 1. Fetch search filters from context and execute scraper
            filters = context.job_search_filters
            keywords = filters.get("keywords", ["Software Engineer"])
            location = filters.get("location", "Remote")
            
            logger.info(f"Triggering LinkedIn & Indeed scrapers for keywords: {keywords}")
            scraped_jobs_res = await scrape_func(keywords=keywords, location=location)
            
            # 2. Hand off to verification agent logic
            await self.transition_state(context, "STATE_VERIFICATION", "SCRAPING_COMPLETE", db, redis_client)
            
            verified_jobs = []
            for raw_job in scraped_jobs_res.get("jobs", []):
                company = raw_job.get("company_name", "")
                verification = await verify_func(company_name=company)
                
                # Standardize job details into our ProfileContext JobItem schema
                verified_status = "verified" if verification.get("verified_status") else "flagged_for_review"
                
                from infra.profile_context import JobItem
                job_item = JobItem(
                    job_id=raw_job.get("job_id", ""),
                    company_name=company,
                    job_title=raw_job.get("job_title", ""),
                    description=raw_job.get("description", ""),
                    location=raw_job.get("location", ""),
                    salary=raw_job.get("salary"),
                    url=raw_job.get("url", ""),
                    verified_status=verified_status
                )
                verified_jobs.append(job_item)
            
            context.job_queue = verified_jobs
            await self.transition_state(context, "STATE_MATCHING", "VERIFICATION_COMPLETE", db, redis_client)
            
        except Exception as e:
            await self.transition_state(context, "STATE_DISCOVERY_FAILED", "ERROR_ENCOUNTERED", db, redis_client)
            raise AgentExecutionError("DiscoveryAgent", str(e), "DISCOVERY")

        return context

    async def run_matching_stage(
        self,
        user_id: str,
        db: AsyncSession,
        redis_client,
        match_func        # Injected placeholder tool (Member 3 logic)
    ) -> ProfileContext:
        """Calculates compatibility scores and transitions to selection wait."""
        context = await self.context_manager.load_context(user_id, db, redis_client)
        if not context:
            raise OrchestrationError(f"ProfileContext not found for user: {user_id}")

        try:
            profile_skills = context.profile_data.skills
            profile_exp = context.profile_data.experience

            # Update match scores in job queue
            for job in context.job_queue:
                job_reqs = {"skills": [job.job_title], "min_experience_years": 0} # Simplified representation
                match_res = await match_func(
                    profile_skills=profile_skills,
                    profile_experience=profile_exp,
                    job_requirements=job_reqs
                )
                job.match_score = match_res.get("compatibility_score", 0.0)
                job.match_reasoning = match_res.get("reasoning", "")

            # Sort job queue in place descending by score
            context.job_queue.sort(key=lambda j: j.match_score or 0.0, reverse=True)
            
            await self.transition_state(context, "STATE_SELECTION_WAIT", "MATCHING_COMPLETE", db, redis_client)
        except Exception as e:
            await self.transition_state(context, "STATE_MATCHING_FAILED", "ERROR_ENCOUNTERED", db, redis_client)
            raise AgentExecutionError("JobMatchingAgent", str(e), "MATCHING")

        return context

    async def run_customization_stage(
        self,
        user_id: str,
        job_id: str,
        db: AsyncSession,
        redis_client,
        resume_func,      # Injected placeholder tool (Member 3 logic)
        cover_letter_func,# Injected placeholder tool (Member 3 logic)
        integrity_func    # Injected placeholder monitor guardrail (M1 responsibility)
    ) -> ProfileContext:
        """Optimizes documents per job and triggers factual integrity guardrail verification."""
        context = await self.context_manager.load_context(user_id, db, redis_client)
        if not context:
            raise OrchestrationError(f"ProfileContext not found for user: {user_id}")

        await self.transition_state(context, "STATE_CUSTOMIZATION", "JOB_SELECTED", db, redis_client)

        try:
            # Retrieve selected job details
            selected_job = next((j for j in context.job_queue if j.job_id == job_id), None)
            if not selected_job:
                raise OrchestrationError(f"Selected job ID {job_id} not found in user queue")

            # Execute optimizations in parallel
            profile_dict = context.profile_data.dict()
            job_dict = selected_job.dict()

            res_doc = await resume_func(profile_data=profile_dict, job_details=job_dict)
            cl_doc = await cover_letter_func(profile_data=profile_dict, job_details=job_dict)

            # Passive guardrail validation: Check document factual integrity against profile context
            await self.transition_state(context, "STATE_GUARDRAIL_CHECK", "DOCUMENTS_GENERATED", db, redis_client)
            
            integrity_check = await integrity_func(
                original_profile=profile_dict,
                tailored_resume_path=res_doc.get("pdf_path")
            )

            if not integrity_check.get("factual_integrity_verified", False):
                await self.transition_state(context, "STATE_GUARDRAIL_BREACH", "INTEGRITY_BREACH", db, redis_client)
                raise IntegrityCheckFailed("Factual mismatch detected in generated resume compared to source CV.")

            # Record successfully generated applications draft
            from infra.profile_context import ApplicationItem
            app_item = ApplicationItem(
                application_id=f"app-{job_id}",
                job_id=job_id,
                method="web-form", # Default selection
                status="draft",
                resume_path=res_doc.get("pdf_path"),
                cover_letter_path=cl_doc.get("pdf_path"),
                timestamp=datetime.utcnow()
            )
            
            # Avoid duplicate drafts
            context.active_applications = [a for a in context.active_applications if a.job_id != job_id]
            context.active_applications.append(app_item)

            await self.transition_state(context, "STATE_APPLICATION", "GUARDRAIL_PASSED", db, redis_client)
        except IntegrityCheckFailed as e:
            raise AgentExecutionError("ProfileIntegrityMonitor", str(e), "INTEGRITY_CHECK")
        except Exception as e:
            await self.transition_state(context, "STATE_CUSTOMIZATION_FAILED", "ERROR_ENCOUNTERED", db, redis_client)
            raise AgentExecutionError("DocumentGenerationAgent", str(e), "CUSTOMIZATION")

        return context
