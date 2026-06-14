# Database Schema — Member 4: Application Automation Agent
**Project:** AI Career Assistant Multi-Agent System 2026  
**Module Owner:** Member 4  
**Status:** Planning Phase  
**Last Updated:** 2026-06-12  
**Database:** PostgreSQL 16+  

---

## 1. Schema Design Principles

1. **UUID primary keys** — portable, avoids ID enumeration attacks
2. **`created_at` / `updated_at` on every table** — full audit trail
3. **JSONB for flexible metadata** — accommodates per-platform variation
4. **Soft deletes** — never hard-delete application records
5. **Status as ENUM** — enforces valid states at DB level
6. **Foreign key constraints** — referential integrity throughout
7. **Indexes on query-hot columns** — optimized for dashboard and API reads

---

## 2. Entity Relationship Diagram

```
users
  └──< applications
              ├── job_id (FK → jobs)
              ├── resume_version_id (FK → resume_versions)
              ├── cover_letter_version_id (FK → cover_letter_versions)
              ├──< application_status_history
              ├──< confirmations
              ├──< application_logs
              └──< retry_attempts

email_sends
  └── application_id (FK → applications)

form_submissions
  └── application_id (FK → applications)

form_schemas (cache)
  └── site_domain

rate_limit_counters
  └── user_id

approval_requests
  └── application_id (FK → applications)
```

---

## 3. Complete DDL

### 3.1 ENUM Types

```sql
-- Application lifecycle states
CREATE TYPE application_status AS ENUM (
    'queued',               -- Received, not yet processing
    'pending_approval',     -- Waiting for user manual approval
    'processing',           -- Celery task is executing
    'applied',              -- Successfully submitted
    'captcha_required',     -- Blocked by CAPTCHA, awaiting resolve
    'failed',               -- All retries exhausted
    'duplicate',            -- Already applied to this job
    'limit_exceeded',       -- Daily cap hit
    'expired',              -- Job deadline passed
    'asset_error',          -- Could not download resume/cover letter
    'rejected',             -- Employer rejected (from email/manual update)
    'interview',            -- Interview scheduled (from email/manual update)
    'accepted'              -- Offer received (from email/manual update)
);

-- Application submission method
CREATE TYPE application_method AS ENUM (
    'email',
    'web_form',
    'linkedin_easy_apply',
    'ats_portal',
    'manual'
);

-- Confirmation evidence type
CREATE TYPE confirmation_type AS ENUM (
    'email_acknowledgement',
    'form_success_message',
    'screenshot',
    'application_id_extracted',
    'manual_confirmation'
);

-- Email send status
CREATE TYPE email_send_status AS ENUM (
    'pending',
    'sent',
    'delivered',
    'bounced',
    'failed'
);
```

---

### 3.2 Core Tables

```sql
-- ============================================================
-- APPLICATIONS (central tracking table)
-- ============================================================
CREATE TABLE applications (
    application_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL,              -- FK to users service (external)
    job_id                  UUID NOT NULL,              -- FK to jobs table (from Job Agent)
    
    -- Job context snapshot (denormalized for resilience)
    company_name            VARCHAR(255) NOT NULL,
    role_title              VARCHAR(255) NOT NULL,
    platform                VARCHAR(100),               -- 'linkedin', 'indeed', 'greenhouse', etc.
    application_url         TEXT,                       -- URL submitted to (if web form)
    contact_email           VARCHAR(255),               -- Email sent to (if email method)
    
    -- Method & status
    method                  application_method NOT NULL,
    status                  application_status NOT NULL DEFAULT 'queued',
    
    -- Asset versions (snapshotted at application time)
    resume_version_id       UUID NOT NULL,
    cover_letter_version_id UUID,
    
    -- Timing
    queued_at               TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    applied_at              TIMESTAMP WITH TIME ZONE,   -- When submission confirmed
    deadline                TIMESTAMP WITH TIME ZONE,   -- Job application deadline
    
    -- Confirmation
    confirmation_id         VARCHAR(255),               -- Platform-issued ID if available
    
    -- Guardrail flags
    manual_approval_required BOOLEAN NOT NULL DEFAULT FALSE,
    approved_at             TIMESTAMP WITH TIME ZONE,
    approved_by             VARCHAR(100),               -- 'user' or 'auto'
    
    -- Retry tracking
    retry_count             INTEGER NOT NULL DEFAULT 0,
    max_retries             INTEGER NOT NULL DEFAULT 3,
    next_retry_at           TIMESTAMP WITH TIME ZONE,
    
    -- Soft delete
    deleted_at              TIMESTAMP WITH TIME ZONE,
    
    -- Audit
    created_at              TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Flexible metadata (platform-specific fields)
    metadata                JSONB DEFAULT '{}',
    
    CONSTRAINT uq_user_job UNIQUE (user_id, job_id),
    CONSTRAINT chk_retry_count CHECK (retry_count >= 0),
    CONSTRAINT chk_max_retries CHECK (max_retries > 0)
);

-- Indexes for common queries
CREATE INDEX idx_applications_user_id ON applications(user_id);
CREATE INDEX idx_applications_status ON applications(status);
CREATE INDEX idx_applications_applied_at ON applications(applied_at DESC NULLS LAST);
CREATE INDEX idx_applications_company ON applications(company_name);
CREATE INDEX idx_applications_user_status ON applications(user_id, status);
CREATE INDEX idx_applications_next_retry ON applications(next_retry_at) 
    WHERE next_retry_at IS NOT NULL;
CREATE INDEX idx_applications_metadata ON applications USING GIN(metadata);
```

---

```sql
-- ============================================================
-- APPLICATION STATUS HISTORY (full audit log of state changes)
-- ============================================================
CREATE TABLE application_status_history (
    history_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id  UUID NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
    
    from_status     application_status,             -- NULL for initial state
    to_status       application_status NOT NULL,
    reason          TEXT,                           -- Human-readable reason for change
    changed_by      VARCHAR(100) DEFAULT 'system',  -- 'system', 'user', 'admin'
    
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_status_history_app_id ON application_status_history(application_id);
CREATE INDEX idx_status_history_created_at ON application_status_history(created_at DESC);
```

---

```sql
-- ============================================================
-- EMAIL SENDS (log of every email sent)
-- ============================================================
CREATE TABLE email_sends (
    email_send_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id      UUID NOT NULL REFERENCES applications(application_id),
    
    -- Send details
    from_address        VARCHAR(255) NOT NULL,
    to_address          VARCHAR(255) NOT NULL,
    subject             TEXT NOT NULL,
    body_preview        TEXT,                       -- First 500 chars of body
    
    -- Attachments
    resume_filename     VARCHAR(255),
    cover_letter_filename VARCHAR(255),
    
    -- Status
    status              email_send_status NOT NULL DEFAULT 'pending',
    provider            VARCHAR(50),                -- 'gmail_api', 'smtp'
    message_id          VARCHAR(255),               -- Provider-issued message ID
    
    -- Timestamps
    sent_at             TIMESTAMP WITH TIME ZONE,
    delivered_at        TIMESTAMP WITH TIME ZONE,
    
    -- Error info
    error_code          VARCHAR(50),
    error_message       TEXT,
    
    -- Retry
    attempt_number      INTEGER NOT NULL DEFAULT 1,
    
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_email_sends_application_id ON email_sends(application_id);
CREATE INDEX idx_email_sends_status ON email_sends(status);
CREATE INDEX idx_email_sends_message_id ON email_sends(message_id) WHERE message_id IS NOT NULL;
```

---

```sql
-- ============================================================
-- FORM SUBMISSIONS (log of every web form submission)
-- ============================================================
CREATE TABLE form_submissions (
    submission_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id      UUID NOT NULL REFERENCES applications(application_id),
    
    -- Target
    form_url            TEXT NOT NULL,
    site_domain         VARCHAR(255) NOT NULL,
    platform_adapter    VARCHAR(100),               -- 'generic', 'linkedin', 'greenhouse', etc.
    
    -- Execution
    started_at          TIMESTAMP WITH TIME ZONE,
    completed_at        TIMESTAMP WITH TIME ZONE,
    duration_seconds    NUMERIC(6,2),
    
    -- Fields
    fields_detected     INTEGER DEFAULT 0,
    fields_filled       INTEGER DEFAULT 0,
    fields_failed       JSONB DEFAULT '[]',         -- Array of { field, error }
    
    -- Outcome
    success             BOOLEAN,
    success_indicator   VARCHAR(100),               -- 'url_change', 'success_message', etc.
    confirmation_text   TEXT,                       -- Raw success message from page
    
    -- Evidence
    pre_submit_screenshot_url   TEXT,
    confirmation_screenshot_url TEXT,
    
    -- Error
    error_type          VARCHAR(100),
    error_message       TEXT,
    captcha_encountered BOOLEAN DEFAULT FALSE,
    captcha_solved      BOOLEAN DEFAULT FALSE,
    
    -- Retry
    attempt_number      INTEGER NOT NULL DEFAULT 1,
    
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_form_submissions_application_id ON form_submissions(application_id);
CREATE INDEX idx_form_submissions_domain ON form_submissions(site_domain);
CREATE INDEX idx_form_submissions_success ON form_submissions(success);
```

---

```sql
-- ============================================================
-- CONFIRMATIONS (evidence of successful applications)
-- ============================================================
CREATE TABLE confirmations (
    confirmation_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id      UUID NOT NULL REFERENCES applications(application_id),
    
    -- Evidence type
    type                confirmation_type NOT NULL,
    
    -- Confirmation data
    external_ref_id     VARCHAR(255),               -- Platform-issued application ID
    raw_content         TEXT,                       -- Raw email body or page text
    evidence_url        TEXT,                       -- S3 URL to screenshot/email copy
    
    -- Source metadata
    source_url          TEXT,                       -- Where confirmation was captured
    source_email        VARCHAR(255),               -- If came via email
    
    -- Timing
    captured_at         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Structured data extracted
    extracted_data      JSONB DEFAULT '{}',         -- { app_id, ref_number, next_steps, etc. }
    
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_confirmations_application_id ON confirmations(application_id);
CREATE INDEX idx_confirmations_type ON confirmations(type);
```

---

```sql
-- ============================================================
-- RETRY ATTEMPTS (track each retry attempt in detail)
-- ============================================================
CREATE TABLE retry_attempts (
    retry_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id      UUID NOT NULL REFERENCES applications(application_id),
    
    attempt_number      INTEGER NOT NULL,
    method              application_method NOT NULL,
    
    started_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMP WITH TIME ZONE,
    
    outcome             VARCHAR(50),                -- 'success', 'failed', 'in_progress'
    error_code          VARCHAR(100),
    error_message       TEXT,
    error_stack_trace   TEXT,
    
    -- Backoff
    next_retry_delay_seconds INTEGER,
    
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_retry_attempts_application_id ON retry_attempts(application_id);
```

---

```sql
-- ============================================================
-- FORM SCHEMAS CACHE (discovered form field mappings per site)
-- ============================================================
CREATE TABLE form_schemas (
    schema_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_domain         VARCHAR(255) NOT NULL UNIQUE,
    
    -- Discovered schema (field name → CSS selector / XPath)
    field_map           JSONB NOT NULL DEFAULT '{}',
    
    -- Health tracking
    last_verified_at    TIMESTAMP WITH TIME ZONE,
    success_count       INTEGER DEFAULT 0,
    failure_count       INTEGER DEFAULT 0,
    is_active           BOOLEAN DEFAULT TRUE,
    
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_form_schemas_domain ON form_schemas(site_domain);
CREATE INDEX idx_form_schemas_active ON form_schemas(is_active) WHERE is_active = TRUE;
```

---

```sql
-- ============================================================
-- APPROVAL REQUESTS (manual review queue)
-- ============================================================
CREATE TABLE approval_requests (
    request_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id      UUID NOT NULL REFERENCES applications(application_id),
    user_id             UUID NOT NULL,
    
    -- Request details
    requested_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW() + INTERVAL '24 hours',
    
    -- Resolution
    resolved_at         TIMESTAMP WITH TIME ZONE,
    decision            VARCHAR(20),                -- 'approved', 'rejected'
    decision_reason     TEXT,
    decided_by          VARCHAR(100),               -- 'user', 'auto_expired'
    
    -- Token for secure approval URL
    approval_token      VARCHAR(64) UNIQUE NOT NULL DEFAULT encode(gen_random_bytes(32), 'hex'),
    
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_approval_requests_user_id ON approval_requests(user_id);
CREATE INDEX idx_approval_requests_app_id ON approval_requests(application_id);
CREATE INDEX idx_approval_requests_token ON approval_requests(approval_token);
CREATE INDEX idx_approval_requests_pending ON approval_requests(expires_at) 
    WHERE decision IS NULL;
```

---

```sql
-- ============================================================
-- APPLICATION LOGS (structured event log per application)
-- ============================================================
CREATE TABLE application_logs (
    log_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id      UUID NOT NULL REFERENCES applications(application_id),
    
    level               VARCHAR(10) NOT NULL,       -- 'INFO', 'WARN', 'ERROR', 'DEBUG'
    event               VARCHAR(100) NOT NULL,       -- e.g. 'email.sent', 'form.field_filled'
    message             TEXT NOT NULL,
    
    -- Structured context
    context             JSONB DEFAULT '{}',
    
    -- Tracing
    trace_id            VARCHAR(64),
    
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (created_at);

-- Partition by month for log retention management
CREATE TABLE application_logs_2026_06 
    PARTITION OF application_logs 
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

CREATE INDEX idx_app_logs_application_id ON application_logs(application_id);
CREATE INDEX idx_app_logs_created_at ON application_logs(created_at DESC);
CREATE INDEX idx_app_logs_level ON application_logs(level) WHERE level IN ('WARN', 'ERROR');
```

---

### 3.3 Trigger: Auto-Update `updated_at`

```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_applications_updated_at
    BEFORE UPDATE ON applications
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_email_sends_updated_at
    BEFORE UPDATE ON email_sends
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

---

## 4. Redis Key Design

```
# Daily application counter per user
rate:daily:{user_id}:{YYYYMMDD}     → INTEGER (TTL: 48h)

# Deduplication check
dedup:applied:{user_id}:{job_id}    → "1" (TTL: 90 days)

# Form schema cache
form_schema:{site_domain}           → JSON (TTL: 7 days)

# Celery task dedup
celery:task:apply:{application_id}  → task_id (TTL: 24h)

# Pending CAPTCHA jobs
captcha:pending:{application_id}    → JSON (TTL: 4h)

# Session pool tracking
selenium:sessions:available         → SET of session_ids
selenium:sessions:busy              → SET of session_ids
```

---

## 5. Migration Strategy

```
migrations/
├── 001_create_enums.sql
├── 002_create_applications.sql
├── 003_create_application_status_history.sql
├── 004_create_email_sends.sql
├── 005_create_form_submissions.sql
├── 006_create_confirmations.sql
├── 007_create_retry_attempts.sql
├── 008_create_form_schemas.sql
├── 009_create_approval_requests.sql
├── 010_create_application_logs.sql
├── 011_create_triggers.sql
└── 012_create_indexes.sql
```

Tool: **Alembic** for Python-managed migrations.

---

## 6. Data Retention Policy

| Table | Retention | Action |
|-------|-----------|--------|
| `applications` | 2 years | Soft delete, then archive |
| `application_logs` | 90 days | Drop old partitions |
| `email_sends` | 1 year | Archive to cold storage |
| `form_submissions` | 6 months | Archive screenshots to Glacier |
| `confirmations` | 2 years | Keep full record |
| `retry_attempts` | 90 days | Auto-delete |
| `form_schemas` | Indefinite | Manual cleanup |
| `approval_requests` | 90 days | Auto-delete resolved |

---

*Next Document: `api_contracts.md` — REST API endpoint specifications*
