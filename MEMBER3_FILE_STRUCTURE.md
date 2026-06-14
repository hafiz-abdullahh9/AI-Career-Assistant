# Member 3 — File Structure
## Job Matching, Resume Optimization & Cover Letter Generation
### Agent 02 — AI-Based Career Assistant System

---

## Complete Directory Tree

```
project-root/
│
├── .env                                    # Environment variables (NEVER committed)
├── .env.example                            # Template with placeholder values (committed)
├── .gitignore                              # Ignore .env, __pycache__, outputs/, logs/
├── requirements.txt                        # Python dependencies
├── README.md                               # Project documentation
│
├── agents/                                 # All AI agents
│   ├── __init__.py
│   ├── career_orchestrator.py              # [Member 1] Pipeline orchestrator
│   ├── job_scraping_agent.py               # [Member 2] Web scraping agent
│   ├── job_verification_agent.py           # [Member 2] Listing verification agent
│   │
│   ├── job_matching_agent.py               # [MEMBER 3] ★ Job matching agent
│   ├── resume_agent.py                     # [MEMBER 3] ★ Resume optimization agent
│   ├── cover_letter_agent.py               # [MEMBER 3] ★ Cover letter generation agent
│   │
│   ├── application_agent.py                # [Member 4] Application automation
│   ├── skill_gap_agent.py                  # [Member 5] Skill gap analysis
│   └── interview_agent.py                  # [Member 5] Interview preparation
│
├── tools/                                  # Tool functions called by agents
│   ├── __init__.py
│   ├── scraping_tools.py                   # [Member 2] LinkedIn/Indeed scrapers
│   ├── verification_tools.py               # [Member 2] Company verification
│   │
│   ├── document_tools.py                   # [MEMBER 3] ★ All document/matching tools
│   │
│   ├── email_tools.py                      # [Member 4] Email sending
│   └── web_form_tools.py                   # [Member 4] Web form automation
│
├── models/                                 # Pydantic data models
│   ├── __init__.py
│   ├── base_models.py                      # [Member 1] Shared base models
│   │
│   ├── matching_models.py                  # [MEMBER 3] ★ All M3 data models
│   │                                       #   - MatchResult
│   │                                       #   - SkillMatch
│   │                                       #   - MatchWeightConfig
│   │                                       #   - ResumeOutput
│   │                                       #   - KeywordReport
│   │                                       #   - CoverLetterOutput
│   │                                       #   - CompanyInfo
│   │                                       #   - FactualAccuracyResult
│   │                                       #   - ATSCompatibilityResult
│   │
│   └── job_models.py                       # [Member 2] Job listing models
│
├── config/                                 # Configuration modules
│   ├── __init__.py
│   │
│   ├── matching_config.py                  # [MEMBER 3] ★ Matching & document config
│   │                                       #   - Match weight defaults
│   │                                       #   - ATS formatting rules
│   │                                       #   - Resume templates
│   │                                       #   - Cover letter tone presets
│   │                                       #   - Environment variable loading
│   │
│   └── settings.py                         # [Member 1] Global settings
│
├── data/                                   # Static data files
│   ├── skill_taxonomy.json                 # [MEMBER 3] ★ Skill synonyms & relations
│   │                                       #   200+ skills with synonyms, related,
│   │                                       #   and category mappings
│   │
│   └── resume_templates/                   # [MEMBER 3] ★ DOCX resume templates
│       ├── ats_standard.docx               #   Standard ATS-friendly template
│       ├── ats_modern.docx                 #   Modern but ATS-compatible template
│       └── ats_minimal.docx                #   Minimal clean template
│
├── services/                               # Business services
│   ├── __init__.py
│   └── tracking_service.py                 # [Member 4] Application tracking
│
├── infra/                                  # Infrastructure
│   ├── __init__.py
│   ├── profile_context.py                  # [Member 1] Redis + PG profile schema
│   ├── database.py                         # [Member 1] Database connections
│   ├── datadog_setup.py                    # [Member 5] APM instrumentation
│   └── k8s/                                # [Member 5] Kubernetes manifests
│       ├── deployment.yaml
│       ├── hpa.yaml
│       ├── service.yaml
│       ├── configmap.yaml
│       └── secret.yaml
│
├── tests/                                  # All test files
│   ├── __init__.py
│   ├── conftest.py                         # Shared test fixtures & config
│   │
│   ├── test_matching_documents.py          # [MEMBER 3] ★ Main test file
│   │                                       #   - Test Job Matching Agent (≥10 cases)
│   │                                       #   - Test Resume Agent (≥10 cases)
│   │                                       #   - Test Cover Letter Agent (≥10 cases)
│   │                                       #   - Test document_tools functions
│   │
│   ├── test_matching_models.py             # [MEMBER 3] ★ Model validation tests
│   │
│   ├── fixtures/                           # [MEMBER 3] ★ Test fixture data
│   │   ├── __init__.py
│   │   ├── sample_profiles.py              #   Mock user profiles for testing
│   │   ├── sample_job_listings.py          #   Mock verified job listings
│   │   ├── sample_resumes/                 #   Sample CV PDFs for testing
│   │   │   ├── software_engineer_cv.pdf
│   │   │   ├── data_scientist_cv.pdf
│   │   │   └── business_analyst_cv.pdf
│   │   └── expected_outputs/               #   Expected output fixtures
│   │       ├── expected_match_results.json
│   │       ├── expected_resume_keywords.json
│   │       └── expected_cover_letter.json
│   │
│   ├── integration/                        # [Member 1] Integration tests
│   │   ├── __init__.py
│   │   └── test_pipeline_m3.py             # [MEMBER 3] ★ Pipeline integration test
│   │
│   ├── test_orchestrator.py                # [Member 1]
│   ├── test_scraping_verification.py       # [Member 2]
│   └── test_application_tracking.py        # [Member 4]
│
├── outputs/                                # Generated document outputs
│   ├── resumes/                            # [MEMBER 3] ★ Generated resume PDFs
│   │   └── .gitkeep
│   └── cover_letters/                      # [MEMBER 3] ★ Generated cover letters
│       └── .gitkeep
│
├── logs/                                   # Application logs
│   └── .gitkeep
│
├── docs/                                   # Documentation
│   ├── tool_interface_spec.md              # [Member 1] Tool interface specification
│   └── member3_readme.md                   # [MEMBER 3] ★ Component documentation
│
└── migrations/                             # [Member 1] Alembic DB migrations
    ├── env.py
    ├── alembic.ini
    └── versions/
        └── .gitkeep
```

---

## Member 3 Files — Summary Table

| # | File Path | Purpose | Lines Est. |
|---|---|---|---|
| 1 | `/agents/job_matching_agent.py` | Job matching agent with OpenAI Agents SDK | 150–200 |
| 2 | `/agents/resume_agent.py` | Resume optimization agent | 200–250 |
| 3 | `/agents/cover_letter_agent.py` | Cover letter generation agent | 180–220 |
| 4 | `/tools/document_tools.py` | All tool functions (match, resume, cover letter) | 400–500 |
| 5 | `/models/matching_models.py` | All Pydantic data models | 200–250 |
| 6 | `/config/matching_config.py` | Configuration, weights, templates, env vars | 100–130 |
| 7 | `/data/skill_taxonomy.json` | Skill synonym & relation database | 500+ |
| 8 | `/data/resume_templates/ats_standard.docx` | Standard ATS resume template | N/A |
| 9 | `/data/resume_templates/ats_modern.docx` | Modern ATS resume template | N/A |
| 10 | `/data/resume_templates/ats_minimal.docx` | Minimal ATS resume template | N/A |
| 11 | `/tests/test_matching_documents.py` | Main test suite (≥30 test cases) | 500–700 |
| 12 | `/tests/test_matching_models.py` | Model validation tests | 100–150 |
| 13 | `/tests/fixtures/sample_profiles.py` | Mock user profiles | 100–150 |
| 14 | `/tests/fixtures/sample_job_listings.py` | Mock verified job listings | 100–150 |
| 15 | `/tests/integration/test_pipeline_m3.py` | End-to-end pipeline test | 100–150 |
| 16 | `/docs/member3_readme.md` | Component documentation | 50–80 |
| | **Total estimated** | | **~2,700–3,200** |

---

## File Creation Order (Dependency-Driven)

Files should be created in this order to minimize import errors:

```
Step 1: Foundation (no dependencies)
    ├── /config/matching_config.py
    ├── /data/skill_taxonomy.json
    └── /data/resume_templates/*.docx

Step 2: Data Models (depends on config)
    └── /models/matching_models.py

Step 3: Test Fixtures (depends on models)
    ├── /tests/fixtures/sample_profiles.py
    └── /tests/fixtures/sample_job_listings.py

Step 4: Tools (depends on models + config)
    └── /tools/document_tools.py

Step 5: Agents (depends on tools + models)
    ├── /agents/job_matching_agent.py
    ├── /agents/resume_agent.py
    └── /agents/cover_letter_agent.py

Step 6: Tests (depends on everything)
    ├── /tests/test_matching_models.py
    ├── /tests/test_matching_documents.py
    └── /tests/integration/test_pipeline_m3.py

Step 7: Documentation
    └── /docs/member3_readme.md
```

---

## .gitignore Additions (Member 3 specific)

```gitignore
# Generated outputs
outputs/resumes/*.pdf
outputs/cover_letters/*.pdf
outputs/cover_letters/*.docx

# Logs
logs/*.log

# Environment
.env

# Python
__pycache__/
*.pyc
.pytest_cache/

# IDE
.vscode/
.idea/
```

---

## .env.example

```bash
# OpenAI
OPENAI_API_KEY=sk-your-key-here

# PostgreSQL
DATABASE_URL=postgresql://user:password@localhost:5432/career_assistant

# Redis
REDIS_URL=redis://localhost:6379/0

# MongoDB
MONGODB_URI=mongodb://localhost:27017/career_assistant

# Application
DOCUMENT_OUTPUT_DIR=./outputs
LOG_LEVEL=INFO
MAX_RECOMMENDATIONS=10
```
