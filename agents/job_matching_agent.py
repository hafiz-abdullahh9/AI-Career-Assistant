"""
Member 3 — Job Matching Agent
Uses the OpenAI Agents SDK to set up the matching agent and provides
programmatic batch matching functions.
"""

import os
import sys
from datetime import datetime
from typing import List, Optional
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
    MatchWeightConfig,
    MatchingBatchResponse,
    AgentErrorResponse,
)
from tools.document_tools import calculate_match_score


# ---------------------------------------------------------------------------
# Tool Registration
# ---------------------------------------------------------------------------

@function_tool(name_override="calculate_match_score")
def calculate_match_score_tool(
    user_profile: UserProfile,
    job_listing: VerifiedJobListing,
    weight_config: Optional[MatchWeightConfig] = None
) -> MatchResult:
    """
    Calculate the match score between a user profile and a job listing.
    """
    return calculate_match_score(user_profile, job_listing, weight_config)


# ---------------------------------------------------------------------------
# Agent Definition
# ---------------------------------------------------------------------------

# Get model from environment or config
AGENT_MODEL = os.getenv("AGENT_MODEL", "gpt-4o-mini")

job_matching_agent = Agent(
    name="Job Matching Agent",
    model=AGENT_MODEL,
    instructions=(
        "You are an expert Job Matching Agent in the AI Career Assistant System.\n"
        "Your task is to analyze candidate profiles and match them with verified job listings.\n"
        "You have access to the calculate_match_score tool to compute compatibility scores.\n"
        "Always provide detailed match breakdowns, rank matching listings, and explain why a candidate fits a role."
    ),
    tools=[calculate_match_score_tool],
)


# ---------------------------------------------------------------------------
# Batch Matching API
# ---------------------------------------------------------------------------

async def match_jobs(
    user_profile: UserProfile,
    job_listings: List[VerifiedJobListing],
    weight_config: Optional[MatchWeightConfig] = None,
    top_n: int = 10
) -> MatchingBatchResponse:
    """
    Match a user profile against a list of verified job listings, rank them,
    and return the top N recommendations.
    """
    logger.info(f"Starting job matching for user: {user_profile.user_id} against {len(job_listings)} listings.")
    
    # 1. Input Validation
    if not user_profile.skills and not user_profile.experience:
        logger.error(f"Empty user profile for user: {user_profile.user_id}")
        raise ValueError("User profile must contain at least some skills or experience.")
        
    # 2. Filter only verified listings (status == "verified")
    verified_listings = [job for job in job_listings if job.verified_status == "verified"]
    total_verified = len(verified_listings)
    
    if total_verified == 0:
        logger.warning("No verified job listings provided for matching.")
        return MatchingBatchResponse(
            user_id=user_profile.user_id,
            total_jobs_evaluated=len(job_listings),
            total_verified_jobs=0,
            results=[],
            created_at=datetime.utcnow()
        )
        
    results: List[MatchResult] = []
    for job in verified_listings:
        try:
            match_res = calculate_match_score(user_profile, job, weight_config)
            results.append(match_res)
        except Exception as e:
            logger.error(f"Error matching job {job.job_id}: {e}")
            continue
            
    # 3. Rank results by score descending
    results.sort(key=lambda x: x.overall_score, reverse=True)
    
    # 4. Assign ranks
    for idx, res in enumerate(results):
        res.recommendation_rank = idx + 1
        
    # 5. Top-N filtering
    results = results[:top_n]
    
    logger.info(f"Completed job matching for user: {user_profile.user_id}. Top {len(results)} matches returned.")
    
    return MatchingBatchResponse(
        user_id=user_profile.user_id,
        total_jobs_evaluated=len(job_listings),
        total_verified_jobs=total_verified,
        results=results,
        created_at=datetime.utcnow()
    )
