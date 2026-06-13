# Member 4 — Application Automation Agent (Execution Layer)
## AI Career Assistant Multi-Agent System

The **Application Automation Agent** acts as the robust execution engine of the AI Career Assistant platform. It processes job applications through two distinct channels: **Email-based Applications** (Gmail OAuth2 / SMTP fallbacks) and **Web Form Automation** (Selenium WebDriver with stealth injection, dynamic DOM field mapping, and 2captcha solver). The engine is governed by a strict state-machine tracker, fine-grained Role-Based Access Control (RBAC), Multi-Factor Authentication (MFA), and a resilient retry/replay system.

---

## 🏗️ System Architecture & Integrations

The Application Automation Agent integrates with the Orchestrator, PostgreSQL database, and Redis cache/queue, using Celery workers to handle async headless browser runs.

```mermaid
graph TD
    subgraph Client/Orchestrator
        Orchestrator[Orchestrator / Client]
        Dashboard[Web Dashboard]
    end

    subgraph API Gateway (FastAPI)
        router[FastAPI Server - Port 8004]
        auth[Auth & MFA Service]
        rbac[RBAC Guard]
        app_api[Application API Router]
        hitl_api[HITL Approval Queue]
        replay_api[Execution Replay Viewer]
    end

    subgraph Cache & Task Queue
        redis_broker[(Redis 7)]
        celery_worker[Celery Worker - P solo]
    end

    subgraph Relational Storage
        postgres[(PostgreSQL 16)]
    end

    subgraph Third-Party Integrations
        gmail[Gmail API OAuth2 / SMTP]
        selenium_grid[Selenium Headless Driver]
        captcha[2captcha API solver]
    end

    Orchestrator -->|POST /submit| app_api
    Dashboard -->|GET /replay| replay_api
    Dashboard -->|POST /approve| hitl_api

    app_api -->|Write Job Metadata| postgres
    app_api -->|Push Task| redis_broker
    celery_worker -->|Fetch Task| redis_broker

    celery_worker -->|Check Allowlists| postgres
    celery_worker -->|Execute Form Application| selenium_grid
    celery_worker -->|Solve Captcha| captcha
    celery_worker -->|Send Email App| gmail

    auth -->|Validate MFA & Token Replay| redis_broker
    auth -->|User/Role Management| postgres
```

---

## ⚙️ Environment Setup

### Prerequisites
* **Python**: 3.11+
* **PostgreSQL**: 16+
* **Redis**: 7+
* **Google Chrome / ChromeDriver**: (Required if checking local worker browser integrations; headless execution is default)

### 1. Installation
Clone the repository and prepare the virtual environment:
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment (Windows)
.venv\Scripts\Activate.ps1

# Upgrade pip and install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

### 2. Configuration (`.env`)
Create a `.env` file in the root directory. Use the template below:
```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/member04_dev
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=super_secure_jwt_secret_key_change_in_production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
MFA_TOTP_ISSUER=AICareerAssistant

# Third Party Integrations
GMAIL_CLIENT_ID=your-gmail-oauth2-client-id
GMAIL_CLIENT_SECRET=your-gmail-oauth2-client-secret
GMAIL_REFRESH_TOKEN=your-gmail-oauth2-refresh-token
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-specific-password

TWOCAPTCHA_API_KEY=your-2captcha-api-key
```

---

## 🚀 Runtimes & Execution Commands

### 1. Database Migrations
Apply Alembic schemas to setup the PostgreSQL tables:
```powershell
alembic upgrade head
```

### 2. Seed Security & RBAC Roles
Seed the foundational roles (`admin`, `operator`, `auditor`, `user`) and access policies:
```powershell
python scripts/seed_rbac.py
```

### 3. Launch the API Server
Start the Uvicorn application on port 8004:
```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8004 --reload
```

### 4. Run the Celery Async Task Worker
For Windows compatibility, run the worker in synchronous/solo execution pool mode to prevent deadlocks:
```powershell
.venv\Scripts\celery.exe -A app.tasks.celery_app.celery_app worker --loglevel=info -P solo
```

---

## 🧪 Pipeline Validation & Testing

Run these tools to verify stack integrity, schema status, and security compliance.

### 1. Full Preflight Health Check
Verify local service availability (DB, Redis, RBAC seeding, and Celery connectivity):
```powershell
python scripts/healthcheck.py --no-chrome
```

### 2. Test Suite Execution
Execute 285 unit and integration tests:
```powershell
.venv\Scripts\pytest
```

### 3. Golden Path Flow Validation
Executes registration, login, MFA registration/verification, application submission, audit checks, and RBAC enforcement sequentially:
```powershell
python scripts/golden_path_validation.py
```

### 4. End-to-End Pipeline Validation Script
Validates the entire automation pipeline, checking state transitions, soft deletes, and response status changes:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/validate_pipeline.ps1 -SkipDockerBuild -VerboseOutput
```

---

## 🛡️ Security Engine & Key Features

### 1. Multi-Factor Authentication (MFA)
* **Enrollment**: Users trigger `/api/v1/auth/mfa/setup` to receive a QR code URI and secret key.
* **Verification**: Verifies TOTP tokens over the standard window. MFA supports backward compatibility for both `code` and `totp_token` inputs.
* **Replay Protection**: Prevents token reuse. Once a TOTP token is verified, it is registered in Redis with a 90-second expiration. Attempting to submit the same token again will fail verification.
* **Backup Codes**: Generates 10 secure backup codes upon setup. When a backup code is consumed, it is hashed, recorded, and deleted from the active list.

### 2. Role-Based Access Control (RBAC)
The API implements fine-grained security policies:
* **Roles**:
  * `admin`: Has global access.
  * `operator`: Handles operational duties (`approve_execution`, `cancel_execution`, `manage_queues`, `view_replay`).
  * `auditor`: Has access to read metadata and audit trails (`view_audits`, `view_replay`).
  * `user`: Basic actions (`submit_applications`, view their own applications).
* **Policy Enforcement**: Custom dependencies (`RequiresRole`, `RequiresPermission`) intercept incoming HTTP routes and evaluate whether the user's role grants access to the specified resource scope.

### 3. Resilient Retries & Execution Replay Viewer
* **Automated Retry Flow**: Users or administrators can trigger `/api/v1/applications/{id}/retry`. If an application fails due to transient reasons (e.g. rate limit, browser crash), a retry is queued without duplicating database records or bypassing security filters.
* **State Machine Boundaries**: Prevents invalid changes (e.g. moving from `FAILED` directly to `PROCESSING` is blocked; a retry will correctly route state back through `QUEUED`).
* **Execution Replay Viewer**: Access `/api/v1/applications/{id}/replay` to review trace files, DOM screenshots, and steps executed during a headless Selenium browser run. This supports auditing and interactive troubleshooting.

### 4. Human-In-The-Loop (HITL) Queue
* When a form requires manual verification, a CAPTCHA solver is blocked, or verification fails, the task state switches to `PENDING_APPROVAL`.
* The application is queued in the HITL dashboard. Operators can view, edit, approve, or cancel pending executions using `/api/v1/approvals/...`.
* **Escalations**: If an application remains in `PENDING_APPROVAL` past the defined timeout window, the system triggers alerts or escalates the record status, shifting state to prevent pipeline starvation.

---

## 🛸 CI/CD Pipeline Overview

The CI/CD pipeline validates every code change automatically:
1. **Linter & Formatting**: Enforces code consistency via `ruff` and `black`.
2. **Preflight Validation**: Runs `pytest` to ensure unit, integration, and security checks are clean.
3. **Container Build**: Tests Dockerfile building using Multi-stage recipes.
4. **Integration Testing**: Boots PostgreSQL and Redis containers to perform integration validations and verify Alembic migrations.
