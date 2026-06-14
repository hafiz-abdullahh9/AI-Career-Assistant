# Retry & Error Strategy — Member 4: Application Automation Agent
**Project:** AI Career Assistant Multi-Agent System 2026  
**Module Owner:** Member 4  
**Status:** Planning Phase  
**Last Updated:** 2026-06-12  

---

## 1. Design Philosophy

The retry strategy follows these core principles:

1. **Fail Fast for non-recoverable errors** — Don't waste resources retrying what cannot succeed.
2. **Exponential backoff with jitter** — Prevent thundering herds; reduce load on external services.
3. **Max retry budget** — Always define a ceiling; never infinite retries.
4. **Dead Letter Queue** — Failed applications are never silently dropped; they go to DLQ for analysis.
5. **Idempotent operations** — Every retry is safe to execute multiple times without side effects.
6. **Observable retries** — Every retry attempt is logged, counted, and alertable.
7. **Human escalation path** — When automation fails, a human can always take over.

---

## 2. Error Classification

All errors are classified by recoverability:

### Class A — Transient (RETRY)
These errors are temporary and usually resolve on their own.

| Error | Example | Strategy |
|-------|---------|----------|
| Network timeout | Connection to SMTP server | Exponential backoff, max 3 retries |
| HTTP 503/504 | Job site temporarily down | Exponential backoff, max 3 retries |
| Browser crash | Chrome OOM or segfault | New session, max 2 retries |
| Element not found | DOM not fully loaded | Wait + re-scan, max 3 retries |
| File download failure | S3 rate limited | Backoff retry, max 3 retries |
| SMTP connection reset | Server closed connection early | Immediate retry once, then backoff |
| Redis connection error | Redis restart | Backoff retry, max 5 retries |

### Class B — Conditional (RETRY WITH DIFFERENT STRATEGY)
These need a changed approach, not just a time delay.

| Error | Example | Strategy |
|-------|---------|----------|
| CAPTCHA detected | reCAPTCHA on form page | Solve CAPTCHA then retry once |
| Form validation error | Required field not filled | Fix field mapping, then retry |
| Session expired | Cookie/auth timeout | Re-authenticate, then retry |
| Rate limit from site | "Too many requests" | Long delay (15 min), retry once |
| Wrong file type accepted | PDF not accepted, DOCX needed | Convert format, retry |

### Class C — Permanent (NO RETRY, ALERT)
These errors cannot be resolved by retrying.

| Error | Example | Strategy |
|-------|---------|----------|
| HTTP 404 | Job listing removed | Mark expired, notify orchestrator |
| HTTP 403 | Account banned from site | Escalate to human, stop |
| Duplicate application (site-side) | "You have already applied" | Mark duplicate, no retry |
| Invalid email address | contact@example.invalid | Mark failed, flag for correction |
| Invalid credentials | SMTP auth failure | Escalate, stop |
| Job deadline passed | Application window closed | Mark expired |
| Max retries exhausted | All attempts failed | DLQ, alert |

---

## 3. Retry Configuration Per Operation

```python
from celery.utils.time import get_exponential_backoff_interval

# Default retry policy applied to all automation tasks
DEFAULT_RETRY_POLICY = {
    "max_retries": 3,
    "retry_backoff": True,
    "retry_backoff_max": 300,   # Cap at 5 minutes
    "retry_jitter": True,       # Add random jitter to avoid thundering herd
}

# Per-operation overrides
RETRY_POLICIES = {
    "email_send": {
        "max_retries": 3,
        "countdown_schedule": [30, 120, 600],   # 30s, 2m, 10m
    },
    "web_form_submit": {
        "max_retries": 3,
        "countdown_schedule": [60, 300, 900],   # 1m, 5m, 15m
    },
    "file_download": {
        "max_retries": 5,
        "countdown_schedule": [5, 15, 30, 60, 120],
    },
    "captcha_solve": {
        "max_retries": 1,
        "countdown_schedule": [0],   # Retry immediately with new session
    },
    "confirmation_poll": {
        "max_retries": 6,            # Check every 20 min for 2 hours
        "countdown_schedule": [1200, 1200, 1200, 1200, 1200, 1200],
    },
}
```

---

## 4. Exponential Backoff with Jitter

### 4.1 Algorithm

```python
import random
import math

def calculate_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 300.0,
    jitter: bool = True
) -> float:
    """
    Exponential backoff with optional full jitter.
    
    attempt=1 → ~1s, attempt=2 → ~2s, attempt=3 → ~4s ... (capped at max_delay)
    With jitter: multiply by random(0.5, 1.5) to spread retries.
    """
    exponential = min(base_delay * (2 ** (attempt - 1)), max_delay)
    
    if jitter:
        # "Full jitter" — randomize within [0, exponential]
        return random.uniform(0, exponential)
    
    return exponential

# Example values:
# attempt=1: 0–1s    (avg 0.5s)
# attempt=2: 0–2s    (avg 1s)
# attempt=3: 0–4s    (avg 2s)
# attempt=4: 0–8s    (avg 4s)
# attempt=5: 0–16s   (avg 8s)
```

### 4.2 Celery Task with Retry

```python
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError

@shared_task(
    bind=True,
    max_retries=3,
    acks_late=True,                 # Acknowledge only after task completes
    reject_on_worker_lost=True,     # Re-queue if worker dies mid-task
)
def apply_via_email(self, application_id: str):
    try:
        result = EmailApplicationSystem().submit(application_id)
        return result
    except TransientError as exc:
        backoff = calculate_backoff(self.request.retries + 1)
        self.retry(exc=exc, countdown=backoff)
    except PermanentError as exc:
        # Do NOT retry — log and escalate
        log_permanent_failure(application_id, exc)
        update_application_status(application_id, "failed", reason=str(exc))
        send_alert(application_id, exc)
        raise exc
```

---

## 5. Dead Letter Queue (DLQ) Design

Applications that exhaust all retries land in the DLQ.

### 5.1 DLQ Flow

```
Max retries exhausted
         │
         ▼
┌─────────────────────────────────────────┐
│  DEAD LETTER QUEUE (Redis List)         │
│  Key: dlq:applications                  │
│  Entry: { application_id, error,        │
│           retry_count, failed_at,       │
│           original_payload }            │
└──────────────────┬──────────────────────┘
                   │
         ┌─────────▼──────────┐
         │  DLQ Processor     │  (runs every 30 min)
         │  (Celery Beat)     │
         └─────────┬──────────┘
                   │
         ┌─────────▼─────────────┐
         │  Analysis & Routing   │
         │  • Auto-requeue if    │
         │    conditions changed │
         │  • Alert engineer     │
         │  • Notify user        │
         └───────────────────────┘
```

### 5.2 DLQ Entry Schema

```python
class DLQEntry(BaseModel):
    application_id: str
    user_id: str
    error_class: str       # 'TransientError', 'PermanentError', etc.
    error_code: str
    error_message: str
    retry_count: int
    failed_at: datetime
    original_payload: dict
    last_attempt_trace_id: str
```

### 5.3 DLQ Requeue Conditions

The DLQ processor checks if a failed application can be re-attempted:

| Condition | Action |
|-----------|--------|
| Error was "site down" AND site is now reachable | Re-queue with fresh retry counter |
| Error was "daily limit" AND new day has started | Re-queue immediately |
| Error was "CAPTCHA" AND CAPTCHA service available | Re-queue |
| Error was permanent | Send user notification, mark `failed` permanently |
| Entry older than 7 days | Archive, close |

---

## 6. Circuit Breaker Pattern

For external services (SMTP, job sites, CAPTCHA APIs), implement a circuit breaker to prevent hammering a failing service.

### 6.1 States

```
CLOSED (normal) ──→ OPEN (failing) ──→ HALF-OPEN (testing)
     ↑                    │                    │
     └────────────────────┘←── Success ────────┘
```

### 6.2 Implementation

```python
class CircuitBreaker:
    """
    Per-domain circuit breaker stored in Redis.
    Keys:
        cb:{domain}:failures  → INTEGER (failure count in window)
        cb:{domain}:state     → 'closed' | 'open' | 'half_open'
        cb:{domain}:opened_at → timestamp
    """
    FAILURE_THRESHOLD = 5           # Failures before opening
    RECOVERY_TIMEOUT = 60           # Seconds before trying again
    SUCCESS_THRESHOLD = 2           # Successes in half-open to close
    WINDOW_SECONDS = 60             # Rolling window for failure count
    
    def is_open(self, domain: str) -> bool:
        state = redis.get(f"cb:{domain}:state")
        if state == "open":
            opened_at = float(redis.get(f"cb:{domain}:opened_at"))
            if time.time() - opened_at > self.RECOVERY_TIMEOUT:
                redis.set(f"cb:{domain}:state", "half_open")
                return False
            return True
        return False
    
    def record_failure(self, domain: str):
        pipe = redis.pipeline()
        pipe.incr(f"cb:{domain}:failures")
        pipe.expire(f"cb:{domain}:failures", self.WINDOW_SECONDS)
        failures, _ = pipe.execute()
        
        if failures >= self.FAILURE_THRESHOLD:
            redis.set(f"cb:{domain}:state", "open")
            redis.set(f"cb:{domain}:opened_at", time.time())
            send_alert(f"Circuit breaker OPEN for {domain}")
    
    def record_success(self, domain: str):
        state = redis.get(f"cb:{domain}:state")
        if state == "half_open":
            successes = redis.incr(f"cb:{domain}:successes")
            if successes >= self.SUCCESS_THRESHOLD:
                redis.set(f"cb:{domain}:state", "closed")
                redis.delete(f"cb:{domain}:failures", f"cb:{domain}:successes")
```

---

## 7. Error Handling Per Module

### 7.1 Email Application System

```
Error Handling Decision Tree for Email Sending:

SMTP_TIMEOUT
  → Retry with exponential backoff (max 3)
  → After max: DLQ + alert

SMTP_AUTH_FAILURE
  → DO NOT retry (credentials invalid)
  → Alert user: "Email credentials need update"
  → Mark application: 'failed'

SMTP_RECIPIENT_REJECTED
  → Check if contact email is correct
  → Mark application: 'failed', reason: 'invalid_recipient'

ATTACHMENT_TOO_LARGE
  → Compress resume PDF (target < 5MB)
  → Retry once
  → If still too large: send without attachment, note in body

GMAIL_API_QUOTA_EXCEEDED
  → Switch to SMTP fallback
  → Retry

GMAIL_API_TOKEN_EXPIRED
  → Refresh OAuth token
  → Retry
```

### 7.2 Web Form Automation Engine

```
Error Handling Decision Tree for Web Form:

PAGE_LOAD_TIMEOUT (30s)
  → Retry page load once (60s timeout)
  → If still fails: check HTTP status → site down → DLQ

ELEMENT_NOT_FOUND
  → Wait 5s for dynamic content
  → Retry find (max 3)
  → If not found: log "field_missing:{field_name}", skip required fields check

STALE_ELEMENT_REFERENCE
  → Re-find element
  → Retry interaction

FILE_UPLOAD_FAILED
  → Verify file exists locally
  → Retry with explicit wait for file input
  → If persistent: try alternative upload method (drag-and-drop simulation)

SUBMIT_NO_CONFIRMATION (timeout)
  → Check if URL changed (may have redirected silently)
  → Check for any success text in DOM
  → Take screenshot regardless
  → If truly ambiguous: mark status as 'applied (unconfirmed)'

BROWSER_CRASH
  → Kill session, create new session
  → Retry full flow from W1 (max 2)

IP_BLOCKED / 403_FORBIDDEN
  → DO NOT retry (would worsen the block)
  → Alert, mark as 'failed', flag domain in circuit breaker

CAPTCHA
  → Attempt CAPTCHA solve
  → Retry submission
  → If CAPTCHA solve fails: status = 'captcha_required', notify user
```

---

## 8. Alerting Strategy

### 8.1 Alert Levels

| Level | Examples | Channel | Response Time |
|-------|---------|---------|---------------|
| **CRITICAL** | Credential failure, IP ban, DB down | PagerDuty + Slack | 15 min |
| **HIGH** | Circuit breaker open, DLQ spike | Slack #alerts | 1 hour |
| **MEDIUM** | Retry count > 2 on any application | Slack #warnings | 4 hours |
| **LOW** | CAPTCHA encountered, field not found | Log only | Next business day |

### 8.2 Alert Schema

```python
class Alert(BaseModel):
    level: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    title: str
    application_id: Optional[str]
    user_id: Optional[str]
    error_code: str
    error_message: str
    context: dict
    timestamp: datetime
    suggested_action: str
```

### 8.3 User Notifications

When an application fails permanently, the user receives:

```
Subject: ❌ Application to {company} could not be submitted

We attempted to submit your application to {company} for the role 
of {role} {retry_count} times but were unable to complete the submission.

Reason: {human_readable_error}

What you can do:
1. Apply manually: {application_url}
2. Update your credentials: {settings_url}
3. Contact support: {support_url}

Your prepared resume and cover letter are saved and ready to use.
```

---

## 9. Failure Metrics & SLOs

Track and alert on these metrics:

| Metric | Target SLO | Alert Threshold |
|--------|-----------|----------------|
| Email application success rate | ≥ 95% | < 90% |
| Web form success rate | ≥ 85% | < 75% |
| Retry rate | < 15% of applications | > 25% |
| P95 email send latency | < 10 seconds | > 30 seconds |
| P95 form submit latency | < 120 seconds | > 300 seconds |
| DLQ size | < 10 items | > 50 items |
| CAPTCHA encounter rate | < 20% | > 40% |
| Daily limit hit rate | < 5% of users | > 15% of users |

---

## 10. Retry Context Preservation

**Design Philosophy** – All retry attempts must retain the original execution context to ensure idempotency and accurate audit trails. Context includes correlation IDs, task IDs, user/session ownership, and any temporary state required for deterministic re‑execution.

**Operational Rules**
- Preserve `X‑Correlation‑Id` and `X‑Task‑Id` headers across retries.
- Store transient payload fragments in Redis with a TTL of 15 minutes; re‑hydrate on retry.
- Ensure any side‑effects (e.g., file uploads) are performed **once** and guarded by a deduplication key.

**Governance Implications** – Guarantees replay integrity and prevents duplicate financial or compliance actions.

**Concrete Retry Behavior** – On each retry, the system checks for an existing context record; if found, it re‑uses the same external identifiers.

**Failure Examples** – Lost correlation ID leads to orphaned audit entries.

**Escalation Behavior** – If context cannot be reconstructed after three attempts, route to DLQ with `context_missing` flag.

**Observability Expectations** – Log `context_restored: true/false` and the TTL remaining.

---

## 11. Retry Classification Matrix

> **[!WARNING]** Duplicate submission prevention – retries must never cause a second real‑world action.

| Error Class | Example | Retryable | Max Attempts | Backoff Strategy | Escalation Path | Governance Impact |
|-------------|---------|-----------|--------------|------------------|-----------------|-------------------|
| Transient – Network | HTTP 502, SMTP timeout | Yes | 5 | Exponential + jitter | DLQ after max | Minimal – expected to recover |
| Permanent – Credential | SMTP auth failure | No | 0 | N/A | Immediate alert | High – requires human fix |
| Governance‑Denied | Approval revoked mid‑run | No | 0 | N/A | Stop, log audit | Critical – compliance breach |
| Quota Exceeded | API rate limit hit | Yes (after back‑off) | 3 | Fixed delay (30 s) | DLQ if persists | Medium – resource caps |
| Selenium Stale Element | `StaleElementReferenceException` | Yes | 3 | Linear (10 s) | DLQ if persists | Low – UI fragility |
| Duplicate Submission | Site returns "already applied" | No | 0 | N/A | Mark duplicate, no retry | High – audit integrity |

*Component‑specific subsections follow for Selenium, SMTP, and Redis‑lock handling.*

---

## 12. Replay‑Safe Retries

**Design Philosophy** – Retries must be safe to replay without creating duplicate external actions.

### Confirmation‑State Validation
- Before any retry that performs a submission, verify the existence of a successful‑submit telemetry record (e.g., `submission_id` stored in Redis).
- Check that the `confirmation_id` from the previous attempt matches the expected value.
- Only proceed if **no** confirmation record is present.

**Operational Rules**
- Perform an atomic `GETSET` on a Redis key `retry:{application_id}` to claim ownership.
- If the key already indicates `completed`, skip the retry.

**Governance Implications** – Prevents duplicate job applications, financial transactions, or legal filings.

**Concrete Retry Behavior** – On a Selenium form submission, the engine first queries `submission_status:{app_id}`; if `status == "submitted"` the retry is aborted and the run is marked as `duplicate_skip`.

**Failure Examples** – Duplicate email sent because confirmation check was omitted.

**Escalation Behavior** – When duplicate detection fires, route to DLQ with `duplicate_submission` flag and notify operator.

**Observability Expectations** – Emit `duplicate_check_passed: bool` and `retry_skipped: bool` metrics.

---

## 13. Dead Letter Queue Recovery Workflow

> **[!WARNING]** DLQ quarantine requirements – entries must be isolated until a human reviewer validates them.

**Workflow Steps**
1. **DLQ Ingestion** – Failed tasks are pushed to Redis list `dlq:{service}` with full payload and error metadata.
2. **Automated Triage** – A periodic Celery beat job scans entries and applies `requeue_conditions` (e.g., site now reachable, daily limit reset).
3. **Operator Assignment** – Un‑requeueable entries are assigned to an on‑call operator via the HITL escalation queue.
4. **Manual Recovery** – Operator can:
   - Edit payload and re‑inject to the original queue.
   - Mark as `discarded` with audit note.
5. **Audit Correlation** – Each DLQ entry stores `last_attempt_trace_id` to link back to the original telemetry trace.
6. **Quarantine Labeling** – Entries carry a `quarantine_reason` field for compliance reporting.
7. **Re‑queue** – On successful manual fix, the entry is removed from DLQ and re‑published with a reset `retry_count`.

**Table – DLQ Entry Fields**
| Field | Description |
|-------|-------------|
| application_id | Primary identifier |
| error_class | Transient / Permanent |
| retry_count | Number of attempts made |
| failed_at | Timestamp of final failure |
| original_payload | Full request data |
| last_attempt_trace_id | Link to observability trace |
| quarantine_reason | Reason for isolation |
| operator_id | Assigned human reviewer |

---

## 14. Retry Budget Enforcement

**Design Philosophy** – Limit the total amount of retry work to protect system capacity and avoid cascading failures.

**Operational Matrices**
| Component | Failure Type | Action | Retry Delay | DLQ Eligible | Human Escalation |
|-----------|--------------|--------|------------|--------------|-------------------|
| Email Service | Transient | Retry (exp backoff) | 30 s‑10 min | Yes after 5 attempts | No |
| Web Form Engine | Selenium errors | Retry (linear) | 10‑60 s | Yes after 3 attempts | Yes (if duplicate risk) |
| Scheduler | quota exceed | Back‑off then retry | 1‑15 min | No | Yes |
| Global | Total retries > 10 % of workload | Pause new retries | N/A | N/A | Alert ops |

**Enforcement Mechanism** – Celery task decorator `@retry_budget(limit=0.1)` checks the rolling window of retry counts stored in Redis.

---

## 15. Structured Retry Telemetry

> **[!WARNING]** Audit preservation – every retry must be linked to the original audit record.

**Mandatory Log Fields**
| Field | Description |
|-------|-------------|
| retry_count | Current attempt number |
| correlation_id | End‑to‑end trace identifier |
| task_id | Celery task UUID |
| application_id | Business‑level identifier |
| component | `email`, `web_form`, `selenium`, etc. |
| adapter | Underlying library (SMTP, ChromeDriver, etc.) |
| previous_error | Serialized exception message |
| escalation_status | `none`, `dlq`, `human_assigned` |
| latency_ms | Time spent in this attempt |
| timestamp | ISO‑8601 time |

**Implementation** – All retry wrappers call `log_retry_event(**fields)` which forwards to the OpenTelemetry collector and also writes to the central `retry_audit` table.

---

## 16. Governance‑Aware Retry Blocking

**Design Philosophy** – Governance rules dominate any retry logic; when a governance signal is active, the system must halt.

**Blocking Conditions** (must stop immediately):
- Approval revoked
- Domain blocked
- Emergency pause active
- Quota exceeded
- Execution cancelled
- HITL escalation triggered
- **Execution Ownership Validation** (new subsection below)

### Execution Ownership Validation
Before any retry the platform verifies:
1. **Orchestration Ownership** – The Celery task ID matches the current workflow owner stored in Redis (`owner:{workflow_id}`).
2. **Active Lock Ownership** – The Redis lock (`lock:{resource}`) is held by the same process attempting the retry.
3. **Session Ownership** – For Selenium actions, the browser session identifier must be the same as the original run and not expired.

If any check fails, the retry is aborted and the event is logged as `ownership_mismatch` and sent to the DLQ.

> **[!WARNING]** Duplicate submission prevention – ensure the above checks are performed before any external call.

> **[!WARNING]** Governance stop conditions – every retry wrapper must query the `governance_state` service; if `stop == true` abort immediately.

---

## 17. Poison Message Detection

**Design Philosophy** – Identify messages that are permanently unrecoverable to avoid endless retry loops.

| Symptom | Detection Heuristic | Action |
|---------|----------------------|--------|
| Malformed payload (JSON schema error) | Schema validation fails on first attempt | Move to DLQ with `poison` flag |
| Repeated `MaximumRetryExceeded` after max attempts | Retry count > configured max AND error unchanged | Alert ops, quarantine |
| Cryptographic verification failure | Signature check fails | Discard, log security alert |
| Persistent `StaleElementReference` after session recreation | Same element fails > 3 sessions | Flag as poison, require manual review |

**Recovery** – Operators can inspect the payload, correct data, and re‑inject via the HITL queue.

---

## 18. Distributed Lock Awareness

**Design Philosophy** – Retries must respect existing distributed locks to avoid race conditions.

**Operational Rules**
- Acquire a Redis lock `retry:{resource}` with a TTL of 30 seconds before retrying a critical section.
- If lock acquisition fails, back‑off and retry lock acquisition (max 3 attempts).
- Release lock immediately after successful operation.

**Table – Lock‑Related Failure Handling**
| Failure | Immediate Action | Subsequent Retry |
|---------|------------------|-----------------|
| Lock contention | Back‑off 5 s, retry lock acquire | Up to 3 times, then DLQ |
| Lock timeout (expired) | Re‑acquire, verify resource state | Proceed if state valid |
| Lost lock during operation | Abort, mark `lock_lost`, DLQ |

> **[!WARNING]** Audit preservation – lock‑related failures must be recorded in the audit trail to guarantee deterministic state.

---

*Next Document: `security_guardrails.md` — security and access control design*
