# Queue Architecture — Celery + Redis

## Overview

The Application Automation Agent uses **Celery** as its distributed task queue,
backed by **Redis** as both the broker (task delivery) and result backend (task tracking).

---

## Three-Queue Design

```
                    ┌─────────────────────────────────┐
                    │         Redis (Broker)           │
                    │                                  │
 FastAPI API ──────►│  Queue: high   priority=10       │
 (submit route)     │  Queue: normal priority=5        │
                    │  Queue: low    priority=1         │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │         Celery Workers           │
                    │  --queues=high,normal,low        │
                    │  --concurrency=4                 │
                    │  consumer 1 ──► processes tasks  │
                    │  consumer 2 ──► processes tasks  │
                    │  consumer 3 ──► processes tasks  │
                    │  consumer 4 ──► processes tasks  │
                    └─────────────────────────────────┘
```

### Queue Assignment Rules

| Queue | Priority | Used For |
|-------|----------|---------|
| `high` | 10 | Applications with `priority=HIGH` in guardrails |
| `normal` | 5 | Standard applications (default) |
| `low` | 1 | Celery Beat periodic tasks (cleanup, maintenance) |

### Priority within a queue

Celery processes tasks in FIFO order within each queue.
The `high` queue is consumed before `normal`, which is consumed before `low`.
Workers poll all three queues simultaneously but weight by priority.

---

## Task Routing

```python
task_routes = {
    "app.tasks.application_tasks.process_application":      {"queue": "normal"},
    "app.tasks.application_tasks.process_application_high": {"queue": "high"},
    "app.tasks.application_tasks.cleanup_stale_applications": {"queue": "low"},
}
```

### Deterministic Task IDs

```python
task_id = f"apply-{application_id}"
```

Using a deterministic task ID prevents the same application from being queued
twice if the API receives duplicate requests before the dedup cache is populated.
Redis rejects duplicate task IDs from Celery's task deduplication.

---

## Redis Key Namespacing

All Redis keys follow a structured namespace to prevent collisions:

```
Rate Limiting:
  rate:daily:{user_id}:{YYYYMMDD}
  → Type: string (counter)
  → TTL:  48 hours
  → Op:   INCR (atomic)

Dedup Cache:
  dedup:applied:{user_id}:{job_id}
  → Type: string ("1")
  → TTL:  90 days
  → Op:   EXISTS (check), SET ... EX (write)

Task Dedup Lock:
  task:lock:{application_id}
  → Type: string
  → TTL:  task timeout + 5min buffer
  → Op:   SET NX (atomic acquire), DEL (release)

Celery Broker (managed by Celery):
  _kombu.binding.high
  _kombu.binding.normal
  _kombu.binding.low

Celery Results (managed by Celery):
  celery-task-meta-{task_id}
```

---

## Reliability Settings

### `acks_late=True` — The Most Critical Setting

```
Standard behavior (acks_late=False, the default):
  Worker picks task → IMMEDIATELY acknowledges → processes task
  If worker crashes → message is GONE → task lost forever

Our behavior (acks_late=True):
  Worker picks task → processes task → acknowledges ONLY on success/known failure
  If worker crashes → message is REQUEUED → another worker picks it up
```

### `reject_on_worker_lost=True`

If a worker is killed with SIGKILL (hard kill), the task is negatively acknowledged
and put back on the queue. Without this, it would go to the DLQ.

### `worker_prefetch_multiplier=1`

```
Without prefetch=1:
  Worker A: handling 4 tasks in queue (even though it can only process 1 at a time)
  Worker B: idle (no tasks assigned to it even though the queue has more)

With prefetch=1:
  Worker A: handling 1 task
  Worker B: handling 1 task
  → Fair distribution, prevents worker A from starving B
```

### Time Limits

```
soft_time_limit=600  (10 minutes)
  → Celery sends SIGTERM to the task
  → Task can catch SoftTimeLimitExceeded and clean up gracefully

time_limit=660       (11 minutes)
  → Celery sends SIGKILL to the worker process
  → No cleanup possible — used as last resort
```

---

## Celery Beat — Periodic Tasks

```
                    ┌──────────────────┐
                    │  Celery Beat     │
                    │  (scheduler)     │
                    │                  │
                    │  Every 30 min:   │
                    │  cleanup_stale   │
                    └────────┬─────────┘
                             │ publishes to "low" queue
                             ▼
                    ┌──────────────────┐
                    │  Celery Worker   │
                    │  (low queue)     │
                    └──────────────────┘
```

### Current Beat Schedule

| Task | Schedule | Queue | Purpose |
|------|----------|-------|---------|
| `cleanup_stale_applications` | Every 30 min | low | Find apps stuck in PROCESSING >15min and fail them |

---

## Monitoring — Flower

Flower is a real-time Celery monitoring web UI:

```
http://localhost:5555
```

Shows:
- Active tasks (currently being processed)
- Queued tasks (waiting in each queue)
- Completed tasks and their results
- Failed tasks and their exceptions
- Worker health and throughput

---

## Scaling the Worker

**Horizontal scaling** (add more workers):
```bash
docker-compose up --scale worker=3
```

Each additional `worker` container registers with the Redis broker and starts
consuming tasks from all three queues. No coordination needed.

**Vertical scaling** (more concurrency per worker):
```yaml
command: celery -A ... worker --concurrency=8  # default is 4
```

**Recommended first approach:** Scale horizontally (add workers) before
increasing concurrency per worker. More workers = better isolation from crashes.

---

## Message Flow Internals

```
1. FastAPI calls process_application.apply_async(args, queue="normal")
   → Celery serializes task to JSON
   → Publishes JSON message to Redis list "_kombu.binding.normal"

2. Celery worker polls Redis BRPOP on all queues (blocking pop with timeout)
   → Picks up message from "high" first (if any), then "normal", then "low"
   → Deserializes JSON → calls process_application(payload_dict)
   → Keeps the message "invisible" (not acknowledged) until task completes

3. Task completes:
   Success → RPUSH to result backend, then DELETE message from broker
   Failure → Retry: LPUSH back to queue with new ETA
   Max retries → mark failed, delete message

4. Celery Beat:
   → Reads beat_schedule configuration
   → At each trigger, calls apply_async() for the scheduled task
   → Beat is a single process — only run ONE Beat container to avoid duplicate triggers
```
