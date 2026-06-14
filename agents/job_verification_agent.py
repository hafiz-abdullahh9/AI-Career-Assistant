"""
Job Verification Agent — /agents/job_verification_agent.py

Agent 02 — AI-Based Career Assistant System
Member 2 — Job Scraping & Verification Engineer
"""

import logging
import json
import os
from typing import Optional, List
from datetime import datetime

import sys

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
from tools.verification_tools import (
    verify_company,
    detect_duplicates,
    check_expired_posting,
    flag_suspicious_listing,
)
from tools.retry_helpers import retry_with_backoff
from config.schemas import VerifiedJobSchema, JobVerificationLLMOutput

logger = logging.getLogger("career_assistant.job_verification_agent")


class JobVerificationAgent:
    """
    AI-powered Job Verification Agent that validates, deduplicates,
    and scores job listings for quality and legitimacy.

    Outputs verified_status per job:
      - "verified"          → passed all checks
      - "rejected"          → duplicate, expired, or highly suspicious
      - "flagged_for_review" → borderline — needs human review

    Uses gpt-4o-mini via openai-agents SDK for advanced text analysis.
    All outputs are validated using Pydantic schemas.
    """

    MODEL = "gpt-4o-mini"

    def __init__(self, openai_api_key: Optional[str] = None):
        """
        Initialise the Job Verification Agent.

        Args:
            openai_api_key: OpenAI API key. If None, reads from OPENAI_API_KEY env var.
        """
        self.api_key = openai_api_key or os.environ.get("OPENAI_API_KEY", "")
        self._client = None
        
        # Initialize openai-agents SDK Agent
        self.sdk_agent = Agent(
            name="JobVerificationAgent",
            instructions=(
                "You are an expert job listing fraud analyst. Evaluate the listing "
                "and return a JSON verdict. Be conservative — only mark as "
                "'rejected' if you're confident it's fraudulent."
            ),
            model=self.MODEL
        )
        
        self.verification_stats = {
            "total_processed": 0,
            "verified": 0,
            "rejected": 0,
            "flagged_for_review": 0,
        }
        logger.info(f"JobVerificationAgent initialised with model={self.MODEL}")

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

    def verify_jobs(self, jobs: List[dict]) -> List[dict]:
        """
        Main entry point: run all verification checks on a list of jobs.
        """
        logger.info(f"Starting verification pipeline for {len(jobs)} jobs")
        verified_results: List[dict] = []

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
                    
                    verification_details["llm_used"] = False
                    verification_details["llm_analysis"] = None

                    # ── Compute initial verdict ──
                    verified_status = self._compute_verdict(
                        company_result=company_result,
                        expiry_result=expiry_result,
                        suspicion_result=suspicion_result,
                        is_duplicate=job.get("is_duplicate", False),
                        job=job,
                    )

                    job["verified_status"] = verified_status
                    job["verification_details"] = verification_details

                    # Run advanced LLM checks for borderline cases
                    if verified_status == "flagged_for_review" and self.api_key:
                        job = self.verify_with_llm(job)
                        # Re-read status in case LLM resolved it
                        verified_status = job["verified_status"]

                    # Validate output matches VerifiedJobSchema Pydantic model
                    validated = VerifiedJobSchema.model_validate(job)
                    validated_job = validated.model_dump()
                    
                    verified_results.append(validated_job)

                    # Update stats
                    self.verification_stats["total_processed"] += 1
                    self.verification_stats[verified_status] += 1

                except Exception as exc:
                    logger.error(f"Verification error for job '{job.get('title', 'unknown')}': {exc}", exc_info=True)
                    # Safe fallback configuration
                    job["verified_status"] = "flagged_for_review"
                    job["verification_details"] = {
                        "company_verification": company_result if 'company_result' in locals() else {"company_name": job.get("company", ""), "is_verified": False, "confidence": 0.0, "flags": [f"Error: {exc}"], "verification_method": "fallback"},
                        "expiry_check": expiry_result if 'expiry_result' in locals() else {"is_expired": False, "expiry_reason": f"Fallback due to: {exc}"},
                        "suspicion_check": suspicion_result if 'suspicion_result' in locals() else {"is_suspicious": True, "suspicion_score": 0.5, "flags": [f"Fallback due to: {exc}"]},
                        "is_duplicate": job.get("is_duplicate", False),
                        "duplicate_of": job.get("duplicate_of", ""),
                        "duplicate_reason": job.get("duplicate_reason", ""),
                        "error": str(exc),
                        "note": "Flagged due to verification processing error",
                        "llm_used": False,
                        "llm_analysis": None
                    }
                    try:
                        validated = VerifiedJobSchema.model_validate(job)
                        verified_results.append(validated.model_dump())
                    except Exception as fallback_val_exc:
                        logger.error(f"Fallback validation failed: {fallback_val_exc}")
                        verified_results.append(job)
                        
                    self.verification_stats["total_processed"] += 1
                    self.verification_stats["flagged_for_review"] += 1

        except Exception as exc:
            logger.error(f"Verification pipeline error: {exc}", exc_info=True)
            # Never crash — mark all unprocessed jobs for review
            for job in jobs:
                if "verified_status" not in job:
                    job["verified_status"] = "flagged_for_review"
                    job["verification_details"] = {
                        "company_verification": {"company_name": job.get("company", ""), "is_verified": False, "confidence": 0.0, "flags": [], "verification_method": "fallback"},
                        "expiry_check": {"is_expired": False, "expiry_reason": ""},
                        "suspicion_check": {"is_suspicious": False, "suspicion_score": 0.0, "flags": []},
                        "is_duplicate": False,
                        "duplicate_of": "",
                        "duplicate_reason": "",
                        "error": str(exc),
                        "note": "Pipeline-level error — flagged for manual review",
                        "llm_used": False,
                        "llm_analysis": None
                    }
                    verified_results.append(job)

        logger.info(
            f"Verification complete: "
            f"{self.verification_stats['verified']} verified, "
            f"{self.verification_stats['rejected']} rejected, "
            f"{self.verification_stats['flagged_for_review']} flagged"
        )

        return verified_results

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
        """
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

        if suspicion_score >= 0.3:
            return "flagged_for_review"

        if company_confidence <= 0.5:
            return "flagged_for_review"

        if not job.get("title") or not job.get("company"):
            return "flagged_for_review"

        if job.get("_flagged_for_review"):
            return "flagged_for_review"

        return "verified"

    @retry_with_backoff()
    def verify_with_llm(self, job: dict) -> dict:
        """
        Use gpt-4o-mini via openai-agents SDK for verification of borderline cases.
        """
        if not self.api_key:
            logger.warning("No API key available for LLM verification.")
            return job

        if "OPENAI_API_KEY" not in os.environ or os.environ["OPENAI_API_KEY"] != self.api_key:
            os.environ["OPENAI_API_KEY"] = self.api_key

        try:
            flags = job.get("verification_details", {}).get("suspicion_check", {}).get("flags", [])

            prompt = f"""Analyse this job listing for legitimacy. It has been flagged for review.

Title: {job.get('title', '')}
Company: {job.get('company', '')}
Location: {job.get('location', '')}
Description (first 1500 chars): {job.get('description', '')[:1500]}
Apply Link: {job.get('apply_link', '')}
Flags: {json.dumps(flags)}

Based on these flags and the content, determine legitimacy. Output a JSON object matching this schema:
{{
  "is_legitimate": true | false,
  "confidence": 0.0 to 1.0,
  "verdict": "verified" | "rejected" | "flagged_for_review",
  "explanation": "brief reasoning"
}}
"""

            run_result = Runner.run_sync(
                self.sdk_agent,
                prompt
            )
            content = run_result.output

            cleaned_content = content.strip()
            if cleaned_content.startswith("```"):
                lines = cleaned_content.splitlines()
                if len(lines) >= 2:
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines[-1].startswith("```"):
                        lines = lines[:-1]
                cleaned_content = "\n".join(lines).strip()

            llm_result = JobVerificationLLMOutput.model_validate_json(cleaned_content)
            verdict = llm_result.verdict

            if verdict in ("verified", "rejected", "flagged_for_review"):
                job["verified_status"] = verdict
                job["verification_details"]["llm_analysis"] = llm_result.model_dump()
                job["verification_details"]["llm_used"] = True
                logger.info(
                    f"LLM verdict via SDK for '{job.get('title', '')}': {verdict} "
                    f"(confidence: {llm_result.confidence})"
                )

        except Exception as exc:
            logger.warning(f"LLM verification failed for '{job.get('title', '')}': {exc}")
            job["verification_details"]["llm_used"] = False

        return job

    def get_verified_jobs(self, jobs: List[dict]) -> List[dict]:
        """Return only jobs with verified_status == 'verified'."""
        return [j for j in jobs if j.get("verified_status") == "verified"]

    def get_rejected_jobs(self, jobs: List[dict]) -> List[dict]:
        """Return only jobs with verified_status == 'rejected'."""
        return [j for j in jobs if j.get("verified_status") == "rejected"]

    def get_flagged_jobs(self, jobs: List[dict]) -> List[dict]:
        """Return only jobs with verified_status == 'flagged_for_review'."""
        return [j for j in jobs if j.get("verified_status") == "flagged_for_review"]

    def get_stats(self) -> dict:
        """Return verification statistics."""
        return self.verification_stats.copy()

    def to_json(self, jobs: List[dict]) -> str:
        """Serialise job list to valid JSON string."""
        try:
            return json.dumps(jobs, indent=2, default=str, ensure_ascii=False)
        except Exception as exc:
            logger.error(f"JSON serialisation failed: {exc}", exc_info=True)
            return json.dumps({"error": str(exc), "jobs": []})

    def generate_report(self, jobs: List[dict]) -> dict:
        """Generate a verification summary report."""
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
