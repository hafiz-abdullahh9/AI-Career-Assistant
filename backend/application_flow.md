# Application Flow — Member 4: Application Automation Agent
**Project:** AI Career Assistant Multi-Agent System 2026  
**Module Owner:** Member 4  
**Status:** Planning Phase  
**Last Updated:** 2026-06-12  

---

## 1. Overview

This document details every step of the application submission flow from the moment this agent receives a job application package to the moment it reports back to the orchestrator. It covers both the **Email Path** and the **Web Form Path**, including all branching, error, and retry conditions.

---

## 2. Master Application Flow

```
╔═══════════════════════════════════════════════╗
║        ORCHESTRATOR SENDS APPLICATION         ║
║   POST /api/v1/applications/submit            ║
╚═══════════════════════════════════════════════╝
                      │
                      ▼
┌──────────────────────────────────────────────┐
│  STEP 1: INPUT VALIDATION                    │
│  • Validate JSON schema (Pydantic)           │
│  • Verify all required fields present        │
│  • Validate file URLs are accessible         │
│  → FAIL: Return 422 Unprocessable Entity     │
└──────────────────────┬───────────────────────┘
                       │ PASS
                       ▼
┌──────────────────────────────────────────────┐
│  STEP 2: GUARDRAILS CHECK                    │
│  • Check daily application limit (Redis)     │
│  • Check job is verified (DB lookup)         │
│  • Check for duplicate application (DB)      │
│  • Check if job deadline has passed          │
│  → LIMIT_EXCEEDED: Return 429, log, stop     │
│  → UNVERIFIED: Return 403, log, stop         │
│  → DUPLICATE: Return 409, log, stop          │
│  → EXPIRED: Return 410, log, stop            │
└──────────────────────┬───────────────────────┘
                       │ ALL PASS
                       ▼
┌──────────────────────────────────────────────┐
│  STEP 3: MANUAL APPROVAL CHECK               │
│  • If manual_approval_required == true:      │
│    - Create approval_request record          │
│    - Notify user (email/webhook)             │
│    - Set application status = 'pending'      │
│    - Return 202 Accepted + tracking URL      │
│    - WAIT for /approve or /reject callback   │
│  • If false: continue immediately            │
└──────────────────────┬───────────────────────┘
                       │ APPROVED or AUTO
                       ▼
┌──────────────────────────────────────────────┐
│  STEP 4: CREATE APPLICATION RECORD           │
│  • INSERT into applications table            │
│  • status = 'queued'                         │
│  • Enqueue Celery task with application_id   │
│  • Return 202 + { application_id, status }   │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│  STEP 5: ROUTE SELECTION                     │
│  • application_method == "email" ?           │
│    → Email Path                              │
│  • application_method == "web_form" ?        │
│    → Web Form Path                           │
│  • UNKNOWN: log error, status = 'failed'     │
└─────────┬────────────────────────┬───────────┘
          │ EMAIL                  │ WEB FORM
          ▼                        ▼
  [See Section 3]          [See Section 4]
```

---

## 3. Email Application Path — Detailed Flow

```
┌──────────────────────────────────────────────────────────┐
│  EMAIL PATH — START                                       │
│  Triggered by Celery task: apply_via_email(app_id)       │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  E1: FETCH ASSETS                                        │
│  • Download resume from storage_url → temp file          │
│  • Download cover_letter from storage_url → temp file    │
│  • Validate file sizes (< 10MB per attachment)           │
│  • → FAIL: retry up to 3x, then status = 'asset_error'  │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  E2: COMPOSE EMAIL                                       │
│  • Load email template for platform/company              │
│  • Inject: user name, role, company, personal statement  │
│  • Attach: resume file (PDF)                             │
│  • Attach: cover letter file (PDF) OR inline in body     │
│  • Set Reply-To: user's email                            │
│  • Set Subject: "Application for {role} — {user_name}"  │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  E3: SELECT SEND METHOD                                  │
│  • User email domain == gmail.com / workspace?           │
│    → Gmail API (OAuth2)                                  │
│  • Otherwise?                                            │
│    → SMTP via aiosmtplib                                 │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  E4: SEND EMAIL                                          │
│  • Send with timeout = 30s                               │
│  • Capture: message_id, sent_at timestamp                │
│  • → SMTP_ERROR / API_ERROR:                             │
│      Exponential backoff retry (1s, 5s, 30s)            │
│      Max retries: 3                                      │
│      On max retries: status = 'failed', alert            │
└──────────────────────────┬───────────────────────────────┘
                           │ SUCCESS
                           ▼
┌──────────────────────────────────────────────────────────┐
│  E5: LOG SEND SUCCESS                                    │
│  • Log: { app_id, message_id, recipient, sent_at }       │
│  • UPDATE applications SET status = 'applied',           │
│    applied_at = NOW(), email_message_id = message_id     │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  E6: CONFIRMATION CAPTURE (async, non-blocking)          │
│  • Schedule: check inbox for auto-reply within 2 hours   │
│  • If auto-reply found:                                  │
│    - Extract application ID / reference number           │
│    - UPDATE confirmation_id in applications table        │
│    - Store raw email in confirmations table              │
│  • If no reply: confirmation remains NULL (acceptable)   │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  E7: CLEANUP & NOTIFY ORCHESTRATOR                       │
│  • Delete temp files                                     │
│  • POST orchestrator webhook with result                 │
│  • Increment user's daily counter in Redis               │
└──────────────────────────────────────────────────────────┘
```

---

## 4. Web Form Application Path — Detailed Flow

```
┌──────────────────────────────────────────────────────────┐
│  WEB FORM PATH — START                                   │
│  Triggered by Celery task: apply_via_webform(app_id)     │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  W1: PREPARE BROWSER SESSION                             │
│  • Request Chrome node from Selenium Grid                │
│  • Apply stealth options (disable webdriver flags)       │
│  • Set realistic User-Agent, viewport (1920x1080)        │
│  • Set implicit wait = 10s, page load timeout = 60s      │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  W2: NAVIGATE TO APPLICATION URL                         │
│  • driver.get(application_url)                           │
│  • Wait for DOM ready state == "complete"                │
│  • → TIMEOUT: retry navigation, max 2x                   │
│  • → HTTP 4xx/5xx: status = 'failed', alert              │
│  • Take "arrival" screenshot                             │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  W3: CHECK FOR CAPTCHA                                   │
│  • Scan DOM for: reCAPTCHA iframe, hCaptcha widget       │
│  • If CAPTCHA detected:                                  │
│    → Strategy A: Send to 2captcha API (auto-solve)       │
│    → Strategy B: Flag for manual review                  │
│      status = 'captcha_required'                         │
│      notify user with form URL                           │
│  • If no CAPTCHA: continue                               │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  W4: FORM DISCOVERY & MAPPING                            │
│  • Check form_schemas cache (Redis) for this domain      │
│  • If cached schema: load and verify fields exist in DOM │
│  • If no cache: dynamically analyze form fields:         │
│    - Find all input, select, textarea elements           │
│    - Infer field type from: name attr, id, label, aria   │
│    - Map to standard field names:                        │
│      { first_name, last_name, email, phone,              │
│        linkedin_url, resume_file, cover_letter,          │
│        years_experience, work_authorization }            │
│  • Save discovered schema to Redis cache (TTL: 7 days)   │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  W5: FILL FORM FIELDS                                    │
│  For each mapped field:                                  │
│  • text/email/tel → clear() + send_keys(value)          │
│  • select → Select(element).select_by_visible_text()    │
│  • checkbox → click() if not already checked            │
│  • file input → send_keys(local_temp_file_path)          │
│  Human-like delays: random 0.1–0.5s between fields      │
│  Scroll field into view before interacting               │
│  → FIELD_NOT_FOUND: log warning, skip field              │
│  → FIELD_ERROR: retry 2x, then log and continue         │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  W6: PRE-SUBMIT REVIEW                                   │
│  • Take "pre-submit" screenshot                          │
│  • Validate required fields are filled                   │
│  • Log field completion report                           │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  W7: SUBMIT FORM                                         │
│  • Find submit button (by type=submit, aria, text)       │
│  • scroll_to_element(submit_btn)                         │
│  • click(submit_btn)                                     │
│  • Wait for one of:                                      │
│    - URL change (redirect to confirmation page)          │
│    - Success message element appears                     │
│    - "Thank you" or "Application received" text          │
│  • Timeout: 30 seconds                                   │
│  → TIMEOUT: retry submit once, then status = 'failed'    │
└──────────────────────────┬───────────────────────────────┘
                           │ SUCCESS INDICATOR FOUND
                           ▼
┌──────────────────────────────────────────────────────────┐
│  W8: CAPTURE CONFIRMATION                                │
│  • Take full-page "confirmation" screenshot              │
│  • Extract text: application ID, reference number        │
│  • Extract URL of confirmation page                      │
│  • Upload screenshot to evidence store (S3)              │
│  • INSERT into confirmations table                       │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  W9: UPDATE TRACKING & CLEANUP                           │
│  • UPDATE applications SET                               │
│    status='applied', applied_at=NOW(),                   │
│    confirmation_id=..., screenshot_url=...               │
│  • Close browser session (return to Grid pool)           │
│  • Delete temp resume/cover_letter files                 │
│  • Increment daily counter in Redis                      │
│  • POST result to orchestrator webhook                   │
└──────────────────────────────────────────────────────────┘
```

---

## 5. Error State Transition Map

```
                    ┌──────────┐
                    │  QUEUED  │
                    └────┬─────┘
                         │
              ┌──────────▼──────────┐
              │     PROCESSING      │
              └──┬──────────────┬───┘
                 │              │
        ┌────────▼───┐    ┌─────▼──────┐
        │  APPLIED   │    │   FAILED   │──→ Dead Letter Queue
        └────────────┘    └─────┬──────┘      → Alert
                                │
                    ┌───────────▼───────────┐
                    │  RETRY_SCHEDULED      │──→ Retry (max 3)
                    └───────────────────────┘


Special States:
  PENDING_APPROVAL  → waiting for user manual approval
  CAPTCHA_REQUIRED  → waiting for manual CAPTCHA solve
  DUPLICATE         → already applied, no action taken
  LIMIT_EXCEEDED    → daily cap hit, deferred to next day
  ASSET_ERROR       → could not download resume/cover letter
```

---

## 6. Asynchronous vs. Synchronous Operations

| Operation | Mode | Rationale |
|-----------|------|-----------|
| Input validation | Sync | Immediate feedback |
| Guardrails check | Sync | Immediate feedback |
| Application record creation | Sync | Must exist before task queues |
| Email sending | Async (Celery) | Can take seconds to minutes |
| Web form filling | Async (Celery) | Browser session = expensive |
| Confirmation email poll | Async (Celery, scheduled) | Non-blocking, hours delay |
| Screenshot upload to S3 | Async | Non-critical path |
| Orchestrator webhook notification | Async | Post-completion, non-blocking |

---

## 7. Idempotency Design

Every application submission is keyed by `application_id` (UUID). The system guarantees:

1. **Dedup check at input:** If `application_id` already exists with status ≠ 'failed', return existing result.
2. **Celery task dedup:** Task ID = `apply_{application_id}`. Celery prevents re-enqueueing same task ID.
3. **DB unique constraint:** `UNIQUE(user_id, job_id)` prevents double-apply at DB level.
4. **Email dedup:** Check sent_emails table for `(user_id, job_id)` before sending.

---

## 8. Notification Events (to Orchestrator/Dashboard)

| Event | Trigger | Payload |
|-------|---------|---------|
| `application.queued` | Application record created | `{ app_id, user_id, job_id }` |
| `application.processing` | Celery task starts | `{ app_id, method }` |
| `application.applied` | Successful submission | Full result object |
| `application.failed` | Max retries exceeded | `{ app_id, error, retry_count }` |
| `application.pending_approval` | Manual review required | `{ app_id, approval_url }` |
| `application.captcha_blocked` | CAPTCHA detected | `{ app_id, form_url }` |
| `confirmation.captured` | Confirmation data found | `{ app_id, confirmation_id }` |

---

*Next Document: `selenium_strategy.md` — browser automation technical strategy*
