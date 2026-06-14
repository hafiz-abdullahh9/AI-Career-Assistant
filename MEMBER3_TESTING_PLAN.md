# Member 3 — Testing Plan
## Job Matching, Resume Optimization & Cover Letter Generation
### Agent 02 — AI-Based Career Assistant System

---

## 1. Testing Strategy Overview

### 1.1 Testing Pyramid

```
            ┌─────────────────┐
            │   Integration   │  ← 5 tests
            │   Tests         │     End-to-end pipeline
            │                 │
         ┌──┴─────────────────┴──┐
         │    Agent Tests         │  ← 30+ tests
         │    (Unit + Mocked LLM) │     Agent behavior
         │                       │
      ┌──┴───────────────────────┴──┐
      │     Tool Function Tests      │  ← 20+ tests
      │     (Pure logic, no LLM)     │     Core algorithms
      │                              │
   ┌──┴──────────────────────────────┴──┐
   │        Model Validation Tests       │  ← 15+ tests
   │        (Pydantic schema tests)      │     Data integrity
   └─────────────────────────────────────┘
```

### 1.2 Testing Framework & Tools

| Tool | Version | Purpose |
|---|---|---|
| `pytest` | 8.2.2 | Test runner |
| `pytest-asyncio` | 0.23.7 | Async agent test support |
| `pytest-mock` | 3.14.0 | Mocking OpenAI API calls |
| `faker` | 26.0.0 | Generating realistic test data |

### 1.3 Test Execution Commands

```bash
# Run all Member 3 tests
pytest tests/test_matching_documents.py tests/test_matching_models.py -v

# Run with coverage
pytest tests/test_matching_documents.py tests/test_matching_models.py --cov=agents --cov=tools --cov=models --cov-report=html

# Run only matching tests
pytest tests/test_matching_documents.py -k "test_matching" -v

# Run only resume tests
pytest tests/test_matching_documents.py -k "test_resume" -v

# Run only cover letter tests
pytest tests/test_matching_documents.py -k "test_cover_letter" -v

# Run integration tests
pytest tests/integration/test_pipeline_m3.py -v

# Run all tests before PR
pytest tests/ -v --tb=short
```

---

## 2. Test Fixtures & Mock Data

### 2.1 Shared Fixtures (`/tests/conftest.py`)

```python
import pytest
from faker import Faker
from tests.fixtures.sample_profiles import (
    full_profile,
    minimal_profile,
    empty_skills_profile,
    senior_engineer_profile,
    data_scientist_profile,
)
from tests.fixtures.sample_job_listings import (
    software_engineer_listing,
    data_scientist_listing,
    no_skills_listing,
    expired_listing,
    batch_listings_20,
)

fake = Faker()

@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response for deterministic testing."""
    ...

@pytest.fixture
def mock_redis_client():
    """Mock Redis client for profile context."""
    ...

@pytest.fixture
def mock_postgres_session():
    """Mock PostgreSQL session for match result storage."""
    ...

@pytest.fixture
def temp_output_dir(tmp_path):
    """Temporary directory for generated documents."""
    resumes = tmp_path / "resumes"
    cover_letters = tmp_path / "cover_letters"
    resumes.mkdir()
    cover_letters.mkdir()
    return tmp_path
```

### 2.2 Sample User Profiles (`/tests/fixtures/sample_profiles.py`)

| Profile | Description | Use Case |
|---|---|---|
| `full_profile` | Complete profile with all fields populated | Happy path tests |
| `minimal_profile` | Only required fields (name, email, 1 skill) | Edge case: minimal input |
| `empty_skills_profile` | Profile with no skills listed | Error handling: no skills |
| `senior_engineer_profile` | 10+ years experience, 15+ skills | High match score scenarios |
| `data_scientist_profile` | ML/AI focused, Python/R skills | Cross-domain matching |
| `career_changer_profile` | Switching from finance to tech | Low match with partial overlap |
| `fresh_graduate_profile` | No work experience, only education | Entry-level matching |

### 2.3 Sample Job Listings (`/tests/fixtures/sample_job_listings.py`)

| Listing | Description | Use Case |
|---|---|---|
| `software_engineer_listing` | Standard SWE role, Python/AWS/Docker | Standard matching |
| `data_scientist_listing` | ML role, Python/TensorFlow/SQL | Cross-skill matching |
| `senior_manager_listing` | Leadership role, 10+ years required | Experience-weighted test |
| `remote_internship_listing` | Remote internship, entry-level | Location + preference test |
| `no_skills_listing` | Listing with empty required_skills | Edge case handling |
| `batch_listings_20` | List of 20 diverse listings | Ranking and top-N tests |

---

## 3. Unit Test Cases

### 3.1 Model Validation Tests (`/tests/test_matching_models.py`)

| # | Test Name | Description | Expected |
|---|---|---|---|
| M1 | `test_match_result_valid` | Create MatchResult with valid data | Model validates |
| M2 | `test_match_result_score_bounds` | Score outside 0-100 range | ValidationError |
| M3 | `test_match_result_serialization` | Serialize/deserialize to JSON | Round-trip matches |
| M4 | `test_skill_match_valid_types` | All three match types accepted | Model validates |
| M5 | `test_skill_match_invalid_type` | Invalid match_type string | ValidationError |
| M6 | `test_resume_output_required_fields` | Missing required fields | ValidationError |
| M7 | `test_cover_letter_output_valid` | All fields populated correctly | Model validates |
| M8 | `test_keyword_report_percentage` | Calculate incorporation % | Correct percentage |
| M9 | `test_user_profile_optional_fields` | Profile with only required fields | Model validates |
| M10 | `test_verified_job_listing_status` | All three verified_status values | Each accepted |
| M11 | `test_match_weight_config_defaults` | Default weights sum to 1.0 | Sum == 1.0 |
| M12 | `test_experience_entry_current_job` | end_date = None for current | Model validates |
| M13 | `test_factual_accuracy_result` | Both pass and fail states | Model validates |
| M14 | `test_ats_compatibility_result` | Score + issues list | Model validates |
| M15 | `test_company_info_optional` | CompanyInfo all fields optional | Model validates |

---

### 3.2 Job Matching Agent Tests (`/tests/test_matching_documents.py`)

| # | Test Name | Description | Expected | Acceptance Criteria |
|---|---|---|---|---|
| JM1 | `test_matching_valid_profile_valid_jobs` | Full profile matched against 5 verified jobs | Returns ranked List[MatchResult] | — |
| JM2 | `test_matching_returns_ranked_results` | Results ordered by overall_score | First result has highest score | — |
| JM3 | `test_matching_exact_skill_match` | User has "Python", job requires "Python" | confidence = 1.0, match_type = "exact" | — |
| JM4 | `test_matching_similar_skill_match` | User has "JavaScript", job requires "JS" | confidence = 0.8, match_type = "similar" | — |
| JM5 | `test_matching_related_skill_match` | User has "React", job requires "Frontend" | confidence = 0.5, match_type = "related" | — |
| JM6 | `test_matching_empty_profile_error` | Profile with no skills/experience | Returns descriptive error, no crash | Never crash |
| JM7 | `test_matching_no_verified_jobs` | Empty job list provided | Returns empty results with message | Never crash |
| JM8 | `test_matching_score_range_0_100` | All scores within bounds | 0.0 ≤ score ≤ 100.0 for all results | — |
| JM9 | `test_matching_precision_threshold` | Known correct matches in test set | Precision@10 > 85% | **SRS 5.3** |
| JM10 | `test_matching_location_remote_preference` | User prefers remote, job is remote | Location score boosted | — |
| JM11 | `test_matching_top_n_filtering` | Request top 5 from 20 jobs | Returns exactly 5 results | — |
| JM12 | `test_matching_score_breakdown_present` | Each result has all score components | All 5 sub-scores present | — |
| JM13 | `test_matching_missing_skills_listed` | Skills user lacks for each job | missing_skills populated correctly | — |
| JM14 | `test_matching_api_failure_retry` | Mock OpenAI API error | Retries with backoff, eventually fails gracefully | Never crash |
| JM15 | `test_matching_only_verified_jobs` | Mix of verified + rejected jobs | Only verified jobs processed | — |

---

### 3.3 Resume Agent Tests (`/tests/test_matching_documents.py`)

| # | Test Name | Description | Expected | Acceptance Criteria |
|---|---|---|---|---|
| R1 | `test_resume_generates_pdf` | Valid profile + job → PDF | PDF file exists at output path | — |
| R2 | `test_resume_no_invented_skills` | Compare resume skills vs profile skills | All resume skills ∈ profile skills | **Factual accuracy = 100%** |
| R3 | `test_resume_no_invented_experience` | Compare resume experience vs profile | All experience entries ∈ profile | **Factual accuracy = 100%** |
| R4 | `test_resume_no_invented_achievements` | Scan for fabricated metrics | No numbers/achievements not in profile | **Factual accuracy = 100%** |
| R5 | `test_resume_no_invented_certifications` | Compare certs in resume vs profile | All certifications ∈ profile | **Factual accuracy = 100%** |
| R6 | `test_resume_ats_no_images` | Check PDF for embedded images | No images detected | **ATS compatible** |
| R7 | `test_resume_ats_no_multicolumn` | Check layout for multi-column | Single column layout | **ATS compatible** |
| R8 | `test_resume_ats_standard_font` | Verify font is Arial or Calibri | Font matches allowed list | **ATS compatible** |
| R9 | `test_resume_keyword_incorporation` | Count job keywords in resume | Incorporation ≥ 80% | **Keyword ≥ 80%** |
| R10 | `test_resume_keyword_report_accurate` | Verify keyword report matches content | Report counts match actual count | — |
| R11 | `test_resume_sections_present` | Check all standard sections exist | Contact, Summary, Experience, Education, Skills | — |
| R12 | `test_resume_section_reordering` | Most relevant section first | Top section matches strongest match area | — |
| R13 | `test_resume_minimal_profile` | Profile with very little info | Generates valid resume with available info | Never crash |
| R14 | `test_resume_missing_cv_error` | Profile with no resume_raw_text | Returns descriptive error | Never crash |
| R15 | `test_resume_pdf_render_failure_fallback` | Mock PDF rendering failure | Falls back to DOCX output | — |

---

### 3.4 Cover Letter Agent Tests (`/tests/test_matching_documents.py`)

| # | Test Name | Description | Expected | Acceptance Criteria |
|---|---|---|---|---|
| CL1 | `test_cover_letter_generates_file` | Valid inputs → file created | File exists at output path | — |
| CL2 | `test_cover_letter_personalized_with_company` | Company info provided | References company name/projects | — |
| CL3 | `test_cover_letter_generic_without_company` | No company info | Professional generic letter, no hallucinated company info | — |
| CL4 | `test_cover_letter_keyword_inclusion` | Count job keywords in letter | Keyword inclusion ≥ 80% | **Keyword ≥ 80%** |
| CL5 | `test_cover_letter_professional_tone_tech` | Tech industry job | Appropriate tech-industry tone | — |
| CL6 | `test_cover_letter_professional_tone_finance` | Finance industry job | More formal tone | — |
| CL7 | `test_cover_letter_no_resume_duplication` | Compare letter vs resume content | Letter complements, doesn't duplicate resume | — |
| CL8 | `test_cover_letter_structure_complete` | Check letter sections | Header, opening, body (3 paragraphs), closing | — |
| CL9 | `test_cover_letter_factual_accuracy` | No invented claims about user | All claims traceable to profile | **Factual accuracy** |
| CL10 | `test_cover_letter_contact_info_present` | User's contact info in header | Name, email, phone (if available) | — |
| CL11 | `test_cover_letter_job_title_referenced` | References specific job title | Job title appears in letter | — |
| CL12 | `test_cover_letter_minimal_profile` | Minimal user profile | Still generates valid letter | Never crash |
| CL13 | `test_cover_letter_coordinates_with_resume` | Resume output provided | Letter references different aspects than resume | — |
| CL14 | `test_cover_letter_api_failure_retry` | Mock API error | Retries with backoff | Never crash |
| CL15 | `test_cover_letter_low_keyword_regenerate` | First gen has < 80% keywords | Agent regenerates with keyword emphasis | — |

---

### 3.5 Tool Function Tests (`/tests/test_matching_documents.py`)

| # | Test Name | Description | Expected |
|---|---|---|---|
| T1 | `test_find_skill_matches_exact` | Exact skill matches | Returns matches with confidence 1.0 |
| T2 | `test_find_skill_matches_synonyms` | Synonym matches (JS/JavaScript) | Returns matches with confidence 0.8 |
| T3 | `test_find_skill_matches_related` | Related skills (React/Frontend) | Returns matches with confidence 0.5 |
| T4 | `test_find_skill_matches_no_match` | Completely unrelated skills | Returns empty list |
| T5 | `test_find_skill_matches_case_insensitive` | "python" vs "Python" | Returns exact match |
| T6 | `test_extract_job_keywords` | Extract keywords from description | Returns relevant keyword list |
| T7 | `test_extract_job_keywords_empty` | Empty description | Returns empty list |
| T8 | `test_verify_factual_accuracy_pass` | Content matches profile exactly | Returns pass with 100% accuracy |
| T9 | `test_verify_factual_accuracy_fail` | Content has invented skill | Returns fail with flagged items |
| T10 | `test_check_ats_compatibility_pass` | Clean ATS-friendly document | Score = 100, no issues |
| T11 | `test_check_ats_compatibility_fail` | Document with images/columns | Score < 100, issues listed |
| T12 | `test_render_pdf_success` | Valid DOCX input | PDF file created |
| T13 | `test_render_pdf_invalid_input` | Non-existent DOCX path | Raises PDFRenderError |
| T14 | `test_calculate_match_score_weights` | Custom weight configuration | Score reflects custom weights |
| T15 | `test_calculate_match_score_perfect` | Perfect match profile | Score near 100.0 |
| T16 | `test_calculate_match_score_zero` | No overlap at all | Score near 0.0 |
| T17 | `test_calculate_match_score_partial` | Some skills match | Score between 30-70 |
| T18 | `test_calculate_match_score_experience` | Experience level matching | Experience component scored correctly |
| T19 | `test_calculate_match_score_location` | Location match variations | Location component varies by match type |
| T20 | `test_calculate_match_score_education` | Education level matching | Education component scored correctly |

---

## 4. Integration Tests (`/tests/integration/test_pipeline_m3.py`)

| # | Test Name | Description | Expected |
|---|---|---|---|
| I1 | `test_full_pipeline_single_job` | Profile → match → resume → cover letter for 1 job | All outputs valid, all files generated |
| I2 | `test_full_pipeline_batch_jobs` | Profile → match 20 jobs → top 3 → resume + CL each | 3 resumes + 3 cover letters generated |
| I3 | `test_pipeline_data_consistency` | Verify data flows correctly between agents | Match result used by resume/CL agents |
| I4 | `test_pipeline_output_format_for_member4` | Verify output matches Member 4's expected input | Output has all fields Member 4 needs |
| I5 | `test_pipeline_error_propagation` | Error in matching → graceful pipeline failure | No crash, descriptive error in output |

---

## 5. Acceptance Criteria Validation Tests

These are the **critical tests** that directly validate the SRS acceptance criteria:

| Criterion | Test(s) | Target | How Measured |
|---|---|---|---|
| **Matching precision > 85%** | JM9 | Precision@10 > 0.85 | Known-correct test set with labeled matches |
| **Resume factual accuracy = 100%** | R2, R3, R4, R5 | Zero invented content | Cross-reference every claim against UserProfile |
| **Cover letter keywords ≥ 80%** | CL4 | ≥ 80% inclusion | Count job keywords present in letter ÷ total |
| **Resume ATS compatible** | R6, R7, R8 | No unsupported elements | Check for images, multi-column, non-standard fonts |
| **All tests green before PR** | All | Exit code 0 | `pytest` with `--tb=short` |
| **No hardcoded secrets** | Grep check | 0 matches | `grep -r "sk-" --include="*.py"` |

### Precision@10 Measurement Methodology

```python
def measure_precision_at_10(agent, profiles, jobs, known_matches):
    """
    Measure Precision@10 for the matching agent.
    
    known_matches: Dict[user_id, Set[job_id]] — the ground truth
    
    For each user:
    1. Get top 10 recommendations from agent
    2. Count how many are in known_matches
    3. Precision@10 = correct_in_top_10 / 10
    
    Average across all users for final metric.
    """
    precisions = []
    for profile in profiles:
        results = agent.match(profile, jobs)[:10]
        recommended_ids = {r.job_id for r in results}
        correct = recommended_ids & known_matches[profile.user_id]
        precisions.append(len(correct) / 10)
    return sum(precisions) / len(precisions)
```

---

## 6. Mocking Strategy

### 6.1 What to Mock

| Component | Mock? | Reason |
|---|---|---|
| OpenAI API calls | **YES** | Deterministic tests, no API cost, no rate limits |
| PostgreSQL queries | **YES** | No DB dependency for unit tests |
| Redis reads | **YES** | No Redis server needed for unit tests |
| MongoDB writes | **YES** | No MongoDB server needed for unit tests |
| PDF rendering | **PARTIAL** | Mock for error tests, real for output validation |
| Skill taxonomy JSON | **NO** | Load real file — it's static data |
| Pydantic models | **NO** | Validate real models |

### 6.2 Mock OpenAI Pattern

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_openai():
    """Mock OpenAI API for deterministic testing."""
    with patch("agents.Runner.run") as mock_run:
        mock_result = AsyncMock()
        mock_result.final_output = '{"score": 85.5, "reason": "Strong skill match"}'
        mock_run.return_value = mock_result
        yield mock_run
```

### 6.3 Mock Database Pattern

```python
@pytest.fixture
def mock_db_session():
    """Mock SQLAlchemy session."""
    session = AsyncMock()
    session.execute.return_value = MockResult(rows=[])
    session.commit.return_value = None
    yield session
```

---

## 7. Test Data Generation

### 7.1 Using Faker for Realistic Data

```python
from faker import Faker

fake = Faker()

def generate_random_profile():
    """Generate a realistic random user profile for testing."""
    skills_pool = [
        "Python", "JavaScript", "SQL", "AWS", "Docker", "React",
        "Machine Learning", "Git", "Linux", "PostgreSQL", "Redis",
        "FastAPI", "Django", "Node.js", "TypeScript", "Kubernetes",
    ]
    return UserProfile(
        user_id=str(fake.uuid4()),
        full_name=fake.name(),
        email=fake.email(),
        phone=fake.phone_number(),
        location=fake.city(),
        summary=fake.paragraph(),
        skills=fake.random_elements(skills_pool, length=fake.random_int(3, 10), unique=True),
        experience=[generate_random_experience() for _ in range(fake.random_int(1, 5))],
        education=[generate_random_education()],
        certifications=fake.random_elements(["AWS Certified", "PMP", "Google Cloud"], unique=True),
        languages=["English"],
        goals=fake.sentence(),
        preferred_locations=[fake.city() for _ in range(2)],
        preferred_job_types=fake.random_elements(["full-time", "remote", "contract"], unique=True),
        resume_raw_text=fake.text(1000),
    )
```

---

## 8. CI/CD Test Integration

### 8.1 Pre-PR Checklist

```bash
# 1. Run all unit tests
pytest tests/test_matching_documents.py tests/test_matching_models.py -v --tb=short

# 2. Run integration tests
pytest tests/integration/test_pipeline_m3.py -v --tb=short

# 3. Check coverage (target: > 80%)
pytest tests/test_matching_documents.py --cov=agents --cov=tools --cov=models --cov-report=term-missing

# 4. Check for hardcoded secrets
grep -rn "sk-\|password\s*=\s*['\"]" --include="*.py" agents/ tools/ models/ config/

# 5. Lint check
python -m flake8 agents/ tools/ models/ config/ --max-line-length 120

# 6. Type check (optional but recommended)
python -m mypy agents/ tools/ models/ config/ --ignore-missing-imports
```

### 8.2 Expected Test Count Summary

| Test File | Test Count | Focus |
|---|---|---|
| `test_matching_models.py` | 15 | Model validation |
| `test_matching_documents.py` — Matching | 15 | Job Matching Agent |
| `test_matching_documents.py` — Resume | 15 | Resume Agent |
| `test_matching_documents.py` — Cover Letter | 15 | Cover Letter Agent |
| `test_matching_documents.py` — Tools | 20 | Tool functions |
| `test_pipeline_m3.py` | 5 | Integration |
| **Total** | **~85** | |

---

## 9. Test Execution Order

Tests are designed to be **independent** and can run in any order. However, for logical development:

1. **First**: Model validation tests → confirms data structures are correct
2. **Second**: Tool function tests → confirms core algorithms work
3. **Third**: Agent tests (mocked) → confirms agent behavior
4. **Fourth**: Integration tests → confirms end-to-end pipeline
5. **Last**: Acceptance criteria tests → confirms SRS compliance
