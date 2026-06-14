# Failure Recovery — Resilience Patterns

## Overview

This document describes every failure scenario the system can encounter and
exactly how each one is detected, handled, and recovered from.

---

## Failure Classification

| Class | Definition | Action |
|-------|-----------|--------|
| **A — Transient** | Temporary, likely to succeed on retry | Retry with backoff |
| **B — Recoverable** | Needs external intervention, then retry | Alert + retry later |
| **C — Permanent** | Will never succeed for this request | Fail, no retry |

---

## Scenario A: Celery Worker Crash (TEST A)

**What happens:** The worker process is killed while processing a task.

**Why this is safe:**
- `acks_late=True` is set on all tasks.
- This means the task message is only acknowledged from Redis **after** the
  task function returns successfully, not when it starts.
- If the worker crashes mid-execution, the message remains in Redis and
  another worker will pick it up.

```
Redis queue: [task-message]
     │
Worker A picks up → starts processing → CRASH (sigkill)
     │
     │  Message NOT acknowledged (acks_late=True)
     │
Worker B (or restarted A) picks up the SAME message
     └── Resumes from the beginning
```

**Caveat:** If the task was at step "PROCESSING" when the crash happened,
the DB still shows "processing". The cleanup Beat task detects this:

```python
# cleanup_stale_applications (runs every 30 minutes):
SELECT * FROM applications
WHERE status = 'processing'
  AND updated_at < NOW() - INTERVAL '15 minutes'

→ transitions each to FAILED with reason "Cleaned up: stuck in PROCESSING"
```

**To test:**
```bash
docker kill automation_worker   # Kill worker mid-task
docker-compose start worker     # Restart worker
# Task should complete on the restarted worker
```

---

## Scenario B: Redis Connection Failure (TEST B)

**What happens:** The Redis container becomes unavailable.

**Impact matrix:**

| Component | Behavior |
|-----------|----------|
| POST /submit | **Fails** — guardrail checks (rate limit, dedup) require Redis |
| GET /status | **Succeeds** — status queries only use the DB |
| Celery broker | **Fails** — Celery cannot publish/consume tasks |
| Celery result | **Fails** — task results cannot be stored |

**Recovery behavior:**
- FastAPI routes that hit Redis will receive a connection error.
- The global exception handler catches this and returns HTTP 500 (not 503).
- When Redis recovers, all operations resume automatically (connection pool reconnects).
- No data is lost — the DB remains intact.

**Degradation path (future Phase D enhancement):**
```
Redis down → fall back to DB-only dedup (slower but safe)
           → accept submissions, defer rate limit check
           → queue tasks in memory (if using an in-process fallback)
```

**To test:**
```bash
docker stop automation_redis    # Stop Redis
curl POST /api/v1/applications/submit  # Should return 500 or 503
docker start automation_redis   # Restart Redis
curl GET /api/v1/ready          # Should return 200 once reconnected
```

---

## Scenario C: PostgreSQL Restart (TEST C)

**What happens:** The DB container restarts.

**What protects us:**
- `pool_pre_ping=True` on the SQLAlchemy engine.
- Pre-ping sends `SELECT 1` before each connection is used.
- Stale/broken connections are detected and discarded before the query runs.
- The pool automatically creates fresh connections.

**Sequence:**
```
DB restarts
     │
Next API request comes in
     │
SQLAlchemy pool picks a connection → pre-ping fails
     │                                    │
     │                              Connection discarded
     │                                    │
     │                         New connection established
     │
Query runs successfully
```

**Celery tasks during DB restart:**
- If the task is at the DB write step when the restart happens, it will fail.
- The Celery retry mechanism catches the `OperationalError` and retries with backoff.
- Backoff schedule: 60s → 120s → 240s (enough time for PG to restart).

**To test:**
```bash
docker restart automation_postgres
# Immediately send a request — expect possible 500
# After ~10s, all requests should succeed
```

---

## Scenario D: Duplicate Submission (TEST D)

**Two-layer protection ensures no duplicates reach the DB.**

### Layer 1 — Redis Fast Path
```
POST /submit with same (user_id, job_id)
     │
check_duplicate():
  Redis EXISTS "dedup:applied:{user_id}:{job_id}"
     │
  Key exists → raise DuplicateApplicationError → HTTP 409
```

### Layer 2 — DB Fallback
```
(Redis key expired or Redis was cleared)
     │
check_duplicate():
  Redis miss
     │
  DB: SELECT FROM applications WHERE user_id=? AND job_id=? AND deleted_at IS NULL
     │
  Row exists → raise DuplicateApplicationError → HTTP 409
```

### Dedup Cache is Set After Successful Submission
```
Task completes successfully:
  mark_dedup_cache(user_id, job_id)
    → Redis SET "dedup:applied:{user_id}:{job_id}" "1" EX 7776000 (90 days)
```

**Note:** The dedup flag is set AFTER submission succeeds, not at submit time.
This allows the user to re-submit if the task fails (so duplicate flag only
blocks genuinely already-applied-to jobs, not failed attempts).

---

## Scenario E: Invalid State Transition (TEST E)

**Example: attempting `processing → queued`**

```
PATCH /api/v1/applications/{id}/status
Body: {"status": "queued"}

Current status in DB: "processing"
     │
ApplicationService.transition_status()
  VALID_TRANSITIONS["processing"] = {applied, failed, captcha_required, asset_error}
     │
  "queued" NOT IN allowed set
     │
  raise InvalidStatusTransitionError(
    message="Cannot transition from 'processing' to 'queued'.",
    details={"from": "processing", "to": "queued", "allowed": [...]}
  )
     │
  Global error handler → HTTP 409
     │
  Response:
  {
    "success": false,
    "error": {
      "code": "INVALID_STATUS_TRANSITION",
      "message": "Cannot transition from 'processing' to 'queued'.",
      "details": {"from": "processing", "to": "queued", "allowed": ["applied", "failed", ...]}
    }
  }
```

**Guarantees:**
- No partial writes (the transition either fully succeeds or fully rolls back).
- The status history is NEVER corrupted with invalid entries.
- The error details expose the allowed transitions for debugging.

---

## Scenario F: Rate Limit Reached

```
POST /submit when user has hit 50 applications today
     │
check_rate_limit(user_id):
  Redis GET "rate:daily:{user_id}:{YYYYMMDD}" → "50"
  50 >= 50 → raise RateLimitExceededError → HTTP 429
     │
  No DB write. No Celery task. Fast rejection.
```

**Reset:** The Redis key has a 48-hour TTL. It expires automatically at midnight
the day after tomorrow, resetting the limit naturally without a cron job.

---

## Scenario G: Max Retries Exhausted

```
process_application task fails 3 times (max_retries=3)
     │
retry 1: delay 60s
retry 2: delay 120s
retry 3: delay 240s
     │
4th attempt fails → self.request.retries >= self.max_retries
     │
_mark_permanently_failed(application_id, error_str):
  transition_status(→ FAILED, reason="Max retries exhausted: {error}")
     │
Task returns {"status": "failed", ...}
     │
Application is in terminal FAILED state — no more retries.
User can create a new application if they wish to retry manually.
```

---

## Recovery Runbook — Quick Reference

| Problem | Symptoms | Recovery Steps |
|---------|----------|----------------|
| Worker crashed | Tasks stuck in QUEUED | `docker-compose restart worker` |
| Apps stuck in PROCESSING | Beat cleanup not yet run | Wait ≤30min for cleanup, or: `docker-compose exec worker celery -A app.tasks.celery_app.celery_app call app.tasks.application_tasks.cleanup_stale_applications` |
| Redis down | API returns 500 on submit | `docker-compose restart redis`, then `GET /ready` until healthy |
| DB down | API returns 500 everywhere | `docker-compose restart postgres`, then verify pool reconnects |
| Celery queue not draining | Tasks queued but not processing | Check worker logs: `docker-compose logs worker` |
| Migration not applied | API 500 on first request | `docker-compose exec api alembic upgrade head` |
