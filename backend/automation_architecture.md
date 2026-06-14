# Automation Architecture — Member 4: Application Automation Agent
**Project:** AI Career Assistant Multi-Agent System 2026  
**Module Owner:** Member 4  
**Status:** Planning Phase  
**Last Updated:** 2026-06-12  

---

## 1. Executive Summary

The Application Automation Agent is the **execution layer** of the AI Career Assistant pipeline. It receives fully prepared application packages (resume, cover letter, job metadata) from upstream agents and executes the actual job application — either via email or web form automation — then records the outcome in the tracking system.

This module is critical: it is the final, externally-visible action the system performs. Every mistake here has a real-world consequence (duplicate applications, account bans, reputational risk). Therefore it must be **conservative, auditable, and retry-safe**.

---

## 2. System Position in the Full Pipeline

```
[User uploads CV]
       ↓
[Job Scraping Agent]         ← Member 1
       ↓
[Job Verification Agent]     ← Member 2
       ↓
[Job Matching Agent]         ← Member 3
       ↓
[Resume Optimization Agent]  ← Orchestrator
       ↓
[Cover Letter Agent]         ← Orchestrator
       ↓
════════════════════════════════════════════
  APPLICATION AUTOMATION AGENT (Member 4)
  ┌─────────────────────────────────────┐
  │  Input Receiver & Validator         │
  │         ↓                           │
  │  Route Selector                     │
  │   ├── Email Application System      │
  │   └── Web Form Automation Engine    │
  │         ↓                           │
  │  Confirmation Capture System        │
  │         ↓                           │
  │  Application Tracking System        │
  │         ↓                           │
  │  Guardrails & Rate Limiter          │
  └─────────────────────────────────────┘
════════════════════════════════════════════
       ↓
[Dashboard / Reporting Layer]
       ↓
[Orchestrator Feedback Loop]
```

---

## 3. Component Architecture

### 3.1 Top-Level Components

| Component | Responsibility | Technology |
|-----------|---------------|------------|
| `InputReceiver` | Receives job application package from orchestrator | FastAPI endpoint + Redis Queue |
| `RouteSelector` | Decides email vs. web form path per job | Rule engine (Python) |
| `EmailApplicationSystem` | Sends application emails via Gmail/SMTP | Gmail API / aiosmtplib |
| `WebFormAutomationEngine` | Fills and submits web-based application forms | Selenium 4 + ChromeDriver |
| `ConfirmationCaptureSystem` | Records proof of submission | PostgreSQL + File Storage |
| `ApplicationTrackingSystem` | Maintains canonical status of each application | PostgreSQL + FastAPI |
| `RetryOrchestrator` | Manages retry queues and backoff strategy | Celery + Redis |
| `GuardrailsManager` | Enforces rate limits, allow-lists, manual approval | Redis counters + middleware |
| `LoggingService` | Structured, Datadog-compatible logs | Python `structlog` |

### 3.2 Component Dependency Graph

```
InputReceiver
    │
    ├── GuardrailsManager  (check limits BEFORE doing anything)
    │
    ├── RouteSelector
    │       ├── EmailApplicationSystem
    │       │       ├── AttachmentHandler
    │       │       ├── GmailAPIClient / SMTPClient
    │       │       └── EmailConfirmationListener
    │       │
    │       └── WebFormAutomationEngine
    │               ├── BrowserSessionManager
    │               ├── FormFieldMapper
    │               ├── FileUploadHandler
    │               ├── CaptchaSolver (3rd party or manual)
    │               └── ScreenshotCapture
    │
    ├── ConfirmationCaptureSystem
    │       ├── SuccessMessageParser
    │       ├── ConfirmationIDExtractor
    │       └── EvidenceStore
    │
    ├── ApplicationTrackingSystem
    │       ├── StatusManager
    │       ├── HistoryLogger
    │       └── TrackingAPIRouter
    │
    └── RetryOrchestrator
            ├── ExponentialBackoffStrategy
            ├── DeadLetterQueue
            └── AlertDispatcher
```

---

## 4. Technology Decisions & Rationale

### 4.1 Backend Framework: FastAPI

- **Why:** Async-native, fast, automatic OpenAPI docs, easy dependency injection.
- **Alternative considered:** Flask — rejected (synchronous by default, less suited for async automation tasks).

### 4.2 Email: Gmail API (primary) + aiosmtplib (fallback)

- **Why Gmail API:** OAuth2, no plaintext passwords, supports read receipts, delivery status.
- **Why aiosmtplib fallback:** Covers non-Gmail SMTP cases and corporate email scenarios.
- **Decision:** Gmail API for google accounts; SMTP for others. Selected at runtime based on user's email provider.

### 4.3 Web Automation: Selenium 4 (with Playwright fallback option)

- **Why Selenium 4:** Mature ecosystem, CDP support, better Grid support, broad site compatibility.
- **Why not Puppeteer:** Node.js dependency increases tech-stack complexity; Python-first repo.
- **Playwright consideration:** May replace Selenium in v2 — better async, faster. Architecture is designed to swap this easily via an `AutomationDriver` abstraction layer.

### 4.4 Database: PostgreSQL

- **Why:** Relational integrity for tracking, JSONB for flexible metadata, good async support via `asyncpg`.

### 4.5 Queue & Task System: Redis + Celery

- **Why Redis:** Fast, in-memory, natural fit for rate counters and job queues.
- **Why Celery:** Mature, battle-tested for Python async tasks, supports retry policies, ETAs, and priority queues.

### 4.6 Logging: structlog + Datadog-compatible JSON

- Structured JSON output from day one.
- Every log line has: `trace_id`, `application_id`, `user_id`, `event`, `timestamp`, `severity`.

---

## 5. Data Flow: End-to-End

### 5.1 Happy Path — Email Application

```
1. Orchestrator → POST /applications/submit
   Payload: { job_id, user_id, resume_url, cover_letter_url, job_metadata }

2. InputReceiver validates payload schema (Pydantic)

3. GuardrailsManager:
   - Check daily limit for user_id (Redis counter)
   - Verify job_id is in verified_jobs table
   - Check if already applied (dedup check)
   - If manual_approval_required=True → create ApprovalRequest → WAIT

4. RouteSelector:
   - job_metadata.application_method == "email" → EmailApplicationSystem

5. EmailApplicationSystem:
   - Fetch resume file from S3/storage
   - Fetch cover letter from S3/storage
   - Compose email from template
   - Send via Gmail API
   - Log email message_id

6. ConfirmationCaptureSystem:
   - Poll/webhook for delivery confirmation
   - Parse any auto-reply for application ID
   - Save confirmation record

7. ApplicationTrackingSystem:
   - UPDATE applications SET status='applied', confirmation_id=..., applied_at=NOW()

8. ReturnResult → Orchestrator: { application_id, status: 'applied', confirmation }
```

### 5.2 Happy Path — Web Form Application

```
1. Same steps 1–4 as above, RouteSelector → WebFormAutomationEngine

2. BrowserSessionManager:
   - Launch headless Chrome with stealth profile
   - Navigate to job application URL

3. FormFieldMapper:
   - Load site-specific form schema (if cached)
   - OR dynamically analyze DOM fields
   - Map { first_name, email, phone, resume_file, cover_letter } → form fields

4. FileUploadHandler:
   - Download resume from storage to temp file
   - Trigger file upload input element

5. SubmitForm:
   - Click submit button
   - Wait for success indicator (URL change, success message, etc.)

6. ScreenshotCapture:
   - Capture full-page screenshot as submission proof
   - Upload to evidence store

7. ConfirmationCaptureSystem:
   - Parse success message / application ID from page
   - Record confirmation

8. ApplicationTrackingSystem: same as step 7 above
```

---

## 6. Integration Contracts with Other Agents

### 6.1 Input from Orchestrator / Upstream Agents

```json
{
  "application_id": "uuid4",
  "user_id": "uuid4",
  "job_id": "uuid4",
  "job_metadata": {
    "company_name": "string",
    "role_title": "string",
    "platform": "linkedin|email|company_site|indeed",
    "application_method": "email|web_form",
    "application_url": "string (nullable)",
    "contact_email": "string (nullable)",
    "deadline": "ISO8601 (nullable)"
  },
  "resume": {
    "version_id": "uuid4",
    "storage_url": "string",
    "filename": "string"
  },
  "cover_letter": {
    "version_id": "uuid4",
    "storage_url": "string",
    "content_text": "string"
  },
  "guardrails": {
    "manual_approval_required": false,
    "max_retries": 3,
    "priority": "normal|high"
  }
}
```

### 6.2 Output to Orchestrator / Dashboard

```json
{
  "application_id": "uuid4",
  "status": "applied|failed|pending_approval|duplicate|limit_exceeded",
  "submitted_at": "ISO8601",
  "confirmation": {
    "type": "email_ack|form_success|screenshot",
    "confirmation_id": "string (nullable)",
    "evidence_url": "string (nullable)"
  },
  "error": {
    "code": "string (nullable)",
    "message": "string (nullable)",
    "retry_count": 0
  },
  "tracking_url": "/api/v1/applications/{application_id}/status"
}
```

---

## 7. Deployment Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Docker Compose / K8s                   │
│                                                           │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  FastAPI     │  │  Celery      │  │  Selenium Grid │  │
│  │  (API Layer) │  │  Workers (N) │  │  (Chrome nodes)│  │
│  └──────┬──────┘  └──────┬───────┘  └───────┬────────┘  │
│         │                │                   │           │
│  ┌──────▼────────────────▼───────────────────▼────────┐  │
│  │              Redis (Queue + Rate Limiter)           │  │
│  └────────────────────────┬───────────────────────────┘  │
│                           │                              │
│  ┌────────────────────────▼───────────────────────────┐  │
│  │              PostgreSQL (Primary DB)               │  │
│  └────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │          S3-compatible Object Storage               │  │
│  │          (Resumes, Cover Letters, Screenshots)      │  │
│  └─────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

---

## 8. Scalability Considerations

| Concern | Strategy |
|---------|----------|
| High application volume | Celery horizontal scaling; add workers on demand |
| Multiple users simultaneously | Per-user Redis rate counters; isolated Celery queues |
| Web form concurrency | Selenium Grid with multiple Chrome nodes |
| DB query performance | Index on `user_id`, `status`, `applied_at`; JSONB indexing |
| Storage costs | Lifecycle policies on S3; compress screenshots (WebP) |
| Browser memory leaks | Worker recycling after N tasks; memory limits per container |

---

## 9. Open Questions (To Resolve Before Implementation)

1. **CAPTCHA strategy:** Use 2captcha/Anti-Captcha API (cost per solve ~$1/1000)? Or flag for manual review?
2. **Storage backend:** AWS S3, GCS, or MinIO (self-hosted)? Affects `storage_url` format.
3. **Manual approval flow:** Email the user? In-app notification? Webhook to orchestrator?
4. **Email read receipts:** Does the system need to detect if the hiring team opened the email?
5. **Multi-account support:** Can one user have multiple email accounts for sending?
6. **Credential storage:** HashiCorp Vault vs. AWS Secrets Manager vs. environment variables?

---

*Next Document: `application_flow.md` — detailed step-by-step flow diagrams*
