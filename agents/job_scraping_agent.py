"""
Job Scraping Agent — /agents/job_scraping_agent.py

Agent 02 — AI-Based Career Assistant System
Member 2 — Job Scraping & Verification Engineer

Responsibilities:
  - Collect job/internship listings from LinkedIn and Indeed using search filters
    (keywords, location, job type, experience level)
  - Extract: company name, job title, description, required skills, location,
    salary, deadline, contact info
  - Assign unique job_id to each record; standardise fields across platforms
  - Model: gpt-4o-mini — do NOT upgrade without lead approval
  - Tools to call: scrape_linkedin_jobs, scrape_indeed_jobs

Error Handling:
  - API connection failures: retry with exponential backoff
  - Rate limiting: implement queue and schedule retries
  - Incomplete job data: log and flag for manual review — never crash the pipeline
"""

import asyncio
import logging
import json
from typing import Optional
from datetime import datetime

from tools.scraping_tools import scrape_indeed_jobs, scrape_linkedin_jobs

logger = logging.getLogger("career_assistant.job_scraping_agent")


class JobScrapingAgent:
    """
    AI-powered Job Scraping Agent that collects job/internship listings
    from LinkedIn and Indeed using search filters.

    Uses gpt-4o-mini for intelligent field extraction and standardisation.
    All outputs are valid JSON — never raises an unhandled exception.
    """

    # Model configured via settings (Gemini)
    try:
        from config import settings
        MODEL = getattr(settings, "LLM_MODEL", "gemini-2.5-flash")
    except ImportError:
        MODEL = "gemini-2.5-flash"

    def __init__(self, gemini_api_key: Optional[str] = None):
        """
        Initialise the Job Scraping Agent.

        Args:
            gemini_api_key: Gemini API key. If None, reads from GEMINI_API_KEY env var.
        """
        import os
        self.api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY", "")
        self._client = None
        self.scrape_history: list[dict] = []
        logger.info(f"JobScrapingAgent initialised (model={self.MODEL})")

    @property
    def client(self):
        """Lazy-initialise the OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
                )
            except ImportError:
                logger.warning("OpenAI package not installed. LLM features disabled.")
                self._client = None
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
        platforms: Optional[list[str]] = None,
        proxies: Optional[list[str]] = None,
        max_pages: int = 10,
    ) -> dict:
        """
        Main entry point: scrape jobs from one or more platforms.

        Args:
            keyword: Search keyword (e.g. "Python Developer")
            location: Location filter (e.g. "Lahore", "Karachi")
            job_type: Job type filter ("Full-time", "Part-time", "Internship", etc.)
            experience_level: Experience level filter
            platforms: List of platforms to scrape (default: ["indeed", "linkedin"])
            proxies: Optional proxy list for rotation
            max_pages: Maximum search pages to scrape per platform

        Returns:
            dict with:
              - status (str): "completed" | "partial" | "failed"
              - jobs (list[dict]): List of standardised job records
              - total_found (int): Total jobs found
              - by_platform (dict): Count per platform
              - errors (list[str]): Any error messages
              - scraped_at (str): ISO timestamp
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

        all_jobs: list[dict] = []
        errors: list[str] = []
        by_platform: dict[str, int] = {}

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

        if self.client:
            all_jobs = [self.enhance_job_with_llm(j) for j in all_jobs]

        result = {
            "status": status,
            "jobs": all_jobs,
            "total_found": len(all_jobs),
            "by_platform": by_platform,
            "errors": errors,
            "scraped_at": datetime.now().isoformat(),
        }

        # Track history
        self.scrape_history.append({
            "keyword": keyword,
            "location": location,
            "job_type": job_type,
            "total_found": len(all_jobs),
            "status": status,
            "scraped_at": result["scraped_at"],
        })

        logger.info(
            f"Scrape complete: status={status}, total_jobs={len(all_jobs)}, "
            f"by_platform={by_platform}, errors={len(errors)}"
        )
        return result

    def enhance_job_with_llm(self, job: dict) -> dict:
        """
        Use gpt-4o-mini to enhance a job record with better skill extraction
        and field standardisation.

        Args:
            job: A standardised job record.

        Returns:
            Enhanced job record with improved fields.

        Note: Gracefully degrades if OpenAI is unavailable.
        """
        if not self.client:
            logger.warning("OpenAI client not available — skipping LLM enhancement")
            return job

        try:
            prompt = f"""Analyse this job listing and extract structured information.

Job Title: {job.get('title', '')}
Company: {job.get('company', '')}
Location: {job.get('location', '')}
Description: {job.get('description', '')[:2000]}

Return a JSON object with:
- "required_skills": list of specific technical and soft skills mentioned
- "salary_range": standardised salary range if mentioned (e.g. "PKR 50,000 - 80,000/month")
- "experience_level": "entry", "mid", "senior", or "not_specified"
- "job_category": primary job category (e.g. "Software Engineering", "Data Science")
- "is_remote": true/false based on description
"""

            response = self.client.chat.completions.create(
                model=self.MODEL,
                messages=[
                    {"role": "system", "content": "You are a job listing analyser. Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=500,
                response_format={"type": "json_object"},
            )

            enhanced = json.loads(response.choices[0].message.content)

            # Merge enhanced fields into job record
            if enhanced.get("required_skills"):
                job["required_skills"] = enhanced["required_skills"]
            if enhanced.get("salary_range"):
                job["salary"] = enhanced["salary_range"]
            if enhanced.get("experience_level"):
                job["experience_level"] = enhanced["experience_level"]
            if enhanced.get("job_category"):
                job["job_category"] = enhanced["job_category"]
            if "is_remote" in enhanced:
                job["is_remote"] = enhanced["is_remote"]

            job["_llm_enhanced"] = True
            logger.info(f"LLM-enhanced job: {job.get('title', '')}")

        except Exception as exc:
            logger.warning(f"LLM enhancement failed for '{job.get('title', '')}': {exc}", exc_info=True)
            job["_llm_enhanced"] = False

        return job

    def to_json(self, jobs: list[dict]) -> str:
        """
        Serialise job list to valid JSON string.
        All agents return valid JSON for all inputs — never raise an unhandled exception.

        Args:
            jobs: List of job dicts.

        Returns:
            JSON string representation.
        """
        try:
            return json.dumps(jobs, indent=2, default=str, ensure_ascii=False)
        except Exception as exc:
            logger.error(f"JSON serialisation failed: {exc}", exc_info=True)
            return json.dumps({"error": str(exc), "jobs": []})

    def get_scrape_history(self) -> list[dict]:
        """Return the agent's scraping history."""
        return self.scrape_history
