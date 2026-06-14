# Member 3 — Architecture Document
## Job Matching, Resume Optimization & Cover Letter Generation
### Agent 02 — AI-Based Career Assistant System

---

## 1. System Architecture Overview

Member 3's components sit at the **middle of the career pipeline**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     Career Orchestrator (Member 1)                      │
│                        Sequences all stages                             │
└───────┬────────────────────┬───────────────────────┬────────────────────┘
        │                    │                       │
        ▼                    ▼                       ▼
  ┌───────────┐    ┌─────────────────┐    ┌──────────────────┐
  │  Scraping  │    │  Verification   │    │   Profile Store   │
  │  Agent     │───▶│  Agent          │    │  (Redis + PG)     │
  │ (Member 2) │    │  (Member 2)     │    │  (Member 1)       │
  └───────────┘    └────────┬────────┘    └────────┬─────────┘
                            │                      │
                            ▼                      ▼
                ┌───────────────────────────────────────────┐
                │         MEMBER 3 BOUNDARY                  │
                │                                            │
                │  ┌─────────────────────────────────┐      │
                │  │    Job Matching Agent             │      │
                │  │    /agents/job_matching_agent.py   │      │
                │  │                                   │      │
                │  │  Input: UserProfile +              │      │
                │  │         VerifiedJobListings        │      │
                │  │  Output: List[MatchResult]         │      │
                │  └──────────────┬────────────────────┘      │
                │                 │                            │
                │          MatchResults                        │
                │           │           │                      │
                │           ▼           ▼                      │
                │  ┌────────────┐ ┌──────────────┐            │
                │  │ Resume     │ │ Cover Letter │            │
                │  │ Agent      │ │ Agent        │            │
                │  │            │ │              │            │
                │  │ Output:    │ │ Output:      │            │
                │  │ PDF + meta │ │ PDF + meta   │            │
                │  └──────┬─────┘ └──────┬───────┘            │
                │         │              │                     │
                └─────────┼──────────────┼─────────────────────┘
                          │              │
                          ▼              ▼
                ┌──────────────────────────────────┐
                │   Application Automation Agent    │
                │   (Member 4)                      │
                │   Receives: Resume + Cover Letter │
                └──────────────────────────────────┘
```

---

## 2. Component Architecture

### 2.1 Layer Architecture

Member 3's code follows a **4-layer architecture**:

```
┌──────────────────────────────────────────────────┐
│  Layer 1: AGENTS (Business Logic + LLM Calls)    │
│  ┌────────────────┐ ┌──────────┐ ┌────────────┐  │
│  │ JobMatchingAgent│ │ResumeAgent│ │CoverLetter │  │
│  │                │ │          │ │Agent       │  │
│  └───────┬────────┘ └────┬─────┘ └─────┬──────┘  │
│          │               │              │         │
├──────────┼───────────────┼──────────────┼─────────┤
│  Layer 2: TOOLS (Core Business Functions)         │
│  ┌────────────────────────────────────────────┐   │
│  │           document_tools.py                │   │
│  │  calculate_match_score()                   │   │
│  │  generate_resume()                         │   │
│  │  generate_cover_letter()                   │   │
│  │  extract_job_keywords()                    │   │
│  │  find_skill_matches()                      │   │
│  │  verify_factual_accuracy()                 │   │
│  │  check_ats_compatibility()                 │   │
│  │  render_pdf()                              │   │
│  └───────────────────┬────────────────────────┘   │
│                      │                            │
├──────────────────────┼────────────────────────────┤
│  Layer 3: MODELS (Data Structures)                │
│  ┌────────────────────────────────────────────┐   │
│  │         matching_models.py                 │   │
│  │  UserProfile, VerifiedJobListing,          │   │
│  │  MatchResult, SkillMatch,                  │   │
│  │  ResumeOutput, CoverLetterOutput,          │   │
│  │  KeywordReport, etc.                       │   │
│  └───────────────────┬────────────────────────┘   │
│                      │                            │
├──────────────────────┼────────────────────────────┤
│  Layer 4: CONFIG & DATA (Configuration)           │
│  ┌──────────────────┐ ┌─────────────────────┐     │
│  │matching_config.py│ │skill_taxonomy.json  │     │
│  │  Weights, rules, │ │  Synonyms, related  │     │
│  │  templates, env  │ │  skills mapping     │     │
│  └──────────────────┘ └─────────────────────┘     │
└───────────────────────────────────────────────────┘
```

### 2.2 Dependency Direction

Dependencies flow **downward only** — no circular dependencies:

```
Agents ──depends on──▶ Tools ──depends on──▶ Models ──depends on──▶ Config
```

- Agents import Tools and Models
- Tools import Models and Config
- Models import Config (for defaults only)
- Config has no internal dependencies

---

## 3. Agent Architecture (OpenAI Agents SDK)

Each agent is built using the `openai-agents` SDK (v0.0.3). Here's the internal architecture of each agent:

### 3.1 Agent Pattern

```python
from agents import Agent, Runner, function_tool

# 1. Define the tool
@function_tool
def calculate_match_score(user_profile: str, job_listing: str) -> str:
    """Calculate match score between user and job."""
    # Parse inputs, compute score, return JSON
    ...

# 2. Create the agent
job_matching_agent = Agent(
    name="Job Matching Agent",
    model="gpt-4o-mini",
    instructions="""You are a job matching specialist...""",
    tools=[calculate_match_score],
)

# 3. Run the agent
async def run_matching(user_profile, job_listings):
    result = await Runner.run(
        job_matching_agent,
        input=format_input(user_profile, job_listings)
    )
    return parse_output(result.final_output)
```

### 3.2 Agent Communication Pattern

Agents do **not** call each other directly. The Career Orchestrator (Member 1) sequences them:

```
Orchestrator
    │
    ├── 1. Call Job Matching Agent
    │       Input:  UserProfile + List[VerifiedJobListing]
    │       Output: List[MatchResult] (ranked)
    │
    ├── 2. For each top match, Call Resume Agent
    │       Input:  UserProfile + VerifiedJobListing + MatchResult
    │       Output: ResumeOutput (PDF path + metadata)
    │
    └── 3. For each top match, Call Cover Letter Agent
            Input:  UserProfile + VerifiedJobListing + MatchResult + ResumeOutput
            Output: CoverLetterOutput (PDF path + metadata)
```

### 3.3 Agent Tracing & Observability

```
Agent Call ──▶ OpenAI Agents SDK Tracing ──▶ Datadog APM (Member 5)
                    │
                    ├── Trace: agent_name, model, tokens_used
                    ├── Span: tool_call, duration, input_size
                    └── Error: exception_type, message, stack
```

---

## 4. Data Flow Architecture

### 4.1 Complete Data Flow

```
                    ┌──────────────┐
                    │  User Upload │
                    │  (CV / PDF)  │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  pypdf /     │
                    │  pdfplumber  │
                    │  Extract     │
                    └──────┬───────┘
                           │
                    ┌──────▼───────────┐
                    │  UserProfile     │
                    │  (PostgreSQL +   │
                    │   Redis cache)   │
                    └──────┬───────────┘
                           │
              ┌────────────┼─────────────────┐
              │            │                 │
              ▼            ▼                 ▼
    ┌─────────────┐ ┌──────────────┐  ┌──────────────┐
    │ Verified    │ │ Skill        │  │ Match Weight │
    │ Job Listings│ │ Taxonomy     │  │ Config       │
    │ (Member 2)  │ │ (JSON)       │  │              │
    └──────┬──────┘ └──────┬───────┘  └──────┬───────┘
           │               │                 │
           └───────────────┼─────────────────┘
                           │
                    ┌──────▼───────────┐
                    │  Job Matching    │
                    │  Agent           │
                    │                  │
                    │  calculate_      │
                    │  match_score()   │
                    └──────┬───────────┘
                           │
                    List[MatchResult]
                           │
              ┌────────────┼─────────────────┐
              │                              │
       ┌──────▼───────────┐          ┌───────▼──────────┐
       │  Resume Agent    │          │  Cover Letter    │
       │                  │          │  Agent           │
       │  generate_       │          │                  │
       │  resume()        │          │  generate_       │
       │                  │          │  cover_letter()  │
       │  ┌────────────┐  │          │                  │
       │  │ Factual    │  │          │  ┌────────────┐  │
       │  │ Accuracy   │  │    ┌─────│  │ Keyword    │  │
       │  │ Verifier   │  │    │     │  │ Matcher    │  │
       │  └────────────┘  │    │     │  └────────────┘  │
       │  ┌────────────┐  │    │     └──────┬───────────┘
       │  │ ATS        │  │    │            │
       │  │ Checker    │  │    │     CoverLetterOutput
       │  └────────────┘  │    │      (PDF + metadata)
       └──────┬───────────┘    │
              │                │
       ResumeOutput            │
       (PDF + metadata)        │
              │                │
              └────────┬───────┘
                       │
                ┌──────▼───────────┐
                │  MongoDB         │
                │  (Document Store)│
                │  Store generated │
                │  documents +     │
                │  version history │
                └──────┬───────────┘
                       │
                ┌──────▼───────────┐
                │  Member 4        │
                │  Application     │
                │  Automation      │
                └──────────────────┘
```

### 4.2 Database Usage

| Database | Purpose | Data Stored |
|---|---|---|
| **PostgreSQL** | Structured data | Match results, document metadata, user-job associations |
| **Redis** | Session/cache | Active user profile context, recent match results cache |
| **MongoDB** | Document store | Generated PDF/DOCX files, document version history, keyword reports |

### 4.3 Database Schema (PostgreSQL)

```sql
-- Match Results Table
CREATE TABLE match_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    job_id          VARCHAR(255) NOT NULL,
    overall_score   DECIMAL(5,2) NOT NULL,
    skill_score     DECIMAL(5,2),
    experience_score DECIMAL(5,2),
    location_score  DECIMAL(5,2),
    education_score DECIMAL(5,2),
    preference_score DECIMAL(5,2),
    matched_skills  JSONB,
    missing_skills  JSONB,
    recommendation_rank INTEGER,
    recommendation_reason TEXT,
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, job_id)
);

-- Generated Documents Table
CREATE TABLE generated_documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    job_id          VARCHAR(255) NOT NULL,
    document_type   VARCHAR(50) NOT NULL,  -- 'resume' | 'cover_letter'
    file_path       VARCHAR(500) NOT NULL,
    mongo_doc_id    VARCHAR(255),          -- Reference to MongoDB document
    ats_score       DECIMAL(5,2),
    keyword_match_pct DECIMAL(5,2),
    factual_verified BOOLEAN DEFAULT FALSE,
    version         INTEGER DEFAULT 1,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_match_user_score ON match_results(user_id, overall_score DESC);
CREATE INDEX idx_docs_user_job ON generated_documents(user_id, job_id);
```

---

## 5. Error Handling Architecture

### 5.1 Error Hierarchy

```
BaseAgentError
├── InputValidationError        # Invalid user profile or job listing
├── MatchingError               # Errors during match calculation
│   ├── EmptyProfileError       # Profile has no skills/experience
│   └── NoJobsAvailableError    # No verified jobs to match against
├── DocumentGenerationError     # Errors during resume/cover letter gen
│   ├── FactualAccuracyError    # Generated content has invented info
│   ├── ATSCompatibilityError   # Document fails ATS checks
│   ├── PDFRenderError          # PDF generation failed
│   └── KeywordThresholdError   # Keyword inclusion below threshold
├── ExternalServiceError        # External API/DB failures
│   ├── OpenAIAPIError          # OpenAI API call failed
│   ├── DatabaseError           # PostgreSQL/Redis/MongoDB error
│   └── RateLimitError          # API rate limit hit
└── ConfigurationError          # Missing env vars, bad config
```

### 5.2 Retry Strategy

```python
RETRY_CONFIG = {
    "max_retries": 3,
    "base_delay_seconds": 2,
    "max_delay_seconds": 30,
    "backoff_factor": 2,           # Exponential: 2s, 4s, 8s
    "retryable_errors": [
        OpenAIAPIError,
        DatabaseError,
        RateLimitError,
    ],
    "non_retryable_errors": [
        InputValidationError,
        FactualAccuracyError,       # Must regenerate, not retry
        ConfigurationError,
    ],
}
```

### 5.3 Error Response Format

All errors return structured JSON conforming to the Tool Interface Spec:

```json
{
    "success": false,
    "error": {
        "code": "FACTUAL_ACCURACY_VIOLATION",
        "message": "Generated resume contains skills not present in user profile",
        "details": {
            "invented_skills": ["Kubernetes", "Go"],
            "agent": "resume_agent",
            "user_id": "uuid-here"
        },
        "retryable": false,
        "timestamp": "2026-06-14T10:00:00Z"
    }
}
```

---

## 6. Security Architecture

### 6.1 Data Flow Security

```
┌─────────┐    TLS 1.3     ┌──────────┐    TLS 1.3     ┌──────────┐
│  Client  │◄──────────────▶│  FastAPI  │◄──────────────▶│  OpenAI  │
│          │                │  Gateway  │                │  API     │
└─────────┘                └─────┬─────┘                └──────────┘
                                 │
                          TLS 1.3│
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
              ┌─────▼────┐ ┌────▼─────┐ ┌────▼─────┐
              │PostgreSQL│ │  Redis   │ │ MongoDB  │
              │AES-256   │ │AES-256   │ │AES-256   │
              │at rest   │ │at rest   │ │at rest   │
              └──────────┘ └──────────┘ └──────────┘
```

### 6.2 Credential Management

```python
# All credentials loaded from environment — NEVER hardcoded
import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]       # Required
DATABASE_URL = os.environ["DATABASE_URL"]             # Required
REDIS_URL = os.environ["REDIS_URL"]                   # Required
MONGODB_URI = os.environ["MONGODB_URI"]               # Required
```

---

## 7. Logging & Observability Architecture

### 7.1 Logging Strategy

```python
from loguru import logger

# Configure structured logging
logger.add(
    "logs/member3_{time}.log",
    rotation="10 MB",
    retention="30 days",
    format="{time} | {level} | {module}:{function}:{line} | {message}",
    level=os.getenv("LOG_LEVEL", "INFO"),
)

# Log levels by category
# DEBUG:   Detailed computation steps, score breakdowns
# INFO:    Agent invocations, document generations, match completions
# WARNING: Retry attempts, fallback activations, low scores
# ERROR:   API failures, generation failures, factual violations
# CRITICAL: Data corruption, security violations
```

### 7.2 Metrics to Track

| Metric | Type | Purpose |
|---|---|---|
| `match_score_distribution` | Histogram | Distribution of match scores |
| `match_agent_latency_ms` | Timer | Time to complete matching |
| `resume_generation_latency_ms` | Timer | Time to generate resume |
| `cover_letter_generation_latency_ms` | Timer | Time to generate cover letter |
| `factual_accuracy_violations` | Counter | Number of factual accuracy failures |
| `ats_compatibility_score` | Gauge | Average ATS score of generated resumes |
| `keyword_match_percentage` | Gauge | Average keyword inclusion % |
| `openai_tokens_used` | Counter | Token consumption per agent |
| `retry_count` | Counter | Number of retries per error type |

---

## 8. Technology Stack Summary

| Category | Technology | Version | Purpose |
|---|---|---|---|
| Agent Framework | openai-agents | 0.0.3 | Agent orchestration, tool registration |
| LLM | OpenAI gpt-4o-mini | latest | Text generation, reasoning |
| Web Framework | FastAPI | 0.111.0 | API endpoints (if needed for testing) |
| Validation | Pydantic | 2.7.4 | Data model validation |
| Database ORM | SQLAlchemy | 2.0.31 | PostgreSQL access |
| DB Driver | psycopg2-binary | 2.9.9 | PostgreSQL connection |
| Migrations | Alembic | 1.13.2 | Schema migrations |
| Cache | Redis | 5.0.7 | Session/profile cache |
| Document Store | PyMongo | 4.8.0 | MongoDB access |
| PDF Reading | pypdf | 4.2.0 | Read existing CVs |
| PDF Extraction | pdfplumber | 0.11.1 | Extract text from PDFs |
| DOCX Generation | python-docx | 1.1.2 | Generate Word documents |
| HTTP Client | httpx | 0.27.0 | Async HTTP calls |
| Testing | pytest | 8.2.2 | Unit/integration testing |
| Test Async | pytest-asyncio | 0.23.7 | Async test support |
| Test Mocking | pytest-mock | 3.14.0 | Mock external services |
| Test Data | faker | 26.0.0 | Generate test fixtures |
| Environment | python-dotenv | 1.0.1 | Load .env files |
| Logging | loguru | 0.7.2 | Structured logging |
| Security | cryptography | 42.0.8 | AES-256 encryption |
