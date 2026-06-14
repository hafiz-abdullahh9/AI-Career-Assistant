# AI Career Assistant — Tool Interface Specification
**Version**: 1.1.0  
**Author**: Member 1 (Project Lead)  
**Classification**: Team Internal — Confidential  

This specification defines the strict interface contracts for all tool integrations. All specialist engineers (Members 2, 3, 4, 5) must adhere to these schemas to guarantee cross-agent compatibility and robust state transitions.

---

## 1. Global Standards & Protocols

### Naming Conventions
* **Functions / Methods**: `snake_case` (e.g., `scrape_linkedin_jobs`)
* **JSON Properties / Dict Keys**: `snake_case` (e.g., `verified_status`)
* **Status Enums**: `UPPERCASE` strings (e.g., `SUCCESS`, `ERROR`, `PENDING`)

### Unified Response Contracts

#### Standard Success Envelope
All tool completions must return a dictionary matching this envelope structure:
```json
{
  "status": "SUCCESS",
  "data": {},
  "timestamp": "2026-06-14T02:32:00Z"
}
```

#### Standard Error Envelope
When a tool fails (network issues, bad parameters, rate limits), it must catch the local exception and return this standardized error contract instead of crashing:
```json
{
  "status": "ERROR",
  "error": {
    "code": "RATE_LIMIT_ERROR | API_UNAVAILABLE | DATA_CORRUPTION | SECURITY_BREACH | VALIDATION_ERROR",
    "message": "Detailed developer-friendly explanation of why the failure occurred.",
    "retryable": true,
    "recovery_action": "RETRY_WITH_BACKOFF | DEGRADE_GRACEFULLY | HALT_PIPELINE"
  },
  "timestamp": "2026-06-14T02:32:00Z"
}
```

---

## 2. Interface Specifications by Component

### Member 2 — Discovery & Verification (Branch: `feature/job-scraping-verification`)

#### 2.1 `scrape_linkedin_jobs`
* **Signature**:
  ```python
  async def scrape_linkedin_jobs(
      keywords: list[str],
      location: str,
      job_type: str = "Full-time",
      limit: int = 50
  ) -> dict: ...
  ```
* **Success Data Schema (`data` property)**:
  ```json
  {
    "provider": "linkedin",
    "jobs": [
      {
        "job_id": "li-102938",
        "company_name": "Google LLC",
        "job_title": "Senior Systems Engineer",
        "description": "Google is seeking a Senior Systems Engineer...",
        "location": "Mountain View, CA",
        "salary": "$180,000 - $220,000",
        "url": "https://linkedin.com/jobs/view/102938",
        "posted_date": "2026-06-13T12:00:00Z"
      }
    ]
  }
  ```

#### 2.2 `scrape_indeed_jobs`
* **Signature**:
  ```python
  async def scrape_indeed_jobs(
      keywords: list[str],
      location: str,
      job_type: str = "Full-time",
      limit: int = 50
  ) -> dict: ...
  ```
* **Success Data Schema**: Same as `scrape_linkedin_jobs` with `"provider": "indeed"`.

#### 2.3 `verify_company`
* **Signature**:
  ```python
  async def verify_company(company_name: str) -> dict: ...
  ```
* **Success Data Schema**:
  ```json
  {
    "company_name": "Google LLC",
    "verified_status": true,
    "confidence_score": 0.99,
    "registry_match": "Google LLC (Delaware Division of Corporations ID: 3581029)",
    "flagged_suspicious": false,
    "reason": "Active legal entity found in primary registries; valid contact channels verified."
  }
  ```

---

### Member 3 — Matching & Document Customization (Branch: `feature/matching-documents`)

#### 2.4 `calculate_match_score`
* **Signature**:
  ```python
  def calculate_match_score(
      profile_skills: list[str],
      profile_experience: list[dict],
      job_requirements: dict
  ) -> dict: ...
  ```
* **Success Data Schema**:
  ```json
  {
    "compatibility_score": 92.5,
    "matched_skills": ["Python", "Docker", "SQL"],
    "missing_skills": ["Kubernetes"],
    "experience_match": true,
    "score_breakdown": {
      "skills_weight_score": 45.0,
      "experience_weight_score": 30.0,
      "location_weight_score": 17.5
    },
    "reasoning": "Candidate matches critical stack (Python/Docker) and meets minimum experience duration. Kubernetes missing."
  }
  ```

#### 2.5 `generate_resume`
* **Hard Constraint**: 100% factual accuracy. No hallucination of skills, roles, or dates.
* **Signature**:
  ```python
  async def generate_resume(
      profile_data: dict,
      job_details: dict
  ) -> dict: ...
  ```
* **Success Data Schema**:
  ```json
  {
    "pdf_path": "/storage/resumes/usr_99_google_res.pdf",
    "keyword_density": 0.88,
    "ats_check_passed": true,
    "validation_report": {
      "no_invented_skills": true,
      "no_invented_roles": true
    }
  }
  ```

#### 2.6 `generate_cover_letter`
* **Signature**:
  ```python
  async def generate_cover_letter(
      profile_data: dict,
      job_details: dict
  ) -> dict: ...
  ```
* **Success Data Schema**:
  ```json
  {
    "pdf_path": "/storage/cover_letters/usr_99_google_cl.pdf",
    "text_content": "Dear Hiring Committee, I am writing to express my interest in..."
  }
  ```

---

### Member 4 — Application Automation & Tracking (Branch: `feature/application-automation`)

#### 2.7 `send_application_email`
* **Signature**:
  ```python
  async def send_application_email(
      to_email: str,
      subject: str,
      body: str,
      attachments: list[str]
  ) -> dict: ...
  ```
* **Success Data Schema**:
  ```json
  {
    "delivery_status": "SENT",
    "message_id": "smtp-outbound-msg-882901",
    "sent_at": "2026-06-14T02:32:15Z"
  }
  ```

#### 2.8 `submit_web_application`
* **Signature**:
  ```python
  async def submit_web_application(
      application_url: str,
      profile_fields: dict,
      resume_path: str
  ) -> dict: ...
  ```
* **Success Data Schema**:
  ```json
  {
    "submission_status": "SUBMITTED",
    "confirmation_code": "CONF-GOOG-81920",
    "screenshot_proof_path": "/storage/proofs/usr_99_google_confirm.png"
  }
  ```

---

### Member 5 — Skill Gap & Mock Interviews (Branch: `feature/skillgap-interview-infra`)

#### 2.9 `generate_learning_roadmap`
* **Signature**:
  ```python
  async def generate_learning_roadmap(
      current_skills: list[str],
      target_job_skills: list[str]
  ) -> dict: ...
  ```
* **Success Data Schema**:
  ```json
  {
    "learning_path": [
      {
        "skill": "Kubernetes",
        "priority": "HIGH",
        "courses": [
          "Docker and Kubernetes: The Complete Guide (Udemy)",
          "CKAD Prep Course (Linux Foundation)"
        ]
      }
    ],
    "estimated_hours_to_complete": 40
  }
  ```

#### 2.10 `run_mock_interview`
* **Signature**:
  ```python
  async def run_mock_interview(
      job_description: str,
      question_index: int,
      user_response: str
  ) -> dict: ...
  ```
* **Success Data Schema**:
  ```json
  {
    "evaluation_score": 8.5,
    "feedback": "Clear explanation of container virtualization; structure your answer with the STAR method.",
    "suggested_answer": "A container shares the host OS kernel and virtualization occurs..."
  }
  ```
