"""
Job Verification Agent — /agents/job_verification_agent.py

Agent 02 — AI-Based Career Assistant System
Member 2 — Job Scraping & Verification Engineer

Responsibilities:
  - Detect duplicate postings across platforms
  - Verify company legitimacy using public records (verify_company tool)
  - Identify expired postings by comparing posted_date vs application_deadline
  - Flag suspicious listings (spelling errors, unusual payment requests,
    invalid contact links)
  - Output verified_status: verified / rejected / flagged_for_review per job

Error Handling:
  - API connection failures: retry with exponential backoff
  - Rate limiting: implement queue and schedule retries
  - Incomplete job data: log and flag for manual review — never crash the pipeline
"""

import logging
import json
from typing import Optional
from datetime import datetime

from tools.verification_tools import (
    verify_company,
    detect_duplicates,
    check_expired_posting,
    flag_suspicious_listing,
)

logger = logging.getLogger("career_assistant.job_verification_agent")


class JobVerificationAgent:
    """
    AI-powered Job Verification Agent that validates, deduplicates,
    and scores job listings for quality and legitimacy.

    Outputs verified_status per job:
      - "verified"          → passed all checks
      - "rejected"          → duplicate, expired, or highly suspicious
      - "flagged_for_review" → borderline — needs human review

    Uses gpt-4o-mini for advanced text analysis.
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
        Initialise the Job Verification Agent.

        Args:
            gemini_api_key: Gemini API key. If None, reads from GEMINI_API_KEY env var.
        """
        import os
        self.api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY", "")
        self._client = None
        self.verification_stats = {
            "total_processed": 0,
            "verified": 0,
            "rejected": 0,
            "flagged_for_review": 0,
        }
        logger.info(f"JobVerificationAgent initialised (model={self.MODEL})")

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

    def verify_jobs(self, jobs: list[dict]) -> list[dict]:
        """
        Main entry point: run all verification checks on a list of jobs.

        Pipeline:
          1. Duplicate detection (across all platforms)
          2. Company verification
          3. Expired posting check
          4. Suspicious listing detection
          5. Final verdict assignment

        Args:
            jobs: List of standardised job records from the Scraping Agent.

        Returns:
            Same list with added verification fields per job:
              - verified_status: "verified" / "rejected" / "flagged_for_review"
              - verification_details: dict with all check results
        """
        logger.info(f"Starting verification pipeline for {len(jobs)} jobs")

        try:
            # Step 1: Duplicate detection (batch operation — cross-platform)
            jobs = detect_duplicates(jobs)

            # Steps 2–5: Per-job verification
            for job in jobs:
                try:
                    verification_details = {}

                    # Step 2: Company verification
                    company_result = verify_company(job.get("company", ""))
                    verification_details["company_verification"] = company_result

                    # Step 3: Expired posting check
                    expiry_result = check_expired_posting(job)
                    verification_details["expiry_check"] = expiry_result

                    # Step 4: Suspicious listing detection
                    suspicion_result = flag_suspicious_listing(job)
                    verification_details["suspicion_check"] = suspicion_result

                    # Step 5: Duplicate info (already set by detect_duplicates)
                    verification_details["is_duplicate"] = job.get("is_duplicate", False)
                    verification_details["duplicate_of"] = job.get("duplicate_of", "")
                    verification_details["duplicate_reason"] = job.get("duplicate_reason", "")

                    # ── Final verdict ──
                    verified_status = self._compute_verdict(
                        company_result=company_result,
                        expiry_result=expiry_result,
                        suspicion_result=suspicion_result,
                        is_duplicate=job.get("is_duplicate", False),
                        job=job,
                    )

                    job["verified_status"] = verified_status
                    job["verification_details"] = verification_details

                    if job.get("verified_status") == "flagged_for_review" and self.client:
                        job = self.verify_with_llm(job)

                    # Update stats
                    self.verification_stats["total_processed"] += 1
                    self.verification_stats[verified_status] += 1

                except Exception as exc:
                    logger.error(f"Verification error for job '{job.get('title', 'unknown')}': {exc}", exc_info=True)
                    job["verified_status"] = "flagged_for_review"
                    job["verification_details"] = {
                        "error": str(exc),
                        "note": "Flagged due to verification processing error",
                    }
                    self.verification_stats["total_processed"] += 1
                    self.verification_stats["flagged_for_review"] += 1

        except Exception as exc:
            logger.error(f"Verification pipeline error: {exc}", exc_info=True)
            # Never crash — mark all unprocessed jobs for review
            for job in jobs:
                if "verified_status" not in job:
                    job["verified_status"] = "flagged_for_review"
                    job["verification_details"] = {
                        "error": str(exc),
                        "note": "Pipeline-level error — flagged for manual review",
                    }

        # Summary logging
        logger.info(
            f"Verification complete: "
            f"{self.verification_stats['verified']} verified, "
            f"{self.verification_stats['rejected']} rejected, "
            f"{self.verification_stats['flagged_for_review']} flagged"
        )

        return jobs

    def _compute_verdict(
        self,
        company_result: dict,
        expiry_result: dict,
        suspicion_result: dict,
        is_duplicate: bool,
        job: dict,
    ) -> str:
        """
        Compute the final verified_status based on all check results.

        Decision logic:
          - REJECTED if:
            • Is a duplicate
            • Is expired (deadline passed)
            • Suspicion score >= 0.6
            • Company verification confidence <= 0.2
          - FLAGGED_FOR_REVIEW if:
            • Suspicion score >= 0.3
            • Company verification confidence <= 0.5
            • Missing critical fields
            • Already marked as _flagged_for_review by scraping agent
          - VERIFIED otherwise

        Returns:
            "verified" | "rejected" | "flagged_for_review"
        """
        # ── Automatic REJECTION ──
        if is_duplicate:
            return "rejected"

        if expiry_result.get("is_expired", False):
            return "rejected"

        suspicion_score = suspicion_result.get("suspicion_score", 0.0)
        if suspicion_score >= 0.6:
            return "rejected"

        company_confidence = company_result.get("confidence", 0.7)
        if company_confidence <= 0.2:
            return "rejected"

        # ── FLAGGED FOR REVIEW ──
        if suspicion_score >= 0.3:
            return "flagged_for_review"

        if company_confidence <= 0.5:
            return "flagged_for_review"

        if not job.get("title") or not job.get("company"):
            return "flagged_for_review"

        if job.get("_flagged_for_review"):
            return "flagged_for_review"

        # ── VERIFIED ──
        return "verified"

    def verify_with_llm(self, job: dict) -> dict:
        """
        Use gpt-4o-mini for advanced verification of borderline cases.

        Only called for jobs with verified_status == "flagged_for_review".

        Args:
            job: A job record with verification fields already set.

        Returns:
            Updated job record with LLM-refined verdict.
        """
        if not self.client:
            logger.warning("OpenAI client not available — skipping LLM verification")
            return job

        try:
            flags = job.get("verification_details", {}).get("suspicion_check", {}).get("flags", [])

            prompt = f"""Analyse this job listing for legitimacy. It has been flagged for review.

Title: {job.get('title', '')}
Company: {job.get('company', '')}
Location: {job.get('location', '')}
Description (first 1500 chars): {job.get('description', '')[:1500]}
Apply Link: {job.get('apply_link', '')}
Flags: {json.dumps(flags)}

Based on these flags and the content, determine:
1. Is this a legitimate job posting? (true/false)
2. What is your confidence? (0.0 to 1.0)
3. Should this be "verified", "rejected", or "flagged_for_review"?
4. Brief explanation.

Return a JSON object with keys: is_legitimate, confidence, verdict, explanation
"""

            response = self.client.chat.completions.create(
                model=self.MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a job listing fraud analyst. Evaluate the listing "
                            "and return a JSON verdict. Be conservative — only mark as "
                            "'rejected' if you're confident it's fraudulent."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=300,
                response_format={"type": "json_object"},
            )

            llm_result = json.loads(response.choices[0].message.content)

            verdict = llm_result.get("verdict", "flagged_for_review")
            if verdict in ("verified", "rejected", "flagged_for_review"):
                job["verified_status"] = verdict
                job["verification_details"]["llm_analysis"] = llm_result
                job["verification_details"]["llm_used"] = True
                logger.info(
                    f"LLM verdict for '{job.get('title', '')}': {verdict} "
                    f"(confidence: {llm_result.get('confidence', 'N/A')})"
                )

        except Exception as exc:
            logger.warning(f"LLM verification failed for '{job.get('title', '')}': {exc}", exc_info=True)
            job["verification_details"]["llm_used"] = False

        return job

    def get_verified_jobs(self, jobs: list[dict]) -> list[dict]:
        """Return only jobs with verified_status == 'verified'."""
        return [j for j in jobs if j.get("verified_status") == "verified"]

    def get_rejected_jobs(self, jobs: list[dict]) -> list[dict]:
        """Return only jobs with verified_status == 'rejected'."""
        return [j for j in jobs if j.get("verified_status") == "rejected"]

    def get_flagged_jobs(self, jobs: list[dict]) -> list[dict]:
        """Return only jobs with verified_status == 'flagged_for_review'."""
        return [j for j in jobs if j.get("verified_status") == "flagged_for_review"]

    def get_stats(self) -> dict:
        """Return verification statistics."""
        return self.verification_stats.copy()

    def to_json(self, jobs: list[dict]) -> str:
        """
        Serialise job list to valid JSON string.
        All agents return valid JSON for all inputs — never raise an unhandled exception.
        """
        try:
            return json.dumps(jobs, indent=2, default=str, ensure_ascii=False)
        except Exception as exc:
            logger.error(f"JSON serialisation failed: {exc}", exc_info=True)
            return json.dumps({"error": str(exc), "jobs": []})

    def generate_report(self, jobs: list[dict]) -> dict:
        """
        Generate a verification summary report.

        Args:
            jobs: The verified job list.

        Returns:
            dict with summary statistics and breakdown.
        """
        total = len(jobs)
        verified = sum(1 for j in jobs if j.get("verified_status") == "verified")
        rejected = sum(1 for j in jobs if j.get("verified_status") == "rejected")
        flagged = sum(1 for j in jobs if j.get("verified_status") == "flagged_for_review")
        duplicates = sum(1 for j in jobs if j.get("is_duplicate", False))
        expired = sum(
            1 for j in jobs
            if j.get("verification_details", {}).get("expiry_check", {}).get("is_expired", False)
        )
        suspicious = sum(
            1 for j in jobs
            if j.get("verification_details", {}).get("suspicion_check", {}).get("is_suspicious", False)
        )

        accuracy = verified / total if total > 0 else 0.0

        return {
            "total_processed": total,
            "verified": verified,
            "rejected": rejected,
            "flagged_for_review": flagged,
            "duplicates_found": duplicates,
            "expired_found": expired,
            "suspicious_found": suspicious,
            "verification_accuracy": round(accuracy, 4),
            "report_generated_at": datetime.now().isoformat(),
        }
