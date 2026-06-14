"""
Member 3 — Cover Letter Agent
Uses the OpenAI Agents SDK to generate tailored cover letters while maintaining 100% factual accuracy.
"""

import os
import sys
from typing import Optional
from loguru import logger

# Import external agents SDK safely to avoid importing local agents package
local_agents = sys.modules.get('agents')
if 'agents' in sys.modules:
    del sys.modules['agents']

original_path = sys.path.copy()
try:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path = [p for p in sys.path if os.path.abspath(p) != os.path.abspath(project_root)]
    from agents import Agent, Runner, function_tool
finally:
    sys.path = original_path
    if local_agents:
        sys.modules['agents'] = local_agents

from models.matching_models import (
    UserProfile,
    VerifiedJobListing,
    MatchResult,
    ResumeOutput,
    CompanyInfo,
    CoverLetterOutput,
)
from tools.document_tools import generate_cover_letter


# ---------------------------------------------------------------------------
# Tool Registration
# ---------------------------------------------------------------------------

@function_tool(name_override="generate_cover_letter")
def generate_cover_letter_tool(
    user_profile: UserProfile,
    job_listing: VerifiedJobListing,
    match_result: MatchResult,
    resume_output: ResumeOutput,
    company_info: Optional[CompanyInfo] = None
) -> CoverLetterOutput:
    """
    Generate an ATS-optimized cover letter tailored to the job description.
    All claims about the user MUST be 100% factually accurate.
    """
    return generate_cover_letter(user_profile, job_listing, match_result, resume_output, company_info)


# ---------------------------------------------------------------------------
# Agent Definition
# ---------------------------------------------------------------------------

AGENT_MODEL = os.getenv("AGENT_MODEL", "gpt-4o-mini")

cover_letter_agent = Agent(
    name="Cover Letter Generation Agent",
    model=AGENT_MODEL,
    instructions=(
        "You are an expert Cover Letter Generation Agent in the AI Career Assistant System.\n"
        "Your task is to write a tailored, professional business cover letter complementing the resume.\n"
        "CRITICAL CONSTRAINT: You must maintain 100% factual accuracy. NEVER invent skills, "
        "experience, achievements, or credentials. Only reference existing candidate information.\n"
        "Incorporate target job description keywords naturally and reference company details when available.\n"
        "You have access to the generate_cover_letter tool."
    ),
    tools=[generate_cover_letter_tool],
)


# ---------------------------------------------------------------------------
# Programmatic API
# ---------------------------------------------------------------------------

async def optimize_cover_letter(
    user_profile: UserProfile,
    job_listing: VerifiedJobListing,
    match_result: MatchResult,
    resume_output: ResumeOutput,
    company_info: Optional[CompanyInfo] = None
) -> CoverLetterOutput:
    """
    Programmatic entry point to run the cover letter generation pipeline.
    """
    logger.info(f"Starting cover letter generation for user: {user_profile.user_id} and job: {job_listing.job_id}")
    
    # Run agent runner or call generate_cover_letter directly to bypass LLM latency when programmatic
    output = generate_cover_letter(user_profile, job_listing, match_result, resume_output, company_info)
    
    logger.info(f"Completed cover letter generation for user: {user_profile.user_id}. Cover letter saved at: {output.cover_letter_file_path}")
    return output
