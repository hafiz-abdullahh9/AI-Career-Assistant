"""
Member 3 — Resume Optimization Agent
Uses the OpenAI Agents SDK to optimize resumes while maintaining 100% factual accuracy.
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
)
from tools.document_tools import generate_resume


# ---------------------------------------------------------------------------
# Tool Registration
# ---------------------------------------------------------------------------

@function_tool(name_override="generate_resume")
def generate_resume_tool(
    user_profile: UserProfile,
    job_listing: VerifiedJobListing,
    match_result: MatchResult,
    template: str = "ats_standard"
) -> ResumeOutput:
    """
    Generate an ATS-optimized resume tailored to the job description.
    All claims about the user MUST be 100% factually accurate.
    """
    return generate_resume(user_profile, job_listing, match_result, template)


# ---------------------------------------------------------------------------
# Agent Definition
# ---------------------------------------------------------------------------

AGENT_MODEL = os.getenv("AGENT_MODEL", "gpt-4o-mini")

resume_agent = Agent(
    name="Resume Optimization Agent",
    model=AGENT_MODEL,
    instructions=(
        "You are an expert Resume Optimization Agent in the AI Career Assistant System.\n"
        "Your task is to tailor a candidate's resume to match a target job listing.\n"
        "CRITICAL CONSTRAINT: You must maintain 100% factual accuracy. NEVER invent skills, "
        "experience, achievements, or credentials. Only optimize existing information.\n"
        "You have access to the generate_resume tool. Follow ATS compatibility rules: "
        "no images, no multi-column layouts, standard fonts, and simple bullet points."
    ),
    tools=[generate_resume_tool],
)


# ---------------------------------------------------------------------------
# Programmatic API
# ---------------------------------------------------------------------------

async def optimize_resume(
    user_profile: UserProfile,
    job_listing: VerifiedJobListing,
    match_result: MatchResult,
    template: str = "ats_standard"
) -> ResumeOutput:
    """
    Programmatic entry point to run the resume optimization pipeline.
    """
    logger.info(f"Starting resume optimization for user: {user_profile.user_id} and job: {job_listing.job_id}")
    
    # Run agent runner or call generate_resume directly
    # To bypass LLM cost/latency when running programmatically, we call generate_resume directly.
    # If LLM tailoring is requested, the tool handles it.
    output = generate_resume(user_profile, job_listing, match_result, template)
    
    logger.info(f"Completed resume optimization for user: {user_profile.user_id}. Resume saved at: {output.resume_file_path}")
    return output
