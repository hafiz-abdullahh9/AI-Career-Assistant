# AGENT 02 — AI-Based Career Assistant System

Welcome to the AI-Based Career Assistant System repository foundation. This project is built to automate the complete career progression lifecycle — covering job discovery, company legitimacy checks, candidate matching, resume optimization, web application automation, application tracking, and AI-led mock interviews.

This repository establishes the foundational multi-agent orchestration scaffolding using the **OpenAI Agents SDK** architecture.

---

## 1. System Architecture Overview

The system runs on a **Manager + Handoff hybrid layout**. The `CareerOrchestrator` manages context state variables (`ProfileContext`) and coordinates specialist agents via distinct pipeline stages.

```
                  ┌──────────────────────┐
                  │  CareerOrchestrator  │
                  └──────────┬───────────┘
                             │
       ┌─────────────────────┼─────────────────────┐
       ▼                     ▼                     ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│  Discovery   │      │ Document Opt │      │   Interview  │
│    Agent     │      │    Agent     │      │  Prep Agent  │
└──────────────┘      └──────────────┘      └──────────────┘
```

### Key Infrastructure Split:
* **Transient Session State (Redis)**: Holds active sessions, job recommendations queue, and orchestrator state variables. TTL is restricted to 24 hours.
* **Persistent Authority Store (PostgreSQL)**: Holds user profile data, persistent applications tracking history, audit logging metrics, and encrypted credential tokens.

---

## 2. Orchestration State Machine Lifecycle

The pipeline operates on the following state workflow transitions:

1. **`IDLE`**: Awaiting user CV upload.
2. **`STATE_PARSING`**: Processing raw document contents and running the PII scrubbing guardrail.
3. **`STATE_DISCOVERY`**: LinkedIn & Indeed scrapers collecting relevant opportunities.
4. **`STATE_VERIFICATION`**: Checking legitimacy of companies (rejects fraudulent postings).
5. **`STATE_MATCHING`**: Ranks verified listings against candidate profile using weighted metrics.
6. **`STATE_SELECTION_WAIT`**: Halts and presents ranked positions to user for manual selection.
7. **`STATE_CUSTOMIZATION`**: Tailors PDF Resumes & Cover Letters for the selected job.
8. **`STATE_GUARDRAIL_CHECK`**: Passive `ProfileIntegrityMonitor` checks that customized credentials are factually accurate to the source profile.
9. **`STATE_APPLICATION`**: Email or Selenium browser automated form submission executes.
10. **`STATE_TRACKING`**: Background monitoring of inbox updates for application status updates.
11. **`STATE_PREPARATION`**: Triggers mock interview engine and custom learning paths.
12. **`STATE_COMPLETED`**: Final workflow state.

---

## 3. Repository Directory Structure

```
├── agents/
│   ├── career_orchestrator.py      # M1: Entry coordinator and state routing machine
│   ├── job_scraping_agent.py       # M2: Crawls LinkedIn and Indeed listings
│   ├── job_verification_agent.py   # M2: Standardizes listings and verifies companies
│   ├── job_matching_agent.py       # M3: Scores profiles against job parameters
│   ├── resume_agent.py             # M3: Tailors resume structure (ATS compatible)
│   ├── cover_letter_agent.py       # M3: Customizes cover letters
│   ├── application_agent.py        # M4: Submits via Selenium/Email automation
│   ├── skill_gap_agent.py          # M5: Renders course suggestions
│   └── interview_agent.py          # M5: Performs interactive mock interview sessions
├── core/
│   ├── config.py                   # Pydantic global configuration parser
│   ├── database.py                 # Redis and PostgreSQL pooling hooks
│   ├── exceptions.py               # Standardized exception classes
│   └── retry.py                    # Reusable exponential backoff decorator
├── docs/
│   └── tool_interface_spec.md      # Strictly enforced input/output contract formats
├── guardrails/
│   ├── integrity_monitor.py        # Passive guardrail verifying factual CV truth
│   └── pii_scrubber.py             # Sanitizes PII variables from CV payload
├── infra/
│   ├── profile_context.py          # ProfileContext schemas and db syncing managers
│   └── security/
│       ├── encryption.py           # Authenticated AES-256-GCM token cipher
│       └── token_manager.py        # Safe credentials retrieval and storage
├── services/
│   └── tracking_service.py         # M4: Email scraping tracking utility
└── tests/
    ├── test_orchestrator.py        # State logic unit test cases
    └── integration/
        └── test_integration.py     # End-to-end integration contracts mock verification
```

---

## 4. Developer Setup & Onboarding Guide

### Prerequisites
* Python 3.11+
* PostgreSQL Database
* Redis Cache Server

### 1. Environment Variable Setup
Create a local `.env` file at the root of the workspace matching these options:
```bash
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/career_assistant"
REDIS_URL="redis://localhost:6379/0"
OPENAI_API_KEY="sk-proj-xxxxxxxxxxxxxxxxxxxxxxxx"
ENCRYPTION_KEY="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODkwYWJjZGU="  # Must be 32-byte Base64 string
LOG_LEVEL="INFO"
```

### 2. Dependency Installation
Install required packages using pip:
```bash
pip install -r requirements.txt
```

---

## 5. Branch & Collaboration Guidelines

To maintain clean codebase transitions:
1. **Branch Assignment**: Always work on your assigned feature branch:
   * Member 2: `feature/job-scraping-verification`
   * Member 3: `feature/matching-documents`
   * Member 4: `feature/application-automation`
   * Member 5: `feature/skillgap-interview-infra`
2. **Commit Standard**: Use conventional commits (e.g., `feat: implement indeed scraper`, `fix: correct regex`).
3. **Merge Pull Requests**: All PRs must target the `develop` branch and require review approval from the Project Lead (Member 1) before merge operations.

---

## 6. Verification & Test Commands

Run the unit test suite to verify that your orchestrator state machines are compliant:
```bash
python -m pytest "tests/test_orchestrator.py"
```

To execute integration contract tests:
```bash
python -m pytest "tests/integration/test_integration.py"
```
