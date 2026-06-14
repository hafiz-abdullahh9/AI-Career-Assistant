# Member 3 — Implementation Plan
## Job Matching, Resume Optimization & Cover Letter Generation
### Agent 02 — AI-Based Career Assistant System

---

## 1. Executive Summary

Member 3 owns **three core agents** and **one shared tool module** in the AI Career Assistant pipeline:

| Agent | File | Phase | Due |
|---|---|---|---|
| Job Matching Agent | `/agents/job_matching_agent.py` | Phase 2 | Week 3 |
| Resume Optimization Agent | `/agents/resume_agent.py` | Phase 3 | Week 4 |
| Cover Letter Agent | `/agents/cover_letter_agent.py` | Phase 3 | Week 4 |
| Document Generation Tools | `/tools/document_tools.py` | Phase 3 | Week 4 |

**Branch**: `feature/matching-documents`

These agents sit at the **center** of the career pipeline: they consume verified job listings from Member 2 and produce customized application documents that Member 4 depends on for application automation.

---

## 2. Upstream Dependencies (What Member 3 Receives)

### 2.1 From Member 1 (Project Lead)
| Artifact | Expected By | Description |
|---|---|---|
| Repo skeleton | Week 1, Day 1 | Full folder structure, base files, branch protection |
| Tool Interface Spec | Week 1, Day 3 | `/docs/tool_interface_spec.md` — function signatures, I/O types, error formats for ALL tools |
| Profile Context schema | Week 2 | `/infra/profile_context.py` — Redis + PostgreSQL schema for user profiles |
| Career Orchestrator | Week 2 | `/agents/career_orchestrator.py` — sequences pipeline stages |

### 2.2 From Member 2 (Job Scraping & Verification)
| Artifact | Expected By | Description |
|---|---|---|
| Verified job listings | Week 2 | Structured JSON with `verified_status` per job |
| Job data fields | Week 2 | `job_id`, `company_name`, `job_title`, `description`, `required_skills`, `location`, `salary`, `deadline`, `contact_info`, `verified_status` |

### 2.3 Blocking Impact
| Who is Blocked | What They Need | Format |
|---|---|---|
| Member 4 (Application Automation) | Customized resume (PDF) + cover letter (PDF/DOCX) | File paths + metadata JSON |

---

## 3. Data Models & Schemas

### 3.1 Input Models (Consumed)

#### UserProfile (from Profile Context — Member 1)
```python
class UserProfile(BaseModel):
    user_id: str
    full_name: str
    email: str
    phone: Optional[str]
    location: str
    summary: Optional[str]
    skills: List[str]                     # ["Python", "Machine Learning", "SQL"]
    experience: List[ExperienceEntry]
    education: List[EducationEntry]
    certifications: List[str]
    languages: List[str]
    goals: Optional[str]                  # Career objective / target role
    preferred_locations: List[str]
    preferred_job_types: List[str]        # ["full-time", "remote", "internship"]
    resume_raw_text: Optional[str]        # Original CV text extracted by pypdf/pdfplumber
    resume_file_path: Optional[str]       # Path to uploaded CV file
```

#### ExperienceEntry
```python
class ExperienceEntry(BaseModel):
    title: str
    company: str
    location: Optional[str]
    start_date: str                       # ISO format
    end_date: Optional[str]              # None if current
    description: str
    skills_used: List[str]
```

#### EducationEntry
```python
class EducationEntry(BaseModel):
    degree: str
    institution: str
    field_of_study: str
    start_date: str
    end_date: Optional[str]
    gpa: Optional[float]
```

#### VerifiedJobListing (from Member 2)
```python
class VerifiedJobListing(BaseModel):
    job_id: str
    company_name: str
    job_title: str
    description: str
    required_skills: List[str]
    preferred_skills: Optional[List[str]]
    location: str
    salary: Optional[str]
    job_type: Optional[str]              # full-time, part-time, contract, internship
    experience_level: Optional[str]      # entry, mid, senior
    application_deadline: Optional[str]
    contact_info: Optional[str]
    application_url: Optional[str]
    posted_date: str
    verified_status: str                  # "verified" | "rejected" | "flagged_for_review"
    source_platform: str                  # "linkedin" | "indeed"
```

### 3.2 Output Models (Produced by Member 3)

#### MatchResult
```python
class MatchResult(BaseModel):
    user_id: str
    job_id: str
    overall_score: float                  # 0.0 — 100.0
    skill_match_score: float
    experience_match_score: float
    location_match_score: float
    education_match_score: float
    preference_match_score: float
    matched_skills: List[str]
    missing_skills: List[str]
    partial_matches: List[SkillMatch]     # Similar/related skill matches
    recommendation_rank: int
    recommendation_reason: str
    created_at: datetime
```

#### SkillMatch
```python
class SkillMatch(BaseModel):
    user_skill: str
    job_skill: str
    match_type: str                       # "exact" | "similar" | "related"
    confidence: float                     # 0.0 — 1.0
```

#### ResumeOutput
```python
class ResumeOutput(BaseModel):
    user_id: str
    job_id: str
    resume_file_path: str                 # Path to generated PDF
    ats_compatibility_score: float        # 0.0 — 100.0
    keyword_incorporation_report: KeywordReport
    sections_modified: List[str]
    factual_accuracy_verified: bool       # MUST always be True
    created_at: datetime
```

#### KeywordReport
```python
class KeywordReport(BaseModel):
    total_job_keywords: int
    incorporated_keywords: int
    incorporation_percentage: float
    keywords_added: List[str]
    keywords_not_applicable: List[str]    # Keywords not in user's actual profile
```

#### CoverLetterOutput
```python
class CoverLetterOutput(BaseModel):
    user_id: str
    job_id: str
    cover_letter_file_path: str           # Path to generated PDF/DOCX
    tone: str                             # "professional" | "creative" | industry-specific
    keyword_match_percentage: float
    personalization_score: float          # How tailored vs generic
    company_info_used: bool               # Whether company research was available
    created_at: datetime
```

---

## 4. Agent Design — Detailed Specifications

### 4.1 Job Matching Agent (`/agents/job_matching_agent.py`)

**Model**: `gpt-4o-mini` (DO NOT upgrade without Lead approval)

**Purpose**: Compare user profile against all verified job listings and produce ranked recommendations with detailed compatibility scores.

#### Matching Algorithm — Weighted Scoring

| Factor | Weight | Method |
|---|---|---|
| Skill match | 40% | Exact match, synonym expansion, semantic similarity |
| Experience relevance | 25% | Years + role title similarity + industry alignment |
| Location compatibility | 15% | Exact match, remote eligibility, commute radius |
| Education fit | 10% | Degree level match, field relevance |
| Preference alignment | 10% | Job type, salary range, company size preferences |

#### Skill Matching Tiers
1. **Exact Match**: User skill exactly matches job requirement (e.g., "Python" ↔ "Python") → confidence = 1.0
2. **Similar Match**: Synonym or version variant (e.g., "JavaScript" ↔ "JS", "PostgreSQL" ↔ "Postgres") → confidence = 0.8
3. **Related Match**: Skills in the same domain (e.g., "React" ↔ "Frontend Development") → confidence = 0.5

#### Tool: `calculate_match_score`
```python
def calculate_match_score(
    user_profile: UserProfile,
    job_listing: VerifiedJobListing,
    weight_config: Optional[MatchWeightConfig] = None
) -> MatchResult:
    """
    Calculate weighted compatibility score between user and job.
    
    Returns MatchResult with breakdown of all matching factors.
    Raises: ValueError if user_profile or job_listing is invalid.
    """
```

#### Flow
1. Receive verified job listings (filtered to `verified_status == "verified"`)
2. For each job, run the scoring algorithm
3. Rank results by `overall_score` descending
4. Return top-N recommendations (configurable, default 10)
5. Pass results to Resume Agent and Cover Letter Agent

---

### 4.2 Resume Optimization Agent (`/agents/resume_agent.py`)

**Model**: `gpt-4o-mini` (DO NOT upgrade without Lead approval)

**Purpose**: Reorganize and optimize user's existing CV content to align with specific job requirements while maintaining 100% factual accuracy.

> **HARD CONSTRAINT**: NEVER invent skills, experience, achievements, or credentials. The resume must ONLY contain information from the user's actual profile. This is validated in every test.

#### Capabilities
1. **Keyword Optimization**: Incorporate job description keywords into existing experience descriptions (only where factually accurate)
2. **Section Reorganization**: Reorder sections to emphasize most relevant experience for the target role
3. **ATS Compatibility**: Apply formatting rules — no graphics, no columns, no tables, no headers/footers, standard fonts, clean section headings
4. **Quantification**: Surface metrics from existing descriptions (do NOT fabricate numbers)

#### Tool: `generate_resume`
```python
def generate_resume(
    user_profile: UserProfile,
    job_listing: VerifiedJobListing,
    match_result: MatchResult,
    template: str = "ats_standard"
) -> ResumeOutput:
    """
    Generate an ATS-optimized resume PDF tailored to the job listing.
    
    CONSTRAINT: All content MUST come from user_profile. No invention.
    Returns ResumeOutput with file path, ATS score, and keyword report.
    Raises: FactualAccuracyError if generated content deviates from profile.
    """
```

#### ATS Formatting Rules
- Font: Arial or Calibri, 10-12pt
- Sections: Contact Info → Summary → Experience → Education → Skills → Certifications
- No images, icons, or graphics
- No multi-column layouts
- No text boxes or tables
- Standard bullet points (•)
- File format: PDF (via `python-docx` → PDF conversion)

#### Factual Accuracy Verification Pipeline
1. Extract all claims from generated resume
2. Cross-reference each claim against `UserProfile` fields
3. Flag any claim not directly traceable to profile data
4. If any flag is raised → reject output, regenerate with stricter constraints
5. Log verification result

---

### 4.3 Cover Letter Agent (`/agents/cover_letter_agent.py`)

**Model**: `gpt-4o-mini` (DO NOT upgrade without Lead approval)

**Purpose**: Generate personalized, professional cover letters that complement the optimized resume.

#### Capabilities
1. **Personalization**: Reference specific company projects, values, or news when company info is available
2. **Keyword Integration**: Incorporate ≥ 80% of job description keywords naturally
3. **Tone Matching**: Adjust formality based on industry (tech vs. finance vs. creative)
4. **Resume Coordination**: Ensure cover letter content complements (not duplicates) resume content
5. **Fallback**: When company info is unavailable, produce a professional generic letter

#### Tool: `generate_cover_letter`
```python
def generate_cover_letter(
    user_profile: UserProfile,
    job_listing: VerifiedJobListing,
    match_result: MatchResult,
    resume_output: ResumeOutput,
    company_info: Optional[CompanyInfo] = None
) -> CoverLetterOutput:
    """
    Generate a tailored cover letter for the job application.
    
    Coordinates with resume output to avoid content duplication.
    CONSTRAINT: All claims about the user MUST be factual.
    Returns CoverLetterOutput with file path and metrics.
    """
```

#### Letter Structure
1. **Header**: User contact info + date + company address
2. **Opening**: Hook referencing specific role + enthusiasm
3. **Body P1**: Most relevant experience aligned to job requirements
4. **Body P2**: Key skills + achievements (from profile only) matching job needs
5. **Body P3**: Cultural fit / company-specific personalization
6. **Closing**: Call to action + availability + professional sign-off

---

## 5. Tools Module (`/tools/document_tools.py`)

This module contains three tool functions that the agents call:

| Tool Function | Called By | Purpose |
|---|---|---|
| `calculate_match_score` | Job Matching Agent | Compute weighted compatibility score |
| `generate_resume` | Resume Agent | Generate ATS-optimized resume PDF |
| `generate_cover_letter` | Cover Letter Agent | Generate personalized cover letter |

### Additional Utility Functions
```python
# PDF generation from DOCX template
def render_pdf(docx_path: str, output_path: str) -> str

# Extract keywords from job description using NLP
def extract_job_keywords(job_description: str) -> List[str]

# Validate factual accuracy of generated content against user profile
def verify_factual_accuracy(generated_text: str, user_profile: UserProfile) -> FactualAccuracyResult

# ATS compatibility checker
def check_ats_compatibility(document_path: str) -> ATSCompatibilityResult

# Skill synonym/similarity lookup
def find_skill_matches(user_skills: List[str], job_skills: List[str]) -> List[SkillMatch]
```

---

## 6. API Integrations

### 6.1 OpenAI API (via `openai-agents` SDK)
- **Model**: `gpt-4o-mini` for all three agents
- **Usage**:
  - Job Matching: Semantic skill similarity, recommendation reasoning
  - Resume Agent: Content reorganization prompts, keyword integration
  - Cover Letter Agent: Letter generation, tone adjustment
- **SDK**: `openai-agents==0.0.3` with `openai>=1.40.0`
- **Tracing**: Enable OpenAI Agents SDK tracing (compatible with Member 5's Datadog export)

### 6.2 Document Processing Libraries
- `pypdf==4.2.0` — Read existing PDF resumes
- `pdfplumber==0.11.1` — Extract text/tables from PDF resumes
- `python-docx==1.1.2` — Generate DOCX files, apply templates, convert to PDF

### 6.3 Database Access
- **PostgreSQL** (via `sqlalchemy==2.0.31` + `psycopg2-binary==2.9.9`): Read/write match results, document metadata
- **Redis** (via `redis==5.0.7`): Read user profile context from session store
- **MongoDB** (via `pymongo==4.8.0`): Store generated documents and version history

### 6.4 Environment Variables Required
```bash
OPENAI_API_KEY=                          # OpenAI API key
DATABASE_URL=                            # PostgreSQL connection string
REDIS_URL=                               # Redis connection string
MONGODB_URI=                             # MongoDB connection string
DOCUMENT_OUTPUT_DIR=                     # Path for generated PDFs
LOG_LEVEL=                               # Logging level (default: INFO)
MAX_RECOMMENDATIONS=                     # Max jobs to recommend (default: 10)
```

---

## 7. Error Handling Strategy

| Error Scenario | Handling |
|---|---|
| Empty/invalid user profile | Return descriptive error JSON, never crash the pipeline |
| No verified jobs available | Return empty recommendations with informative message |
| OpenAI API failure | Retry with exponential backoff (3 attempts, base 2s) |
| OpenAI rate limiting | Queue request, retry after `Retry-After` header delay |
| PDF generation failure | Log error, attempt DOCX-only fallback, notify orchestrator |
| Factual accuracy violation | Reject output, regenerate with stricter prompt, log violation |
| Missing company info (cover letter) | Generate professional generic letter (graceful degradation) |
| Database connection failure | Retry 3x, then fail gracefully with cached data if available |
| Invalid job listing format | Validate input schema, reject with descriptive error |

All errors return structured JSON conforming to the Tool Interface Spec error format.

---

## 8. Security & Privacy Requirements

Per SRS Section 5.2 and shared team rules:

1. **Encryption at Rest**: All PII (CVs, contact info, tokens) encrypted with **AES-256**
2. **Encryption in Transit**: All API calls over **TLS 1.3**
3. **No Hardcoded Secrets**: All API keys, OAuth tokens, and DB credentials via environment variables
4. **Data Minimization**: Generated documents stored with user_id reference only; raw profile data not duplicated
5. **Audit Logging**: Log all document generation events (who, when, what) without logging PII content
6. **Document Retention**: Generated documents respect user-configurable retention policies

---

## 9. Phased Delivery Schedule

### Phase 2 — Week 3: Job Matching
- [ ] Implement data models (`/models/matching_models.py`)
- [ ] Implement skill matching utilities (`/tools/document_tools.py` — matching portion)
- [ ] Implement Job Matching Agent (`/agents/job_matching_agent.py`)
- [ ] Write unit tests for matching (≥ 10 test cases)
- [ ] Validate precision > 85% on test datasets

### Phase 3 — Week 4: Resume & Cover Letter
- [ ] Implement resume generation tools (`/tools/document_tools.py` — resume portion)
- [ ] Implement Resume Optimization Agent (`/agents/resume_agent.py`)
- [ ] Implement factual accuracy verification pipeline
- [ ] Implement Cover Letter Agent (`/agents/cover_letter_agent.py`)
- [ ] Write unit tests for resume + cover letter (≥ 10 test cases each)
- [ ] Validate ATS compatibility, keyword incorporation ≥ 80%
- [ ] Validate factual accuracy = 100%
- [ ] Open PR to `develop` with all tests passing

---

## 10. Acceptance Criteria Checklist

| # | Criterion | Source | Metric |
|---|---|---|---|
| 1 | Job Matching precision > 85% on top recommendations | SRS 5.3 | Precision@10 |
| 2 | Resume factual accuracy = 100% | Hard constraint | Zero invented content |
| 3 | Cover letter keyword inclusion ≥ 80% | SRS requirement | Keyword match % |
| 4 | Resume passes ATS compatibility validation | SRS requirement | No unsupported formatting |
| 5 | All tests green before PR | Shared rule | pytest exit code 0 |
| 6 | No hardcoded secrets | Shared rule | grep verification |
| 7 | Conventional commits | Shared rule | feat:/fix:/test:/docs: |
| 8 | PR open 2 days before Week 4 end | Shared rule | PR timestamp |
