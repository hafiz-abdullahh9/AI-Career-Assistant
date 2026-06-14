"""
Job Scraping Agent — /agents/job_scraping_agent.py

Agent 02 — AI-Based Career Assistant System
Member 2 — Job Scraping & Verification Engineer
"""

import asyncio
import logging
import json
import os
from typing import Optional, List
from datetime import datetime

import sys
import os

# Bypass local namespace shadowing of 'agents' module
_local_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_sys_path_backup = sys.path.copy()
sys.path = [p for p in sys.path if os.path.abspath(p) != os.path.abspath(_local_dir)]

_agents_module_backup = sys.modules.get('agents', None)
if 'agents' in sys.modules:
    del sys.modules['agents']

try:
    from agents import Agent, Runner
finally:
    sys.path = _sys_path_backup
    if _agents_module_backup is not None:
        sys.modules['agents'] = _agents_module_backup
from tools.scraping_tools import scrape_indeed_jobs, scrape_linkedin_jobs
from tools.retry_helpers import retry_with_backoff
from config.schemas import JobEnhancement, ScrapedJobSchema

logger = logging.getLogger("career_assistant.job_scraping_agent")


class JobScrapingAgent:
    """
    AI-powered Job Scraping Agent that collects job/internship listings
    from LinkedIn and Indeed using search filters.

    Uses gpt-4o-mini via openai-agents SDK for intelligent field extraction.
    All outputs are validated using Pydantic schemas.
    """

    MODEL = "gpt-4o-mini"

    def __init__(self, openai_api_key: Optional[str] = None):
        """
        Initialise the Job Scraping Agent.

        Args:
            openai_api_key: OpenAI API key. If None, reads from OPENAI_API_KEY env var.
        """
        self.api_key = openai_api_key or os.environ.get("OPENAI_API_KEY", "")
        
        # Initialize standard OpenAI client for backward compatibility
        self._client = None
        
        # Initialize openai-agents SDK Agent
        self.sdk_agent = Agent(
            name="JobScrapingAgent",
            instructions=(
                "You are an expert job listing analyser. Your task is to extract structured details from "
                "job postings and output them as a clean JSON object. Ensure that the values correspond exactly "
                "to the requested properties."
            ),
            model=self.MODEL
        )
        
        self.scrape_history: List[dict] = []
        logger.info(f"JobScrapingAgent initialised with model={self.MODEL}")

    @property
    def client(self):
        """Lazy-initialise standard OpenAI client for fallback/legacy functions."""
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialise OpenAI client: {e}", exc_info=True)
                self._client = None
        return self._client

    async def scrape_jobs(
        self,
        keyword: str,
        location: str = "",
        job_type: str = "",
        experience_level: str = "",
        platforms: Optional[List[str]] = None,
        proxies: Optional[List[str]] = None,
        max_pages: int = 10,
    ) -> dict:
        """
        Main entry point: scrape jobs from one or more platforms.
        """
        if platforms is None:
            platforms = ["indeed", "linkedin"]

        try:
            from config import settings
            default_proxies = getattr(settings, "PROXIES", None)
        except ImportError:
            default_proxies = None
            
        active_proxies = proxies if proxies is not None else default_proxies

        logger.info(
            f"Scraping jobs: keyword='{keyword}', location='{location}', "
            f"job_type='{job_type}', platforms={platforms}"
        )

        all_jobs: List[dict] = []
        errors: List[str] = []
        by_platform: dict = {}

        for platform in platforms:
            try:
                if platform.lower() == "indeed":
                    jobs = await scrape_indeed_jobs(
                        keyword=keyword,
                        location=location,
                        job_type=job_type,
                        experience_level=experience_level,
                        proxies=active_proxies,
                        max_pages=max_pages,
                    )
                elif platform.lower() == "linkedin":
                    jobs = await scrape_linkedin_jobs(
                        keyword=keyword,
                        location=location,
                        job_type=job_type,
                        experience_level=experience_level,
                        proxies=active_proxies,
                        max_pages=max_pages,
                    )
                else:
                    logger.warning(f"Unknown platform: {platform}")
                    errors.append(f"Unknown platform: {platform}")
                    continue

                by_platform[platform] = len(jobs)
                all_jobs.extend(jobs)
                logger.info(f"Scraped {len(jobs)} jobs from {platform}")

            except Exception as exc:
                error_msg = f"{platform} scraping failed: {type(exc).__name__}: {exc}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)
                by_platform[platform] = 0

        # Determine overall status
        if not all_jobs and errors:
            status = "failed"
        elif errors:
            status = "partial"
        else:
            status = "completed"

        # Enhance scraped listings with LLM features
        enhanced_jobs: List[dict] = []
        for job in all_jobs:
            try:
                enhanced_job = self.enhance_job_with_llm(job)
                # Validate schema output using Pydantic
                validated = ScrapedJobSchema.model_validate(enhanced_job)
                enhanced_jobs.append(validated.model_dump())
            except Exception as exc:
                logger.warning(f"Enhancement or validation failed for job '{job.get('title')}': {exc}")
                # Fallback to unenhanced standardized job to avoid pipeline crash
                try:
                    job["_llm_enhanced"] = False
                    validated = ScrapedJobSchema.model_validate(job)
                    enhanced_jobs.append(validated.model_dump())
                except Exception as val_exc:
                    logger.error(f"Critical validation failure on fallback: {val_exc}")

        result = {
            "status": status,
            "jobs": enhanced_jobs,
            "total_found": len(enhanced_jobs),
            "by_platform": by_platform,
            "errors": errors,
            "scraped_at": datetime.now().isoformat(),
        }

        self.scrape_history.append({
            "keyword": keyword,
            "location": location,
            "job_type": job_type,
            "total_found": len(enhanced_jobs),
            "status": status,
            "scraped_at": result["scraped_at"],
        })

        logger.info(
            f"Scrape complete: status={status}, total_jobs={len(enhanced_jobs)}, "
            f"by_platform={by_platform}, errors={len(errors)}"
        )
        return result

    @retry_with_backoff()
    def enhance_job_with_llm(self, job: dict) -> dict:
        """
        Use gpt-4o-mini via openai-agents SDK to enhance a job record.
        """
        # Ensure we have our API key loaded
        if not self.api_key:
            logger.warning("No API key available for LLM enhancement.")
            job["_llm_enhanced"] = False
            return job

        # Re-set key in environment just in case
        if "OPENAI_API_KEY" not in os.environ or os.environ["OPENAI_API_KEY"] != self.api_key:
            os.environ["OPENAI_API_KEY"] = self.api_key

        prompt = f"""Analyse this job listing and extract structured information.

Job Title: {job.get('title', '')}
Company: {job.get('company', '')}
Location: {job.get('location', '')}
Description: {job.get('description', '')[:2000]}

Return a JSON object matching this schema definition:
{{
  "required_skills": ["list", "of", "skills"],
  "salary_range": "standardised salary string or null",
  "experience_level": "entry" | "mid" | "senior" | "not_specified",
  "job_category": "primary job category string",
  "is_remote": true | false
}}
"""

        try:
            # Call openai-agents SDK Runner to process synchronously
            run_result = Runner.run_sync(
                self.sdk_agent,
                prompt
            )
            content = run_result.output

            # Strip markdown code blocks if present
            cleaned_content = content.strip()
            if cleaned_content.startswith("```"):
                lines = cleaned_content.splitlines()
                if len(lines) >= 2:
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines[-1].startswith("```"):
                        lines = lines[:-1]
                cleaned_content = "\n".join(lines).strip()

            enhanced = JobEnhancement.model_validate_json(cleaned_content)

            # Merge validated fields into standard job record
            job["required_skills"] = list(set(job.get("required_skills", []) + enhanced.required_skills))
            if enhanced.salary_range:
                job["salary"] = enhanced.salary_range
            job["experience_level"] = enhanced.experience_level
            job["job_category"] = enhanced.job_category
            job["is_remote"] = enhanced.is_remote
            job["_llm_enhanced"] = True
            logger.info(f"LLM-enhanced job via SDK: {job.get('title', '')}")

        except Exception as exc:
            logger.warning(f"LLM enhancement failed for '{job.get('title', '')}': {exc}")
            job["_llm_enhanced"] = False

        return job

    def to_json(self, jobs: List[dict]) -> str:
        """Serialise job list to valid JSON string."""
        try:
            return json.dumps(jobs, indent=2, default=str, ensure_ascii=False)
        except Exception as exc:
            logger.error(f"JSON serialisation failed: {exc}", exc_info=True)
            return json.dumps({"error": str(exc), "jobs": []})

    def get_scrape_history(self) -> List[dict]:
        """Return the agent's scraping history."""
        return self.scrape_history
