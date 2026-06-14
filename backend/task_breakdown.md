# Task Breakdown — Member 4: Application Automation Agent
**Project:** AI Career Assistant Multi-Agent System 2026  
**Module Owner:** Member 4  
**Status:** Planning Phase  
**Last Updated:** 2026-06-12  

---

## 1. Overview

This document provides the complete implementation roadmap, broken into sprints. Each task is atomic, estimable, and reviewable independently. Tasks are sequenced by dependency order — infrastructure and data layer first, business logic second, UI and integrations last.

---

## 2. Implementation Phases

```
Phase 0: Foundation          [Week 1]     — Project setup, infra, configs
Phase 1: Data Layer          [Week 1-2]   — DB schema, models, migrations
Phase 2: Core APIs           [Week 2-3]   — FastAPI endpoints, basic routing
Phase 3: Email System        [Week 3-4]   — Gmail API + SMTP integration
Phase 4: Web Automation      [Week 4-6]   — Selenium engine, form filling
Phase 5: Tracking System     [Week 5-6]   — Tracking API, status management
Phase 6: Guardrails          [Week 6]     — Rate limiting, security layers
Phase 7: Integration         [Week 7]     — Connect to orchestrator, other agents
Phase 8: Testing & QA        [Week 7-8]   — Test suite, load testing
Phase 9: Deployment          [Week 8]     — Docker, CI/CD, monitoring
```

---

## 3. Phase 0: Foundation (Week 1)

### TASK-001: Project Scaffolding
**Estimate:** 0.5 day  
**Depends on:** Nothing

- [ ] Create `member_04/` directory structure
- [ ] Initialize Python project with `pyproject.toml`
- [ ] Set up virtual environment and dependencies
- [ ] Configure `pre-commit` hooks (black, ruff, mypy)

```
member_04/
├── app/
│   ├── api/           # FastAPI routers
│   ├── core/          # Config, database, security
│   ├── models/        # Pydantic models + SQLAlchemy ORM
│   ├── services/      # Business logic
│   │   ├── email/
│   │   ├── automation/
│   │   ├── tracking/
│   │   └── guardrails/
│   ├── tasks/         # Celery tasks
│   └── workers/       # Celery worker configuration
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── migrations/        # Alembic migrations
├── docker/            # Dockerfiles
├── docker-compose.yml
├── docker-compose.test.yml
├── pyproject.toml
├── alembic.ini
└── .env.example
```

### TASK-002: Docker Compose Infrastructure
**Estimate:** 0.5 day  
**Depends on:** TASK-001

- [ ] Write `docker-compose.yml` with all services
- [ ] Configure PostgreSQL 16 service + health check
- [ ] Configure Redis 7 service + health check
- [ ] Configure Selenium Hub + Chrome node services
- [ ] Configure shared volume for resume temp files
- [ ] Test all services come up healthy: `docker-compose up`

### TASK-003: Configuration System
**Estimate:** 0.5 day  
**Depends on:** TASK-001

- [ ] Create `app/core/config.py` using `pydantic-settings`
- [ ] Define all config vars with types and defaults
- [ ] Create `.env.example` with all required variables
- [ ] Integrate Secrets Manager client (AWS SM or Vault)
- [ ] Test config loads correctly in different environments

### TASK-004: Logging Setup
**Estimate:** 0.5 day  
**Depends on:** TASK-003

- [ ] Install and configure `structlog`
- [ ] Define standard log format (JSON with trace_id, user_id, app_id)
- [ ] Create logging middleware for FastAPI (auto-injects request_id)
- [ ] Configure log levels per environment
- [ ] Test log output format matches Datadog expected schema

---

## 4. Phase 1: Data Layer (Week 1-2)

### TASK-005: Database Connection & Pool
**Estimate:** 0.5 day  
**Depends on:** TASK-002, TASK-003

- [ ] Set up `asyncpg` connection pool
- [ ] Create `app/core/database.py` with pool management
- [ ] Create `get_db()` FastAPI dependency
- [ ] Write connection health check endpoint
- [ ] Test pool under concurrent load

### TASK-006: Alembic Migration Setup
**Estimate:** 0.5 day  
**Depends on:** TASK-005

- [ ] Initialize Alembic: `alembic init migrations`
- [ ] Configure `alembic.ini` with async support
- [ ] Write migration 001: Create ENUM types
- [ ] Test: `alembic upgrade head` applies without error

### TASK-007: Core Schema Migrations
**Estimate:** 1 day  
**Depends on:** TASK-006

- [ ] Migration 002: `applications` table + indexes
- [ ] Migration 003: `application_status_history` + trigger
- [ ] Migration 004: `email_sends` table
- [ ] Migration 005: `form_submissions` table
- [ ] Migration 006: `confirmations` table
- [ ] Migration 007: `retry_attempts` table
- [ ] Migration 008: `form_schemas` table
- [ ] Migration 009: `approval_requests` table
- [ ] Migration 010: `application_logs` table (partitioned)
- [ ] Migration 011: `updated_at` trigger function
- [ ] Test: Run all migrations up, then down, then up again

### TASK-008: SQLAlchemy ORM Models
**Estimate:** 1 day  
**Depends on:** TASK-007

- [ ] Create `Application` model with all fields
- [ ] Create `ApplicationStatusHistory` model
- [ ] Create `EmailSend` model
- [ ] Create `FormSubmission` model
- [ ] Create `Confirmation` model
- [ ] Create `RetryAttempt` model
- [ ] Create `FormSchema` model
- [ ] Create `ApprovalRequest` model
- [ ] Verify model relationships match FK constraints

### TASK-009: Pydantic Request/Response Schemas
**Estimate:** 1 day  
**Depends on:** TASK-008

- [ ] Create `ApplicationSubmitRequest` schema with validators
- [ ] Create `ApplicationResponse` schema
- [ ] Create `ApplicationListResponse` schema (paginated)
- [ ] Create `ApprovalRequest` schema
- [ ] Create `StatusUpdateRequest` schema
- [ ] Create `ApplicationResult` (output to orchestrator) schema
- [ ] Create `ErrorResponse` schema
- [ ] Write tests for all validators (see testing_strategy.md)

### TASK-010: Redis Client Setup
**Estimate:** 0.5 day  
**Depends on:** TASK-002, TASK-003

- [ ] Install and configure `redis.asyncio`
- [ ] Create `app/core/redis.py` with connection pool
- [ ] Create `get_redis()` FastAPI dependency
- [ ] Implement basic key operations (get, set, incr, expire)
- [ ] Write Redis health check

---

## 5. Phase 2: Core APIs (Week 2-3)

### TASK-011: FastAPI Application Setup
**Estimate:** 0.5 day  
**Depends on:** TASK-009, TASK-010

- [ ] Create `app/main.py` with FastAPI app
- [ ] Add CORS middleware
- [ ] Add request ID middleware
- [ ] Add logging middleware
- [ ] Add global exception handler
- [ ] Configure OpenAPI metadata
- [ ] Add `/health` and `/ready` endpoints

### TASK-012: JWT Authentication Middleware
**Estimate:** 0.5 day  
**Depends on:** TASK-011

- [ ] Install and configure `python-jose`
- [ ] Create JWT validation dependency
- [ ] Create `get_current_user()` dependency
- [ ] Add auth to protected routes
- [ ] Create internal service shared-secret validation
- [ ] Write auth unit tests

### TASK-013: Application Submit Endpoint
**Estimate:** 1 day  
**Depends on:** TASK-012, TASK-008, TASK-009

- [ ] Implement `POST /api/v1/applications/submit`
- [ ] Add idempotency key handling
- [ ] Add guardrails check (see TASK-018 for guard service)
- [ ] Add application record creation
- [ ] Enqueue Celery task
- [ ] Return 202 with tracking URL
- [ ] Write unit + integration tests

### TASK-014: Application Status & List Endpoints
**Estimate:** 1 day  
**Depends on:** TASK-013

- [ ] Implement `GET /api/v1/applications/{id}/status`
- [ ] Implement `GET /api/v1/applications` with filters + cursor pagination
- [ ] Implement `PATCH /api/v1/applications/{id}/status`
- [ ] Implement `DELETE /api/v1/applications/{id}` (soft delete)
- [ ] Implement `GET /users/{id}/statistics`
- [ ] Write unit + integration tests for all endpoints

### TASK-015: Approval Workflow Endpoints
**Estimate:** 1 day  
**Depends on:** TASK-013

- [ ] Implement `GET /api/v1/applications/{id}/approval`
- [ ] Implement `POST /api/v1/approvals/{token}/approve`
- [ ] Implement `POST /api/v1/approvals/{token}/reject`
- [ ] Add token expiry check
- [ ] Auto-reject expired tokens (Celery Beat task)
- [ ] Write unit + integration tests

### TASK-016: Confirmation Endpoints
**Estimate:** 0.5 day  
**Depends on:** TASK-013

- [ ] Implement `GET /api/v1/applications/{id}/confirmations`
- [ ] Implement `POST /internal/applications/{id}/result` (internal)
- [ ] Write tests

### TASK-017: WebSocket Live Tracking
**Estimate:** 1 day  
**Depends on:** TASK-015

- [ ] Add `websockets` dependency
- [ ] Implement `WS /ws/applications/{id}/live`
- [ ] Integrate with Redis Pub/Sub for status event emission
- [ ] Test with WebSocket client

---

## 6. Phase 3: Guardrails Service (Week 3)

### TASK-018: Rate Limiting Service
**Estimate:** 1 day  
**Depends on:** TASK-010

- [ ] Implement `GuardrailsManager` class
- [ ] Implement `check_daily_limit(user_id)` with Redis INCR
- [ ] Implement `check_platform_limit(user_id, platform)` 
- [ ] Implement `increment_counter(user_id)` post-success
- [ ] Implement `GET /users/{id}/rate-limits` endpoint
- [ ] Write unit + integration tests

### TASK-019: Job Verification Service
**Estimate:** 0.5 day  
**Depends on:** TASK-005

- [ ] Implement `verify_job_is_approved(job_id)` — queries verified_jobs table (or external API)
- [ ] Define interface to Job Verification Agent (stub initially)
- [ ] Write unit tests with mocked verification results

### TASK-020: Duplicate Detection Service
**Estimate:** 0.5 day  
**Depends on:** TASK-010, TASK-005

- [ ] Implement `check_for_duplicate(user_id, job_id)` using both Redis and DB
- [ ] Implement Redis dedup cache population post-apply
- [ ] Write unit + integration tests

### TASK-021: Manual Approval Service
**Estimate:** 1 day  
**Depends on:** TASK-015

- [ ] Implement `ApprovalService` with request creation, notification, expiry
- [ ] Implement approval email template and sender
- [ ] Implement Celery Beat job for expired approval cleanup
- [ ] Write tests

---

## 7. Phase 3: Celery Task Infrastructure (Week 3)

### TASK-022: Celery App Setup
**Estimate:** 0.5 day  
**Depends on:** TASK-010

- [ ] Create `app/workers/celery_app.py`
- [ ] Configure broker (Redis) and backend (Redis)
- [ ] Configure task serialization (JSON)
- [ ] Configure priority queues: `high`, `normal`, `low`
- [ ] Configure Celery Beat for scheduled tasks
- [ ] Add Celery health check

### TASK-023: Route Selector Task
**Estimate:** 0.5 day  
**Depends on:** TASK-022

- [ ] Implement `route_application(application_id)` Celery task
- [ ] Route to `apply_via_email` or `apply_via_webform` based on DB record
- [ ] Handle unknown method gracefully
- [ ] Write unit tests

### TASK-024: DLQ Processor
**Estimate:** 0.5 day  
**Depends on:** TASK-022

- [ ] Implement `process_dlq()` Celery Beat task (every 30 min)
- [ ] Implement requeue logic for recoverable entries
- [ ] Implement alerting for permanent failures
- [ ] Write tests

---

## 8. Phase 3: Email Application System (Week 3-4)

### TASK-025: Gmail API Client
**Estimate:** 1 day  
**Depends on:** TASK-022

- [ ] Install `google-auth`, `google-api-python-client`
- [ ] Implement `GmailAPIClient` with OAuth2
- [ ] Implement token refresh logic
- [ ] Implement `send_message(to, subject, body, attachments)` method
- [ ] Write unit tests with mocked Gmail API

### TASK-026: SMTP Fallback Client
**Estimate:** 0.5 day  
**Depends on:** TASK-022

- [ ] Install `aiosmtplib`
- [ ] Implement `SMTPClient` with TLS support
- [ ] Implement connection pooling
- [ ] Implement `send_message(...)` method (same interface as Gmail client)
- [ ] Write unit tests

### TASK-027: Email Client Factory
**Estimate:** 0.5 day  
**Depends on:** TASK-025, TASK-026

- [ ] Implement `EmailClientFactory.get_client(user_email)` 
- [ ] Auto-detect Gmail vs. SMTP based on email domain
- [ ] Write unit tests

### TASK-028: Email Composer
**Estimate:** 1 day  
**Depends on:** TASK-027

- [ ] Create Jinja2 email templates (HTML + plain text)
- [ ] Implement `EmailComposer.compose(application, user, job)` 
- [ ] Add attachment handling (resume PDF, cover letter PDF)
- [ ] Add file size validation
- [ ] Add PDF compression fallback (if >5MB)
- [ ] Write unit tests

### TASK-029: Email Application Celery Task
**Estimate:** 1 day  
**Depends on:** TASK-028

- [ ] Implement `apply_via_email(application_id)` Celery task
- [ ] Integrate fetch assets → compose → send → log flow
- [ ] Add retry policy per `retry_and_error_strategy.md`
- [ ] Handle all error classes (permanent vs. transient)
- [ ] Write integration tests

### TASK-030: Email Confirmation Listener
**Estimate:** 1 day  
**Depends on:** TASK-029

- [ ] Implement `poll_for_confirmation(application_id, message_id)` Celery task
- [ ] Gmail API inbox search by thread_id
- [ ] Parse auto-reply for application reference numbers
- [ ] Store confirmation record in DB
- [ ] Write unit tests with mocked Gmail inbox

---

## 9. Phase 4: Web Form Automation Engine (Week 4-6)

### TASK-031: Browser Session Manager
**Estimate:** 1 day  
**Depends on:** TASK-022

- [ ] Implement `BrowserSessionManager`
- [ ] Remote driver creation (Selenium Grid)
- [ ] Stealth JS patches application
- [ ] Session recycling after N tasks
- [ ] Session timeout handling
- [ ] Write integration tests against local Grid

### TASK-032: Form Field Mapper
**Estimate:** 1.5 days  
**Depends on:** TASK-031

- [ ] Implement `FormFieldMapper.discover_fields(driver)`
- [ ] Implement all field name normalization patterns
- [ ] Implement label-based field detection
- [ ] Add aria-label support
- [ ] Add Redis schema caching
- [ ] Write tests with mock DOM (`mock_form_page.html`)

### TASK-033: Human-Like Interaction Utilities
**Estimate:** 0.5 day  
**Depends on:** TASK-031

- [ ] Implement `human_type(element, text)`
- [ ] Implement `human_click(driver, element)`
- [ ] Implement `scroll_to_element(driver, element)`
- [ ] Add configurable random delay ranges
- [ ] Write unit tests

### TASK-034: File Upload Handler
**Estimate:** 1 day  
**Depends on:** TASK-032, TASK-033

- [ ] Implement `FileUploadHandler.download_to_temp(url)` 
- [ ] Implement `FileUploadHandler.upload_to_form(element, path)`
- [ ] Add temp file cleanup on success and failure
- [ ] Handle alternative upload methods (drag-and-drop)
- [ ] Write integration tests

### TASK-035: CAPTCHA Detection & Solver
**Estimate:** 1.5 days  
**Depends on:** TASK-031

- [ ] Implement `detect_captcha(driver)` for reCAPTCHA and hCaptcha
- [ ] Implement 2captcha API client
- [ ] Implement CAPTCHA token injection into form
- [ ] Implement "flag for manual review" path
- [ ] Write unit tests with mocked 2captcha responses

### TASK-036: Confirmation Page Parser
**Estimate:** 1 day  
**Depends on:** TASK-031

- [ ] Implement `ConfirmationPageParser.extract_confirmation(driver)`
- [ ] Detect success indicators: URL change, success text, application ID
- [ ] Handle ambiguous state (applied but no clear confirmation)
- [ ] Write tests with mock confirmation HTML

### TASK-037: Screenshot Evidence System
**Estimate:** 0.5 day  
**Depends on:** TASK-031

- [ ] Implement `capture_screenshot(driver, app_id, label, storage_client)`
- [ ] PNG → WebP conversion and compression
- [ ] S3 upload
- [ ] Write unit tests

### TASK-038: Generic Web Form Adapter
**Estimate:** 2 days  
**Depends on:** TASK-032, TASK-033, TASK-034, TASK-035, TASK-036, TASK-037

- [ ] Implement `GenericAdapter` implementing full W1–W9 flow
- [ ] Integrate all sub-components
- [ ] Handle all error cases with proper recovery
- [ ] Write integration tests against local form server

### TASK-039: Platform-Specific Adapters
**Estimate:** 3 days  
**Depends on:** TASK-038

- [ ] Implement `LinkedInAdapter` (Easy Apply flow)
- [ ] Implement `GreenhouseAdapter` (Greenhouse ATS)
- [ ] Implement `LeverAdapter` (Lever ATS)
- [ ] Implement `IndeedAdapter` (Indeed Quick Apply)
- [ ] Write at least smoke tests per adapter (using mock pages)

### TASK-040: Adapter Registry & Auto-Selection
**Estimate:** 0.5 day  
**Depends on:** TASK-039

- [ ] Implement `AdapterRegistry.get_adapter(url)` — domain-based selection
- [ ] Register all platform adapters
- [ ] Default to `GenericAdapter` for unknown domains
- [ ] Write unit tests

### TASK-041: Web Form Celery Task
**Estimate:** 1 day  
**Depends on:** TASK-040

- [ ] Implement `apply_via_webform(application_id)` Celery task
- [ ] Add retry policy per `retry_and_error_strategy.md`
- [ ] Integrate circuit breaker
- [ ] Write integration tests

---

## 10. Phase 5: Confirmation Capture System (Week 5-6)

### TASK-042: Confirmation Storage Service
**Estimate:** 0.5 day  
**Depends on:** TASK-007, TASK-008

- [ ] Implement `ConfirmationService.save(application_id, type, data)`
- [ ] Implement `ConfirmationService.get_all(application_id)` 
- [ ] Write integration tests

### TASK-043: Reference Number Extractor
**Estimate:** 1 day  
**Depends on:** TASK-042

- [ ] Implement regex patterns for common application ID formats
- [ ] Extract from page text, email body
- [ ] Normalize extracted IDs
- [ ] Write unit tests with sample confirmation texts

---

## 11. Phase 5: Application Tracking System (Week 5-6)

### TASK-044: Status Manager Service
**Estimate:** 1 day  
**Depends on:** TASK-007, TASK-008

- [ ] Implement `StatusManager.transition(application_id, new_status, reason)`
- [ ] Enforce valid status transitions (state machine)
- [ ] Auto-log to `application_status_history`
- [ ] Emit Redis Pub/Sub event for WebSocket
- [ ] Write unit tests for state machine

### TASK-045: Application Search & Filter Service
**Estimate:** 1 day  
**Depends on:** TASK-014

- [ ] Implement cursor-based pagination
- [ ] Implement all filter options (status, date, company, method)
- [ ] Optimize DB queries with proper use of indexes
- [ ] Write performance tests

---

## 12. Phase 6: Circuit Breaker & Alerting (Week 6)

### TASK-046: Circuit Breaker Implementation
**Estimate:** 1 day  
**Depends on:** TASK-010

- [ ] Implement `CircuitBreaker` class per `retry_and_error_strategy.md`
- [ ] Integrate with Email and Web Form systems
- [ ] Write unit tests for all state transitions

### TASK-047: Alert Dispatcher
**Estimate:** 1 day  
**Depends on:** TASK-044

- [ ] Implement `AlertDispatcher.send(alert)` 
- [ ] Slack webhook integration
- [ ] User email notification
- [ ] Severity-based routing
- [ ] Write unit tests

---

## 13. Phase 7: Integration (Week 7)

### TASK-048: Orchestrator Webhook Integration
**Estimate:** 1 day  
**Depends on:** All core tasks

- [ ] Implement `OrchestratorClient.notify_result(application_id, result)`
- [ ] Add retry logic for webhook delivery
- [ ] Add signature verification (HMAC)
- [ ] Write integration tests

### TASK-049: Job Verification Agent Integration
**Estimate:** 0.5 day  
**Depends on:** TASK-019

- [ ] Replace stub with real API client to Job Verification Agent
- [ ] Define and document the cross-agent API contract
- [ ] Write integration tests with mock verification service

### TASK-050: Storage Service Integration
**Estimate:** 0.5 day  
**Depends on:** TASK-034, TASK-037

- [ ] Implement `StorageClient` (AWS S3 / GCS / MinIO)
- [ ] Implement `upload(key, data)` and `download(url)` methods
- [ ] Add presigned URL support
- [ ] Write integration tests

---

## 14. Phase 8: Testing & QA (Week 7-8)

### TASK-051: Complete Unit Test Suite
**Estimate:** 2 days  
**Depends on:** All implementation tasks

- [ ] Achieve ≥ 85% line coverage across all modules
- [ ] Cover all error paths and edge cases
- [ ] Run `pytest --cov` and review report

### TASK-052: Integration Test Suite
**Estimate:** 1.5 days  
**Depends on:** TASK-051

- [ ] All integration tests pass against local Docker stack
- [ ] Test database migrations run cleanly
- [ ] Test Celery task execution end-to-end

### TASK-053: E2E Test Suite
**Estimate:** 1 day  
**Depends on:** TASK-038

- [ ] E2E email test with sandbox SMTP
- [ ] E2E web form test with local form server
- [ ] Verify screenshot capture works in headless Chrome

### TASK-054: Load Testing
**Estimate:** 1 day  
**Depends on:** TASK-052

- [ ] Write Locust test plan
- [ ] Run 100 submissions/minute test
- [ ] Verify no memory leaks after 10 minutes
- [ ] Document performance baseline

---

## 15. Phase 9: Deployment (Week 8)

### TASK-055: Dockerfiles
**Estimate:** 0.5 day  
**Depends on:** All implementation tasks

- [ ] Write `Dockerfile` for FastAPI service
- [ ] Write `Dockerfile.worker` for Celery workers
- [ ] Optimize image size (multi-stage builds)
- [ ] Add security scanning with `trivy`

### TASK-056: CI/CD Pipeline
**Estimate:** 1 day  
**Depends on:** TASK-055

- [ ] Write GitHub Actions workflow (unit → integration → security → build → e2e)
- [ ] Add Docker image push to registry
- [ ] Add automatic deployment to staging on `main`

### TASK-057: Observability Setup
**Estimate:** 1 day  
**Depends on:** TASK-055

- [ ] Configure Datadog agent or Prometheus metrics endpoint
- [ ] Create dashboard: application success rate, retry rate, DLQ size, latency
- [ ] Define alert rules in Datadog/PagerDuty
- [ ] Test alerting end-to-end

### TASK-058: Documentation & Handoff
**Estimate:** 0.5 day  
**Depends on:** All tasks

- [ ] Update all planning docs with any implementation changes
- [ ] Write `README.md` for `member_04/` module
- [ ] Write `RUNBOOK.md` for operations (how to drain queue, handle DLQ, etc.)
- [ ] Record demo video of full pipeline

---

## 16. Total Estimate Summary

| Phase | Days | Key Deliverable |
|-------|------|----------------|
| 0: Foundation | 2 | Project + infra up and running |
| 1: Data Layer | 3 | DB schema deployed, models ready |
| 2: Core APIs | 4 | All REST endpoints functional |
| 3: Guardrails + Celery | 3 | Rate limiting, approval, task queue |
| 3: Email System | 4 | Email applications working |
| 4: Web Automation | 8 | Web form automation working |
| 5: Tracking + Confirmation | 3 | Full tracking + evidence capture |
| 6: Circuit Breaker + Alerts | 2 | Resilience + observability |
| 7: Integration | 2 | Connected to other agents |
| 8: Testing & QA | 5.5 | Full test suite passing |
| 9: Deployment | 3.5 | Deployed, monitored, documented |
| **TOTAL** | **~40 days** | **Production-ready module** |

---

## 17. Task Priority Matrix

```
                HIGH IMPACT        LOW IMPACT
                ────────────────────────────
HIGH            │ TASK-007 (DB)  │ TASK-039  │
URGENCY         │ TASK-013 (API) │ TASK-043  │
                │ TASK-029 (Email│ TASK-037  │
                │ TASK-041 (Form)│           │
                ────────────────────────────
LOW             │ TASK-018 (RL)  │ TASK-057  │
URGENCY         │ TASK-048 (Hook)│ TASK-058  │
                │ TASK-046 (CB)  │           │
                ────────────────────────────
```

**CRITICAL PATH:** TASK-001 → 002 → 005 → 007 → 008 → 013 → 022 → 025 → 029 → 041 → 048

---

*This task breakdown is the implementation contract. No task should begin implementation until this plan is reviewed and approved by the team.*
