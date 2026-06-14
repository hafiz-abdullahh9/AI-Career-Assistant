# Member 3 — Task Breakdown
## Job Matching, Resume Optimization & Cover Letter Generation
### Agent 02 — AI-Based Career Assistant System

---

## Legend
- `[ ]` — Not started
- `[/]` — In progress
- `[x]` — Complete

---

## Phase 0: Setup & Preparation (Days 1–2)

### 0.1 Environment Setup
- [ ] Create and activate Python virtual environment
- [ ] Install all dependencies from `requirements.txt`
- [ ] Verify all packages install without conflicts
- [ ] Set up `.env` file with all required environment variables (see Implementation Plan §6.4)
- [ ] Verify database connections (PostgreSQL, Redis, MongoDB)

### 0.2 Branch & Repo Setup
- [ ] Pull latest `develop` branch
- [ ] Create `feature/matching-documents` branch from `develop`
- [ ] Verify repo skeleton exists (created by Member 1)
- [ ] Read and understand `/docs/tool_interface_spec.md` (from Member 1)
- [ ] Confirm Profile Context schema from Member 1 (`/infra/profile_context.py`)
- [ ] Review Member 2's verified job listing output format
- [ ] Create all required directories under the branch

### 0.3 Dependency Verification
- [ ] Confirm Member 2's verified job listings are available (or create mock data for development)
- [ ] Confirm Member 1's Tool Interface Spec defines the function signatures we need
- [ ] Confirm Member 1's Profile Context schema is compatible with our `UserProfile` model
- [ ] Create mock/fixture data for standalone development if upstream not ready

---

## Phase 1: Data Models & Shared Utilities (Days 3–4)

### 1.1 Pydantic Models (`/models/matching_models.py`)
- [ ] Define `UserProfile` model (or import from Member 1's schema)
- [ ] Define `ExperienceEntry` model
- [ ] Define `EducationEntry` model
- [ ] Define `VerifiedJobListing` model (match Member 2's output format)
- [ ] Define `MatchResult` model
- [ ] Define `SkillMatch` model
- [ ] Define `MatchWeightConfig` model
- [ ] Define `ResumeOutput` model
- [ ] Define `KeywordReport` model
- [ ] Define `CoverLetterOutput` model
- [ ] Define `CompanyInfo` model
- [ ] Define `FactualAccuracyResult` model
- [ ] Define `ATSCompatibilityResult` model
- [ ] Add JSON serialization support for all models
- [ ] Write unit tests for model validation (edge cases, required vs optional fields)

### 1.2 Configuration Module (`/config/matching_config.py`)
- [ ] Define default match weight configuration
- [ ] Define ATS formatting rules as constants
- [ ] Define resume template options
- [ ] Define cover letter tone presets
- [ ] Load environment variables via `python-dotenv`
- [ ] Add config validation on startup

### 1.3 Skill Taxonomy & Synonym Map (`/data/skill_taxonomy.json`)
- [ ] Build initial skill synonym dictionary (≥ 200 common tech/business skills)
- [ ] Include related skill mappings (e.g., "React" → "Frontend Development")
- [ ] Structure: `{ "canonical_name": {"synonyms": [...], "related": [...], "category": "..."} }`
- [ ] Write loader utility to parse taxonomy at runtime

---

## Phase 2: Job Matching Agent — Week 3

### 2.1 Skill Matching Utilities (`/tools/document_tools.py` — matching section)
- [ ] Implement `find_skill_matches(user_skills, job_skills) -> List[SkillMatch]`
  - [ ] Exact match detection (case-insensitive)
  - [ ] Synonym match detection (from taxonomy)
  - [ ] Related skill detection (from taxonomy)
  - [ ] Assign confidence scores per tier (1.0 / 0.8 / 0.5)
- [ ] Implement `extract_job_keywords(job_description) -> List[str]`
  - [ ] Use OpenAI API for keyword extraction
  - [ ] Deduplicate and normalize keywords
- [ ] Write unit tests for skill matching (≥ 5 cases)
- [ ] Write unit tests for keyword extraction (≥ 3 cases)

### 2.2 Match Score Calculator (`/tools/document_tools.py`)
- [ ] Implement `calculate_match_score(user_profile, job_listing, weight_config) -> MatchResult`
  - [ ] Skill match component (40% weight)
  - [ ] Experience relevance component (25% weight)
  - [ ] Location compatibility component (15% weight)
  - [ ] Education fit component (10% weight)
  - [ ] Preference alignment component (10% weight)
  - [ ] Weighted aggregation into overall score (0–100)
  - [ ] Generate recommendation reason text via OpenAI
- [ ] Write unit tests for score calculation (≥ 5 cases)
  - [ ] Test perfect match scenario
  - [ ] Test zero match scenario
  - [ ] Test partial match with varying weights
  - [ ] Test edge cases (empty skills, no experience)
  - [ ] Test location matching (remote, exact, regional)

### 2.3 Job Matching Agent (`/agents/job_matching_agent.py`)
- [ ] Set up OpenAI Agents SDK agent with `gpt-4o-mini`
- [ ] Register `calculate_match_score` as agent tool
- [ ] Implement agent instructions/system prompt
- [ ] Implement input validation (reject non-verified jobs)
- [ ] Implement batch matching across all verified jobs
- [ ] Implement ranking and top-N filtering
- [ ] Implement detailed breakdown generation
- [ ] Implement error handling:
  - [ ] Empty profile → informative error
  - [ ] No verified jobs → empty results with message
  - [ ] API failure → exponential backoff retry
- [ ] Enable SDK tracing
- [ ] Write unit tests (≥ 10 cases):
  - [ ] Test with valid profile + valid jobs → ranked results
  - [ ] Test with empty profile → descriptive error
  - [ ] Test with no verified jobs → empty result
  - [ ] Test ranking order (highest score first)
  - [ ] Test score breakdown accuracy
  - [ ] Test skill match types (exact, similar, related)
  - [ ] Test location matching (remote preference)
  - [ ] Test experience level matching
  - [ ] Test education requirement matching
  - [ ] Test with malformed input → graceful error

### 2.4 Matching Validation
- [ ] Create test dataset with known correct matches
- [ ] Measure Precision@10 on test dataset
- [ ] Verify precision > 85% threshold
- [ ] Document results

---

## Phase 3: Resume & Cover Letter — Week 4

### 3.1 Resume Generation Utilities (`/tools/document_tools.py` — resume section)
- [ ] Implement `render_pdf(docx_path, output_path) -> str`
  - [ ] Use `python-docx` for DOCX generation
  - [ ] Convert DOCX to PDF
  - [ ] Return output file path
- [ ] Implement `check_ats_compatibility(document_path) -> ATSCompatibilityResult`
  - [ ] Check for forbidden elements (images, tables, multi-column)
  - [ ] Verify font compatibility
  - [ ] Verify section heading standards
  - [ ] Return score and list of issues
- [ ] Implement `verify_factual_accuracy(generated_text, user_profile) -> FactualAccuracyResult`
  - [ ] Extract claims from generated text using OpenAI
  - [ ] Cross-reference each claim against UserProfile
  - [ ] Flag any claim not traceable to profile
  - [ ] Return pass/fail with details
- [ ] Write unit tests for each utility (≥ 3 cases each)

### 3.2 Resume Optimization Agent (`/agents/resume_agent.py`)
- [ ] Set up OpenAI Agents SDK agent with `gpt-4o-mini`
- [ ] Register `generate_resume` as agent tool
- [ ] Implement agent instructions/system prompt
  - [ ] CRITICAL: Include hard constraint about factual accuracy in system prompt
  - [ ] Include ATS formatting rules
  - [ ] Include keyword incorporation instructions
- [ ] Implement resume generation pipeline:
  - [ ] Parse existing CV content from user profile
  - [ ] Extract job keywords from target listing
  - [ ] Reorganize sections for relevance
  - [ ] Incorporate keywords into existing descriptions
  - [ ] Apply ATS-compatible formatting
  - [ ] Generate DOCX from template
  - [ ] Convert to PDF
  - [ ] Run ATS compatibility check
  - [ ] Run factual accuracy verification
  - [ ] Generate keyword incorporation report
- [ ] Implement error handling:
  - [ ] Missing CV content → error with guidance
  - [ ] PDF generation failure → DOCX fallback
  - [ ] Factual accuracy failure → regenerate with stricter prompt
  - [ ] API failure → exponential backoff retry
- [ ] Enable SDK tracing
- [ ] Write unit tests (≥ 10 cases):
  - [ ] Test with valid profile + job → generates PDF
  - [ ] Test factual accuracy — no invented skills
  - [ ] Test factual accuracy — no invented experience
  - [ ] Test factual accuracy — no invented achievements
  - [ ] Test ATS compatibility — no images
  - [ ] Test ATS compatibility — no multi-column
  - [ ] Test keyword incorporation ≥ 80%
  - [ ] Test section reordering for relevance
  - [ ] Test with minimal profile → still generates valid resume
  - [ ] Test with missing CV → descriptive error

### 3.3 Cover Letter Agent (`/agents/cover_letter_agent.py`)
- [ ] Set up OpenAI Agents SDK agent with `gpt-4o-mini`
- [ ] Register `generate_cover_letter` as agent tool
- [ ] Implement agent instructions/system prompt
  - [ ] Include tone adjustment rules per industry
  - [ ] Include resume coordination instructions
  - [ ] Include factual accuracy constraint
- [ ] Implement cover letter generation pipeline:
  - [ ] Determine tone based on industry/job type
  - [ ] Gather company info (if available)
  - [ ] Extract key job requirements
  - [ ] Map user's relevant experience to requirements
  - [ ] Generate letter using structured template
  - [ ] Verify keyword inclusion ≥ 80%
  - [ ] Verify no content duplication with resume
  - [ ] Generate output file (PDF/DOCX)
- [ ] Implement fallback for missing company info
- [ ] Implement error handling:
  - [ ] Missing profile → descriptive error
  - [ ] API failure → exponential backoff retry
  - [ ] Low keyword match → regenerate with emphasis
- [ ] Enable SDK tracing
- [ ] Write unit tests (≥ 10 cases):
  - [ ] Test with full info → personalized letter
  - [ ] Test with missing company info → generic professional letter
  - [ ] Test keyword inclusion ≥ 80%
  - [ ] Test tone matches industry (tech)
  - [ ] Test tone matches industry (finance)
  - [ ] Test no content duplication with resume
  - [ ] Test letter structure (all sections present)
  - [ ] Test factual accuracy — no invented claims
  - [ ] Test with minimal profile → still valid letter
  - [ ] Test coordination with resume output

---

## Phase 4: Integration & Polish (End of Week 4)

### 4.1 End-to-End Pipeline Testing
- [ ] Create integration test: profile → matching → resume → cover letter
- [ ] Verify data flows correctly between all three agents
- [ ] Verify output formats match Member 4's expected input
- [ ] Test with 5+ diverse user profiles
- [ ] Test with 20+ diverse job listings

### 4.2 Documentation
- [ ] Document all tool functions with docstrings
- [ ] Update `/docs/tool_interface_spec.md` if needed (coordinate with Member 1)
- [ ] Create `README.md` section for Member 3's components
- [ ] Document environment variable requirements

### 4.3 Code Quality
- [ ] Run linter (flake8/black) on all files
- [ ] Ensure all functions have type hints
- [ ] Ensure logging via `loguru` for all important operations
- [ ] Verify no hardcoded secrets (grep check)
- [ ] Verify conventional commit messages

### 4.4 PR Submission
- [ ] Run full test suite — all tests green
- [ ] Create PR from `feature/matching-documents` → `develop`
- [ ] Write comprehensive PR description
- [ ] Request review from Member 1 (Project Lead)
- [ ] Address review feedback

---

## Task Count Summary

| Phase | Tasks | Estimated Effort |
|---|---|---|
| Phase 0: Setup | 14 tasks | 1–2 days |
| Phase 1: Models & Utilities | 17 tasks | 2 days |
| Phase 2: Job Matching | 30+ tasks | 5–7 days (Week 3) |
| Phase 3: Resume & Cover Letter | 40+ tasks | 7–10 days (Week 4) |
| Phase 4: Integration & Polish | 13 tasks | 2–3 days |
| **Total** | **~114 tasks** | **~3 weeks** |

---

## Critical Path Items

1. **Mock data from Member 2** — If not available, create fixtures on Day 1
2. **Profile Context schema from Member 1** — Must align before models are finalized
3. **Tool Interface Spec from Member 1** — Must read before implementing tool functions
4. **Factual accuracy verification** — Central to acceptance; test early and often
5. **ATS compatibility** — Research common ATS systems' parsing rules early
