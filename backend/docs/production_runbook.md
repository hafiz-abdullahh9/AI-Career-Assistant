# Production Runbook — Application Automation Agent

> **Service**: Member 4 — Application Automation Agent  
> **Stack**: FastAPI + Celery + PostgreSQL + Redis + Selenium/Chrome  
> **Deployment**: Docker Compose (staging / production)  
> **Last Updated**: 2026-06-13

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Deployment Steps](#2-deployment-steps)
3. [Migration Workflow](#3-migration-workflow)
4. [RBAC Bootstrap](#4-rbac-bootstrap)
5. [Health Verification](#5-health-verification)
6. [Rollback Procedure](#6-rollback-procedure)
7. [Scaling the Worker](#7-scaling-the-worker)
8. [Emergency Procedures](#8-emergency-procedures)
9. [Troubleshooting Guide](#9-troubleshooting-guide)
10. [Replay Debugging](#10-replay-debugging)
11. [Monitoring Checklist](#11-monitoring-checklist)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose                        │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │  migrate │  │   api    │  │  worker  │              │
│  │ (one-shot│  │ FastAPI  │  │  Celery  │              │
│  │  +RBAC)  │  │  :8004   │  │  +Chrome │              │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘              │
│       │              │              │                     │
│       ▼              ▼              ▼                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ postgres │  │  redis   │  │   beat   │              │
│  │  :5432   │  │  :6379   │  │ Celery   │              │
│  └──────────┘  └──────────┘  │ scheduler│              │
│                               └──────────┘              │
│                                                          │
│  ┌──────────┐                                           │
│  │  flower  │  Celery monitoring UI :5555               │
│  └──────────┘                                           │
└─────────────────────────────────────────────────────────┘
```

**Startup sequence** (enforced by `depends_on` conditions):
1. `postgres` → healthy
2. `redis` → healthy  
3. `migrate` → runs `alembic upgrade head` + `seed_rbac.py` + `verify_rbac.py` → exits 0
4. `api` + `worker` + `beat` → start
5. `flower` → starts (depends only on redis)

---

## 2. Deployment Steps

### First Deployment (clean environment)

```bash
# 1. Clone and configure
cd Member_04_Application_Automation
cp .env.production.example .env.production
# Edit .env.production — fill in ALL CHANGE_ME values

# 2. Pull/build images
docker compose -f docker-compose.yml build --no-cache

# 3. Start infrastructure first (optional — compose handles ordering)
docker compose -f docker-compose.yml up -d postgres redis

# 4. Wait for postgres to be healthy
docker compose -f docker-compose.yml ps

# 5. Start everything (migrate runs first automatically)
docker compose -f docker-compose.yml up -d

# 6. Verify migrate service exited cleanly
docker compose -f docker-compose.yml logs migrate

# 7. Verify API is healthy
curl -f http://localhost:8004/health
```

### Subsequent Deployments (rolling update)

```bash
# 1. Pull new images or rebuild
docker compose -f docker-compose.yml build api worker

# 2. Apply migrations BEFORE replacing running containers
docker compose -f docker-compose.yml run --rm migrate

# 3. Replace api and worker with zero-downtime rolling restart
docker compose -f docker-compose.yml up -d --no-deps api
docker compose -f docker-compose.yml up -d --no-deps worker
docker compose -f docker-compose.yml up -d --no-deps beat

# 4. Verify health
curl -f http://localhost:8004/health
python scripts/healthcheck.py --json
```

> [!IMPORTANT]
> Always run migrations **before** deploying new app containers. The migrate service handles this automatically on first `up`, but on rolling updates you must run it explicitly.

---

## 3. Migration Workflow

### View current migration state

```bash
# What revision is the DB at?
docker compose -f docker-compose.yml run --rm \
  -e DATABASE_URL=postgresql+asyncpg://... \
  api alembic current

# Show full migration history
docker compose -f docker-compose.yml run --rm api alembic history --verbose
```

### Apply migrations manually

```bash
# Apply all pending migrations to head
docker compose -f docker-compose.yml run --rm api alembic upgrade head

# Apply a specific revision
docker compose -f docker-compose.yml run --rm api alembic upgrade <revision_id>
```

### Create a new migration

```bash
# Auto-generate from model changes
docker compose -f docker-compose.yml run --rm api \
  alembic revision --autogenerate -m "describe_your_change"

# Always review the generated file in migrations/versions/ before applying
```

### Check for unapplied migrations (CI gate)

```bash
alembic check
# Exits 0 if no unapplied migrations, 1 otherwise
```

---

## 4. RBAC Bootstrap

RBAC seeding is **idempotent** — safe to re-run at any time.

### Roles and permissions matrix

| Role | Permissions |
|------|-------------|
| `admin` | All 10 permissions |
| `operator` | approve_execution, cancel_execution, manage_queues, access_dashboard, view_replay |
| `auditor` | view_audits, view_replay |
| `viewer` | access_dashboard |

### Re-seed RBAC manually

```bash
docker compose -f docker-compose.yml run --rm api python scripts/seed_rbac.py
```

### Verify RBAC integrity

```bash
docker compose -f docker-compose.yml run --rm api python scripts/verify_rbac.py
```

Verification checks:
- Audit event preservation after user deletion (actor_id → NULL)
- Cascade deletes for user_roles, user_sessions, mfa_secrets
- Required indexes present
- Uniqueness constraints enforced
- Security column types correct

---

## 5. Health Verification

### API liveness check

```bash
curl -f http://localhost:8004/health
# Expected: {"status": "ok", ...}
```

### Full preflight health check

```bash
# Human-readable output
python scripts/healthcheck.py

# JSON output (monitoring systems)
python scripts/healthcheck.py --json

# Quick liveness only (DB + Redis)
python scripts/healthcheck.py --liveness

# Skip Chrome (API containers)
python scripts/healthcheck.py --no-chrome
```

### Check all container statuses

```bash
docker compose -f docker-compose.yml ps
# All services should show: healthy (or exited 0 for migrate)
```

### Check logs for errors

```bash
# API logs
docker compose -f docker-compose.yml logs --tail=50 api

# Worker logs
docker compose -f docker-compose.yml logs --tail=50 worker

# Migration logs
docker compose -f docker-compose.yml logs migrate

# All services, follow
docker compose -f docker-compose.yml logs -f
```

### Flower UI (Celery monitoring)

```
http://localhost:5555/flower
```

Shows: active workers, task queue depth, task success/failure rates, task history.

---

## 6. Rollback Procedure

### Application rollback (no schema changes)

```bash
# Tag the current working image before deploying new version
docker tag automation-api:latest automation-api:rollback
docker tag automation-worker:latest automation-worker:rollback

# If new version is broken, roll back:
docker compose -f docker-compose.yml stop api worker beat
docker tag automation-api:rollback automation-api:latest
docker tag automation-worker:rollback automation-worker:latest
docker compose -f docker-compose.yml up -d api worker beat
```

### Database rollback (if migration was applied)

> [!WARNING]
> Downgrading Alembic migrations is risky if data has been written to new schema columns. Always test downgrade scripts in staging before production.

```bash
# Downgrade one revision
docker compose -f docker-compose.yml run --rm api alembic downgrade -1

# Downgrade to a specific revision
docker compose -f docker-compose.yml run --rm api alembic downgrade <revision_id>

# View what the downgrade will do (without applying)
docker compose -f docker-compose.yml run --rm api alembic downgrade --sql -1
```

---

## 7. Scaling the Worker

### Scale Celery workers horizontally

```bash
# Run 3 worker containers
docker compose -f docker-compose.yml up -d --scale worker=3

# Each worker gets a unique hostname: worker@<container_id>
# All workers pick from the same Redis queues: high, normal, low
```

### Tune concurrency per worker

Set in `.env.production`:
```
CELERY_CONCURRENCY=4   # Threads per worker container
```

> [!TIP]
> For Selenium workers: keep concurrency low (2–4) because each Selenium task spawns a Chrome process. More Chrome instances = more memory. Monitor RAM with `docker stats`.

### Monitor worker resource usage

```bash
docker stats automation_worker
# Watch MEM USAGE — each Chrome session uses ~300–500MB
```

---

## 8. Emergency Procedures

### Emergency pause — stop all task processing

```bash
# Revoke all active tasks and shut down workers
docker compose -f docker-compose.yml stop worker beat

# Or: soft stop (let running tasks finish, then stop)
docker compose -f docker-compose.yml exec worker \
  celery -A app.tasks.celery_app.celery_app control shutdown
```

### Emergency pause — drain queue only (keep workers running)

```bash
# Cancel all pending tasks in all queues
docker compose -f docker-compose.yml exec worker \
  celery -A app.tasks.celery_app.celery_app purge -f
```

> [!CAUTION]
> `purge` permanently discards all queued tasks. Use only in genuine emergencies.

### Emergency restart — full stack

```bash
docker compose -f docker-compose.yml down
docker compose -f docker-compose.yml up -d
```

### Database connection exhaustion

If PostgreSQL reports "too many connections":

```bash
# Check active connections
docker compose -f docker-compose.yml exec postgres \
  psql -U postgres -d automation_db \
  -c "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"

# Terminate idle connections
docker compose -f docker-compose.yml exec postgres \
  psql -U postgres -d automation_db \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - interval '5 minutes';"
```

---

## 9. Troubleshooting Guide

### `migrate` service exits with non-zero code

```bash
docker compose -f docker-compose.yml logs migrate
```

Common causes:
- **Postgres not healthy yet** → increase `start_period` in postgres healthcheck
- **Missing alembic head** → check `migrations/versions/` for merge conflicts
- **RBAC seed fails** → check `scripts/seed_rbac.py` for schema mismatch

### API container starts but `/health` returns 503

```bash
docker compose -f docker-compose.yml logs api | grep -E "ERROR|CRITICAL"
```

Common causes:
- **DB unreachable** → check `DATABASE_URL` in `.env.production`
- **Redis unreachable** → check `REDIS_URL`
- **Migration not applied** → `migrate` service failed silently

### Worker tasks not executing

```bash
# Check worker is connected to broker
docker compose -f docker-compose.yml exec worker \
  celery -A app.tasks.celery_app.celery_app inspect ping

# Check queue depths
docker compose -f docker-compose.yml exec worker \
  celery -A app.tasks.celery_app.celery_app inspect active_queues
```

### Chrome/Selenium failures in worker

```bash
docker compose -f docker-compose.yml logs worker | grep -i "chrome\|selenium\|webdriver"
```

Common causes:
- **Missing `--no-sandbox`** → ensure `CHROME_NO_SANDBOX=1` in worker environment
- **ChromeDriver version mismatch** → rebuild worker image after updating `CHROME_VERSION`
- **Out of memory** → reduce `CELERY_CONCURRENCY`; add memory limits to worker service

### Permission denied errors in container

```bash
# Check if non-root user can write to required paths
docker compose -f docker-compose.yml exec --user root worker \
  ls -la /home/appuser/.wdm/
```

---

## 10. Replay Debugging

The platform supports execution replay for debugging failed or suspicious automation runs.

### View replay data

```bash
# Query replay events for a specific application
docker compose -f docker-compose.yml exec postgres \
  psql -U postgres -d automation_db \
  -c "SELECT * FROM audit_events WHERE resource_type = 'application' ORDER BY timestamp DESC LIMIT 20;"
```

### Export replay trace for a session

```bash
# GET /api/v1/applications/{app_id}/replay
curl -H "Authorization: Bearer <token>" \
  http://localhost:8004/api/v1/applications/<app_id>/replay
```

### Replay trace interpretation

- `SUBMITTED` → `QUEUED` → `IN_PROGRESS` → `COMPLETED` / `FAILED` / `PENDING_APPROVAL`
- HITL escalations appear as `PENDING_APPROVAL` with an `approval_request_id`
- Retry events show `retry_count` and `retry_reason`

---

## 11. Monitoring Checklist

### Pre-deployment checklist

- [ ] `.env.production` is complete — no `CHANGE_ME` values remaining
- [ ] `docker compose build` completed without errors
- [ ] `alembic check` shows no unapplied migrations
- [ ] `python scripts/healthcheck.py` exits 0 on staging
- [ ] Flower UI accessible and showing connected workers
- [ ] `/health` endpoint returns 200

### Post-deployment checklist

- [ ] All containers show `healthy` status
- [ ] `migrate` service exited with code 0
- [ ] Unit tests pass: `pytest tests/unit`
- [ ] RBAC verified: `python scripts/verify_rbac.py`
- [ ] API accessible: `curl http://localhost:8004/health`
- [ ] No ERROR-level logs in first 5 minutes: `docker compose logs -f`
- [ ] Celery workers accepting tasks: Flower → Workers tab

### Regular operational checks (daily)

```bash
# Quick full health check
python scripts/healthcheck.py

# Check for any FAILED tasks in the last 24h
# (via Flower UI or celery inspect)
docker compose -f docker-compose.yml exec worker \
  celery -A app.tasks.celery_app.celery_app inspect stats

# Check postgres disk usage
docker compose -f docker-compose.yml exec postgres \
  psql -U postgres -d automation_db \
  -c "SELECT pg_size_pretty(pg_database_size('automation_db'));"
```
