# Local Development Guide

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Docker Desktop | ≥ 4.0 | https://www.docker.com/products/docker-desktop |
| Docker Compose | ≥ 2.0 | Bundled with Docker Desktop |
| Python | ≥ 3.12 | https://python.org (only needed for tests/scripts outside Docker) |
| Git | any | https://git-scm.com |

---

## Quick Start (Docker — Recommended)

```bash
# 1. Clone and enter the module directory
cd "E:\Antigravity Projects\Hackthon\Member_04_Application_Automation"

# 2. Copy the environment template
Copy-Item .env.example .env

# 3. Start the full stack
docker-compose up --build

# 4. Verify everything is running
# FastAPI Swagger UI:    http://localhost:8004/docs
# Celery Flower:         http://localhost:5555
# Health check:          http://localhost:8004/api/v1/health
# Readiness check:       http://localhost:8004/api/v1/ready
```

### Expected Output on Startup

```
automation_postgres  | database system is ready to accept connections
automation_redis     | Ready to accept connections
automation_api       | Application startup complete
automation_api       | Uvicorn running on http://0.0.0.0:8004
automation_worker    | celery@worker ready.
automation_worker    | Registered tasks: app.tasks.application_tasks.process_application
```

---

## Running Database Migrations

Migrations run automatically when using docker-compose. For manual control:

```bash
# Apply all pending migrations
docker-compose exec api alembic upgrade head

# Check current revision
docker-compose exec api alembic current

# View migration history
docker-compose exec api alembic history

# Rollback the last migration
docker-compose exec api alembic downgrade -1

# Generate a new auto-migration (after changing ORM models)
docker-compose exec api alembic revision --autogenerate -m "add_field_xyz"
```

---

## Running Tests

### Unit Tests (no external services needed)

```bash
# Install dev dependencies locally
pip install -e ".[dev]"

# Run all unit tests
pytest tests/unit/ -v

# Run with coverage report
pytest tests/unit/ --cov=app --cov-report=term-missing

# Run a specific test file
pytest tests/unit/test_status_machine.py -v

# Run a specific test
pytest tests/unit/test_status_machine.py::TestTerminalStates -v
```

### Integration Tests (mock infrastructure, no Docker needed)

```bash
pytest tests/integration/ -v
```

### Load Tests (requires running Docker stack)

```bash
# Start stack first
docker-compose up -d

# Run baseline (50 submissions, 10 concurrent)
python tests/load/load_test.py --count 50

# Run higher concurrency
python tests/load/load_test.py --count 100 --concurrency 20

# Save results
python tests/load/load_test.py --count 50 --output load_results.json
```

---

## Validation Pipeline Script

```powershell
# Run full 10-step validation against running Docker stack
.\scripts\validate_pipeline.ps1

# Skip Docker build (if already running)
.\scripts\validate_pipeline.ps1 -SkipDockerBuild

# Verbose output (shows all HTTP responses)
.\scripts\validate_pipeline.ps1 -VerboseOutput

# Against a different host
.\scripts\validate_pipeline.ps1 -BaseUrl "http://staging.example.com"
```

---

## Manual API Testing (Swagger UI)

Open **http://localhost:8004/docs** for the interactive Swagger UI.

### Step-by-step flow test:

**1. Submit a fake email application:**
```json
POST /api/v1/applications/submit
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "job_id": "7f3e4e20-f56c-4b77-8f81-1234567890ab",
  "job_metadata": {
    "company_name": "Test Corp",
    "role_title": "Engineer",
    "application_method": "email",
    "contact_email": "jobs@testcorp.example.com"
  },
  "resume": {
    "version_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "storage_url": "https://our-storage.example.com/resume.pdf",
    "filename": "My_Resume.pdf"
  }
}
```
→ Expected: HTTP 202 with `application_id` and `tracking_url`

**2. Poll status (use application_id from step 1):**
```
GET /api/v1/applications/{application_id}/status
```
→ Watch status change from `queued` → `processing` → `applied`

**3. View audit trail:**
```
GET /api/v1/applications/{application_id}/history
```
→ Shows every status transition with timestamps

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `development` | Environment mode |
| `DEBUG` | `true` | Enable SQL echo and pretty logs |
| `DATABASE_URL` | postgres://... | Async PostgreSQL connection string |
| `REDIS_URL` | redis://localhost:6379/0 | Redis for app data |
| `CELERY_BROKER_URL` | redis://localhost:6379/1 | Redis for Celery tasks |
| `CELERY_RESULT_BACKEND` | redis://localhost:6379/2 | Redis for task results |
| `DAILY_APPLICATION_LIMIT_DEFAULT` | `50` | Max submissions per user per day |
| `ENABLE_REAL_EMAIL_SENDING` | `false` | Feature flag for Phase B |
| `ENABLE_REAL_WEB_AUTOMATION` | `false` | Feature flag for Phase C |

> All feature flags default to `false` in Phase A.
> Real automation begins in Phase B/C by setting these to `true`.

---

## Debugging Tools

### View API logs
```bash
docker-compose logs -f api
```

### View worker task processing
```bash
docker-compose logs -f worker
```

### Query the database directly
```bash
docker-compose exec postgres psql -U postgres -d automation_db

# Useful queries:
SELECT application_id, company_name, status, retry_count FROM applications;
SELECT from_status, to_status, reason, created_at FROM application_status_history ORDER BY created_at;
SELECT level, event, message, created_at FROM application_logs ORDER BY created_at;
```

### Inspect Redis state
```bash
docker-compose exec redis redis-cli

# View all keys
KEYS *

# Check rate limit counter
GET rate:daily:550e8400-e29b-41d4-a716-446655440000:20260612

# Check dedup cache
EXISTS dedup:applied:550e8400-e29b-41d4-a716-446655440000:7f3e4e20-f56c-4b77-8f81-1234567890ab

# View Celery queues
LLEN _kombu.binding.normal
LLEN _kombu.binding.high
```

### Celery worker — inspect
```bash
# List registered tasks
docker-compose exec worker celery -A app.tasks.celery_app.celery_app inspect registered

# List active tasks
docker-compose exec worker celery -A app.tasks.celery_app.celery_app inspect active

# Manually trigger cleanup task
docker-compose exec worker celery -A app.tasks.celery_app.celery_app call \
    app.tasks.application_tasks.cleanup_stale_applications
```

---

## Resetting the Local Environment

```bash
# Stop everything and delete all data volumes
docker-compose down -v

# Rebuild from scratch
docker-compose up --build
```

---

## Code Quality

```bash
# Install pre-commit hooks (run once after cloning)
pip install pre-commit
pre-commit install
pre-commit install --hook-type commit-msg

# Run all hooks manually
pre-commit run --all-files

# Run only the linter
ruff check app/ tests/

# Auto-fix linting issues
ruff check --fix app/ tests/

# Format code
ruff format app/ tests/

# Type check
mypy app/
```

---

## Project Structure

```
Member_04_Application_Automation/
├── app/
│   ├── main.py              ← FastAPI app factory
│   ├── core/
│   │   ├── config.py        ← Pydantic-settings (all env vars)
│   │   ├── logging.py       ← Structlog configuration
│   │   ├── exceptions.py    ← Custom exception hierarchy
│   │   ├── database.py      ← Async SQLAlchemy engine
│   │   └── redis.py         ← Async Redis client
│   ├── models/
│   │   ├── orm.py           ← SQLAlchemy ORM models
│   │   └── schemas.py       ← Pydantic schemas + status enums
│   ├── services/
│   │   └── application_service.py  ← ALL business logic
│   ├── tasks/
│   │   ├── celery_app.py    ← Celery configuration
│   │   └── application_tasks.py    ← Task definitions
│   ├── api/v1/
│   │   ├── health.py        ← /health, /ready endpoints
│   │   ├── applications.py  ← Application CRUD endpoints
│   │   └── router.py        ← Route aggregation
│   └── middleware/
│       └── request_id.py    ← Trace ID injection
├── migrations/
│   └── versions/
│       └── 001_initial_schema.py   ← DB schema
├── tests/
│   ├── conftest.py          ← Shared fixtures
│   ├── unit/                ← No external deps
│   ├── integration/         ← HTTP-level with mocked infra
│   └── load/                ← Requires running Docker stack
├── docs/
│   ├── runtime_flow.md      ← Execution trace documentation
│   ├── state_machine.md     ← Status lifecycle documentation
│   ├── failure_recovery.md  ← Failure scenario playbook
│   ├── queue_architecture.md ← Celery + Redis design
│   └── local_development.md ← This file
├── scripts/
│   └── validate_pipeline.ps1 ← Automated validation script
├── docker/
│   ├── Dockerfile           ← FastAPI image
│   └── Dockerfile.worker    ← Celery worker image
├── docker-compose.yml       ← Full stack definition
├── pyproject.toml           ← Dependencies + tool config
├── alembic.ini              ← Migration configuration
└── .env.example             ← Environment template
```
