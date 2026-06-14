# Runtime Flow — Application Automation Agent

## Overview

This document traces the **exact execution path** of every application submission
from the initial HTTP request through to final database confirmation.

---

## 1. Entry Point — HTTP Request

```
Client / Orchestrator
       │
       │  POST /api/v1/applications/submit
       │  Headers: Content-Type: application/json
       │           X-Request-ID: <trace-id>       ← optional
       │
       ▼
RequestIDMiddleware
  ├── reads X-Request-ID or generates uuid4()
  ├── binds trace_id to structlog context
  └── attaches trace_id to request.state
```

**At this point:** every log line emitted during this request will carry `trace_id`.

---

## 2. Request Validation — FastAPI / Pydantic

```
       │
       ▼
Pydantic v2 schema validation (ApplicationSubmitRequest)
  ├── user_id must be a valid UUID
  ├── job_id must be a valid UUID
  ├── job_metadata.application_method must be a valid enum
  ├── if method == "email"    → contact_email required
  ├── if method == "web_form" → application_url required
  ├── resume.filename must end in .pdf
  ├── resume.filename must not contain path traversal characters
  └── resume.storage_url must use HTTPS
       │
       │  On validation failure → HTTP 422 (FastAPI default)
       │  On success → route handler receives typed request object
```

---

## 3. Route Handler — Thin Orchestration

```
       │
       ▼
submit_application() in app/api/v1/applications.py
  ├── creates ApplicationService(db=session, redis=client)
  ├── calls service.check_rate_limit()
  ├── calls service.check_duplicate()
  ├── calls service.create_application()
  ├── builds TaskPayload (JSON-serializable)
  ├── calls process_application.apply_async()
  └── calls service.attach_task_id()
       │
       │  Returns HTTP 202 with {application_id, status: "queued", tracking_url}
```

**Rule:** The route handler contains ZERO business logic. It only calls the service
and returns a response. All decisions happen in ApplicationService.

---

## 4. Guardrail Layer — ApplicationService

```
service.check_rate_limit(user_id)
  ├── Redis GET  key="rate:daily:{user_id}:{YYYYMMDD}"
  ├── if value >= limit → raise RateLimitExceededError (→ HTTP 429)
  └── if value < limit  → pass

service.check_duplicate(user_id, job_id)
  ├── Redis EXISTS key="dedup:applied:{user_id}:{job_id}"
  ├── if key exists → raise DuplicateApplicationError (→ HTTP 409)
  ├── else → DB query: SELECT WHERE user_id=? AND job_id=? AND deleted_at IS NULL
  └── if row exists → raise DuplicateApplicationError (→ HTTP 409)
```

---

## 5. Application Record Creation — Database

```
service.create_application(request)
  ├── constructs Application ORM object (status="queued")
  ├── session.add(application)
  ├── session.flush()        ← generates application_id (server-side UUID)
  ├── _append_status_history(from=None, to="queued")
  └── _append_log(event="application.created")
       │
       │  Session commits when the context manager exits (get_db_session)
```

---

## 6. Task Enqueueing — Celery

```
process_application.apply_async(
    args=[payload_dict],        ← JSON-serializable TaskPayload
    queue="normal" or "high",   ← based on guardrails.priority
    task_id=f"apply-{app_id}",  ← deterministic, prevents duplicate tasks
)
  ├── Serialized to JSON
  └── Published to Redis queue: "normal" or "high"

service.attach_task_id(app_id, task.id)
  └── UPDATE applications SET celery_task_id=? WHERE application_id=?
```

---

## 7. Worker Processing — Celery Task

```
Celery worker picks up task from Redis queue
       │
       ▼
process_application(payload_dict)    [sync wrapper]
  └── run_async(_process_application_async(payload))
           │
           ▼
   bind structlog context: {application_id, user_id, method}
           │
           ▼
   STEP 1: transition_status(QUEUED → PROCESSING)
     ├── validates transition is legal
     ├── writes to application_status_history
     └── writes to application_logs
           │
           ▼
   STEP 2: _execute_application(payload)
     ├── if method == "email"    → _fake_process_email()   ← Phase A: STUB
     ├── if method == "web_form" → _fake_process_webform() ← Phase A: STUB
     └── returns {success: bool, confirmation_id: str, message: str}
           │
           ▼
   STEP 3: if success:
     ├── transition_status(PROCESSING → APPLIED)
     ├── set_confirmation(confirmation_id)
     ├── mark_daily_counter(user_id)   ← Redis INCR
     └── mark_dedup_cache(user_id, job_id) ← Redis SET 90d TTL
           │
           ▼
   STEP 3: if failed:
     └── transition_status(PROCESSING → FAILED)
```

---

## 8. Retry Flow — On Failure

```
process_application task raises Exception
  │
  ├── self.request.retries < self.max_retries (3)?
  │     YES: self.retry(exc=exc, countdown=60 * 2^retry_count)
  │           → Task re-queued with exponential delay
  │           → Delays: 60s → 120s → 240s
  │
  └── NO (max retries exhausted):
        _mark_permanently_failed(application_id, error_str)
          └── transition_status(→ FAILED, reason="Max retries exhausted")
```

---

## 9. Status Query Flow

```
GET /api/v1/applications/{id}/status
  │
  ▼
service.get_application(application_id)
  ├── SELECT * FROM applications WHERE application_id=? AND deleted_at IS NULL
  ├── if not found → raise NotFoundError (→ HTTP 404)
  └── returns Application ORM → serialized to ApplicationResponse
```

---

## 10. Error Response Flow

```
Any AppBaseError raised anywhere in the pipeline
  │
  ▼
app_error_handler() in main.py
  ├── logs: level=WARNING, error_code, message, path
  └── returns JSON:
      {
        "success": false,
        "error": {
          "code": "RATE_LIMIT_EXCEEDED",
          "message": "...",
          "details": {...}
        },
        "meta": {"request_id": "<trace-id>"}
      }

Any unexpected Exception (bug):
  └── unhandled_error_handler()
      ├── logs: level=ERROR, exc_info=True (full traceback)
      └── returns generic 500 (no internal details exposed)
```

---

## Sequence Diagram (Condensed)

```
Client      FastAPI      Service      Redis       DB        Celery
  │            │            │           │          │           │
  │──POST──►   │            │           │          │           │
  │            │──validate──│           │          │           │
  │            │──guard─────►──GET key──│          │           │
  │            │            │◄──miss────│          │           │
  │            │──guard──────────────────►─SELECT──│           │
  │            │            │◄────────────────empty│           │
  │            │──create─────────────────►─INSERT──│           │
  │            │            │◄────────────────uuid─│           │
  │            │──enqueue───────────────────────────►─publish──│
  │◄──202──────│            │           │          │           │
  │            │            │           │          │           │
  (async - Celery worker processes)                │           │
  │            │            │           │          │◄──PROC────│
  │            │            │           │          │───done────►
  │            │            │           │◄──INCR───────────────│
  │            │            │           │◄──SET key────────────│
  │            │            │           │          │───UPDATE──►
  │            │            │           │          │           │
  │──GET───►   │            │           │          │           │
  │            │──fetch──────────────────►─SELECT──│           │
  │◄──200──────│ {status:"applied"}     │          │           │
```
