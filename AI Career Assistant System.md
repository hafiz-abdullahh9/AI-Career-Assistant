
AI-Based Career Assistant
Multi-Agent Orchestrator
Autonomous Job Discovery, Application & Career Development Pipeline
AI Career Assistant Multi-Agent System  |  Built on OpenAI Agents SDK
Architecture & Development Blueprint  —  2026

1. Executive Summary
The AI Career Assistant is a production-grade multi-agent system that automates the complete job search lifecycle — from job discovery and verification to resume customization, automated application, and interview preparation. Using the OpenAI Agents SDK, a Career Orchestrator coordinates eight specialist agents, each responsible for one stage of the pipeline. The system reduces manual job-search effort by over 90%, increases application throughput 10x, and improves match quality through AI-driven compatibility scoring.
2. Pain Point Analysis
Why this system is the highest-ROI starting point:
Metric	Without AI Agents	With This System
Time to apply per job	20–40 minutes (manual)	< 1 minute (automated)
Resume customization	Rarely done / generic CV	Tailored per job, ATS-optimized
Job search coverage	1–2 platforms, manual checking	Continuous multi-platform scraping
Application volume	5–10 / week (manual)	50–100 / week (automated)
Interview prep quality	Inconsistent, unguided	AI mock interviews + feedback
Career guidance	None / generic advice	Personalized skill-gap roadmap

3. System Architecture
3.1 Agent Topology
The system follows the Manager + Handoff hybrid pattern recommended by the OpenAI Agents SDK. The Career Orchestrator is the entry point. It sequences the pipeline — scraping, verification, matching, customization, application, tracking, skill-gap analysis, and interview prep — handing off full ownership to specialist agents for each stage while retaining session context across the full user journey.
3.2 Agents
Agent	Responsibility	Model	Role
Career Orchestrator	Entry point. Sequences the pipeline across all stages and maintains session/profile context.	GPT-4o	Orchestrator
Job Scraping Agent	Collects job/internship listings from LinkedIn and Indeed based on user search filters.	GPT-4o-mini	Specialist
Job Verification Agent	Filters duplicates, expired postings, and fake listings; verifies company legitimacy.	GPT-4o-mini	Specialist
Job Matching Agent	Calculates compatibility score between user profile and job requirements; ranks recommendations.	GPT-4o-mini	Specialist
Resume Optimization Agent	Customizes and ATS-optimizes resume per job, without inventing information.	GPT-4o-mini	Specialist
Cover Letter Agent	Generates personalized cover letters tailored to job and company.	GPT-4o-mini	Specialist
Application Automation Agent	Submits applications via email or web-form automation; captures confirmations.	GPT-4o-mini	Specialist
Skill Gap & Interview Agent	Analyzes skill gaps, builds learning roadmaps, and runs AI mock interviews with feedback.	GPT-4o	Specialist
Profile Integrity Monitor	Passive guardrail. Validates factual accuracy of generated documents and flags conflicting profile data.	GPT-4o-mini	Guardrail

3.3 Pipeline Flow Diagram (Text Representation)
User Profile / CV Upload
       |
       v
[Career Orchestrator]  <-- Profile Integrity Monitor (passive guardrail)
       |
       v
[Job Scraping Agent] --> [Job Verification Agent]
       |
       v
[Job Matching Agent] --> Ranked Recommendations
       |
  (user selects job)
       |
  +----+----+
  |         |
  v         v
[Resume   [Cover Letter
 Opt. Agent]  Agent]
  |         |
  +----+----+
       |
       v
[Application Automation Agent] --> Email / Web Form Submission
       |
       v
[Application Tracking] --> Status Monitoring
       |
       v
[Skill Gap & Interview Agent] --> Learning Roadmap + Mock Interview

4. Tool Integrations
Tool Name	Purpose	Integration
scrape_linkedin_jobs	Collect job listings with filters (keywords, location, type)	LinkedIn API
scrape_indeed_jobs	Collect job listings with filters	Indeed API
verify_company	Check company legitimacy against public records	Company Registry / Web Lookup
parse_cv	Extract skills, experience, education from uploaded CV	Document Processing API
calculate_match_score	Compute compatibility score between profile and job	Internal Matching Engine
generate_resume	Produce ATS-optimized resume reorganizing CV content	Document Generation Service
generate_cover_letter	Produce tailored cover letter	LLM Generation Service
send_application_email	Send application email with attachments	Gmail / SMTP API
submit_web_application	Fill and submit web application forms	Selenium / Browser Automation
update_application_status	Record/update status in tracking dashboard	Internal DB API
generate_learning_roadmap	Produce skill-gap report and learning path	Internal Skill Engine
run_mock_interview	Conduct AI mock interview and score responses	LLM + Speech/Text Processing

5. Guardrails
•Input Guardrail: CV/PII scrubber — strips sensitive identifiers (national ID numbers, bank details) before passing CV content to any agent.
•Input Guardrail: Profile completeness checker — flags incomplete profiles before job matching begins.
•Output Guardrail: Factual accuracy checker — Resume/Cover Letter Agents may never add skills, titles, or experience not present in the source CV.
•Output Guardrail: ATS formatting validator — rejects resume layouts with graphics, columns, or unsupported formatting.
•Tool Guardrail: Application rate limiter — Application Automation Agent may not submit more than a configurable daily cap per platform to avoid account flags.
•Tool Guardrail: Job verification gate — Job Matching Agent only ranks listings marked verified_status = true.

6. OpenAI Agents SDK Implementation
6.1 Core Agent Definitions
from agents import Agent, Runner, function_tool, handoff
from agents.guardrails import input_guardrail, output_guardrail

# ── Specialist Agents ──────────────────────────────────────────
job_verification_agent = Agent(
    name="JobVerificationAgent",
    instructions="""Filter job listings: (1) remove duplicates,
    (2) remove expired postings, (3) verify company legitimacy,
    (4) flag suspicious listings. Return verified_status per job.""",
    model="gpt-4o-mini",
    tools=[verify_company],
)

job_matching_agent = Agent(
    name="JobMatchingAgent",
    instructions="Calculate compatibility scores between user profile
    and verified jobs. Rank by weighted skills, experience, location,
    and goal alignment.",
    model="gpt-4o-mini",
    tools=[calculate_match_score],
)

resume_agent = Agent(
    name="ResumeOptimizationAgent",
    instructions="""Reorganize and highlight CV content to match job
    requirements. NEVER invent skills or experience. Ensure ATS
    compatibility.""",
    model="gpt-4o-mini",
    tools=[generate_resume],
)

# ── Career Orchestrator (entry point) ──────────────────────────
career_orchestrator = Agent(
    name="CareerOrchestrator",
    instructions="""Sequence the career pipeline: job collection,
    verification, matching, document customization, application,
    tracking, and skill development. Maintain user profile context
    across all handoffs.""",
    model="gpt-4o",
    handoffs=[job_verification_agent, job_matching_agent, resume_agent],
    tools=[parse_cv],
)

# ── Run ────────────────────────────────────────────────────────
async def run_career_pipeline(user_id: str, action: str):
    context = {"user_id": user_id}
    result = await Runner.run(career_orchestrator, input=action, context=context)
    return result.final_output

7. Data Flow & State Management
Each user session maintains a Profile Context object (OpenAI Agents SDK Sessions) that persists CV data, job-search filters, application history, and agent-chain results. This allows the Skill Gap & Interview Agent to access the full application history without re-fetching profile data.
•Session storage: Redis (TTL 24h for active sessions, persistent profile store in PostgreSQL)
•State keys: user_id, profile_data, job_queue, match_scores, application_status, agent_chain, timestamps
•Tracing: OpenAI Agents SDK built-in tracing enabled for full observability

8. Performance Targets & KPIs
KPI	Target	Notes
Job search & filtering	< 3 seconds	Per FR matching SRS Section 5.1
Resume generation	< 30 seconds	Per job, ATS-optimized
Cover letter generation	< 45 seconds	Per job
Application submission	< 2 minutes	Per application, email or web form
Job verification accuracy	> 95%	Duplicate/expired/fake filtering
CV parsing accuracy	> 90%	Skill/experience extraction
Job matching precision	> 85%	Top recommendations
Resume factual accuracy	100%	No invented information — hard constraint

9. Infrastructure & Deployment
•Runtime: Python 3.11+, FastAPI gateway, async event loop
•Frontend: React/Vue.js web portal with dashboard, CV upload, job browser, application tracker
•Orchestration: Kubernetes (1 pod per agent group, HPA on queue depth)
•LLM API: OpenAI (gpt-4o for orchestrator/skill-gap-interview, gpt-4o-mini for specialists)
•Databases: PostgreSQL (users, jobs, applications), MongoDB (CV/document store), Elasticsearch (job search index), Redis (session/cache)
•Browser Automation: Selenium/Puppeteer cluster for web-form applications
•Tracing & Monitoring: OpenAI Agents tracing + Datadog APM + PagerDuty alerts

10. Development Roadmap
Phase	Duration	Deliverables
Phase 1 — Foundation	2 weeks	Career Orchestrator, Job Scraping + Verification Agents, core DB schema, unit tests
Phase 2 — Matching & Profile	1 week	Job Matching Agent, CV parsing, User Profile Service
Phase 3 — Document Generation	1 week	Resume Optimization Agent, Cover Letter Agent, ATS validator
Phase 4 — Application Automation	1 week	Application Automation Agent, email + web-form submission, tracking dashboard
Phase 5 — Skill Gap & Interview Prep	1 week	Skill Gap Analysis Agent, Mock Interview Agent, learning roadmap engine
Phase 6 — Infra & Hardening	2 weeks	Kubernetes deployment, observability stack, load testing, SLA validation, rollout
