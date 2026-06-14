# Testing Strategy — Member 4: Application Automation Agent
**Project:** AI Career Assistant Multi-Agent System 2026  
**Module Owner:** Member 4  
**Status:** Planning Phase  
**Last Updated:** 2026-06-12  

---

## 1. Testing Philosophy

Automation systems that interact with external websites are notoriously hard to test. This strategy addresses:

- **Fast feedback loops** — Unit tests run in <5 seconds total
- **Isolation from external services** — No real emails sent, no real browsers in unit tests
- **Realistic integration tests** — Use controlled test sites and sandboxes
- **Deterministic E2E tests** — Mock external dependencies for reliable CI
- **Coverage of failure paths** — Error handling, retries, and edge cases tested as rigorously as happy paths

---

## 2. Testing Pyramid

```
                    ┌─────────────────┐
                    │    E2E Tests    │  (5%)
                    │  Slow, brittle  │
                    │  Full pipeline  │
                   ╱└─────────────────╲
                  ╱ ┌───────────────┐  ╲
                 ╱  │ Integration   │   ╲
                ╱   │    Tests      │    ╲
               ╱    │ (30%)         │     ╲
              ╱     └───────────────┘      ╲
             ╱  ┌─────────────────────────┐  ╲
            ╱   │      Unit Tests         │    ╲
           ╱    │         (65%)           │     ╲
          ╱     │   Fast, isolated        │      ╲
         ╱      └─────────────────────────┘       ╲
```

---

## 3. Unit Tests

**Framework:** pytest + pytest-asyncio  
**Mocking:** unittest.mock, pytest-mock, responses  
**Target coverage:** ≥ 85% line coverage  

### 3.1 Test Structure

```
tests/
├── unit/
│   ├── test_input_validation.py
│   ├── test_guardrails.py
│   ├── test_route_selector.py
│   ├── test_email_system.py
│   ├── test_form_field_mapper.py
│   ├── test_confirmation_capture.py
│   ├── test_retry_logic.py
│   ├── test_circuit_breaker.py
│   ├── test_tracking_system.py
│   └── test_security.py
│
├── integration/
│   ├── test_email_integration.py
│   ├── test_webform_integration.py
│   ├── test_database_operations.py
│   ├── test_celery_tasks.py
│   └── test_redis_operations.py
│
├── e2e/
│   ├── test_full_email_pipeline.py
│   └── test_full_webform_pipeline.py
│
└── fixtures/
    ├── sample_application.json
    ├── sample_job_metadata.json
    ├── mock_form_page.html
    ├── mock_confirmation_page.html
    └── fake_resume.pdf
```

### 3.2 Key Unit Test Cases

#### Input Validation Tests

```python
class TestInputValidation:
    
    def test_valid_email_application_passes(self):
        request = build_valid_email_request()
        assert validate_application_request(request) is True
    
    def test_missing_contact_email_for_email_method_fails(self):
        request = build_valid_email_request()
        request.job_metadata.contact_email = None
        with pytest.raises(ValidationError, match="contact_email required"):
            validate_application_request(request)
    
    def test_invalid_resume_url_domain_fails(self):
        request = build_valid_email_request()
        request.resume.storage_url = "https://evil.com/resume.pdf"
        with pytest.raises(ValidationError, match="approved storage provider"):
            validate_application_request(request)
    
    def test_path_traversal_in_filename_fails(self):
        request = build_valid_email_request()
        request.resume.filename = "../../etc/passwd"
        with pytest.raises(ValidationError, match="Invalid filename"):
            validate_application_request(request)
    
    def test_non_pdf_resume_fails(self):
        request = build_valid_email_request()
        request.resume.filename = "resume.exe"
        with pytest.raises(ValidationError, match="must be PDF"):
            validate_application_request(request)
```

#### Guardrails Tests

```python
class TestGuardrails:
    
    @pytest.mark.asyncio
    async def test_daily_limit_enforced(self, redis_mock):
        redis_mock.get.return_value = "50"   # User at limit
        with pytest.raises(RateLimitExceededError):
            await check_daily_limit(user_id="test-user", limit=50)
    
    @pytest.mark.asyncio
    async def test_daily_limit_not_exceeded(self, redis_mock):
        redis_mock.get.return_value = "12"   # User under limit
        result = await check_daily_limit(user_id="test-user", limit=50)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_unverified_job_raises(self, db_mock):
        db_mock.fetchone.return_value = None
        with pytest.raises(UnverifiedJobError):
            await verify_job_is_approved(job_id="fake-job-id")
    
    @pytest.mark.asyncio
    async def test_duplicate_application_detected(self, db_mock):
        db_mock.fetchone.return_value = {"status": "applied"}
        with pytest.raises(DuplicateApplicationError):
            await check_for_duplicate(user_id="u1", job_id="j1")
```

#### Retry Logic Tests

```python
class TestRetryLogic:
    
    def test_backoff_increases_exponentially(self):
        delays = [calculate_backoff(i, jitter=False) for i in range(1, 6)]
        # Each delay should be roughly double the previous
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i-1]
    
    def test_backoff_capped_at_max_delay(self):
        delay = calculate_backoff(attempt=100, max_delay=300.0, jitter=False)
        assert delay == 300.0
    
    def test_jitter_produces_different_values(self):
        delays = [calculate_backoff(1, jitter=True) for _ in range(100)]
        assert len(set(delays)) > 1  # Not all same value
    
    def test_permanent_error_does_not_retry(self, celery_task_mock):
        with pytest.raises(PermanentError):
            apply_via_email.apply(
                args=["app-id"],
                throw=True
            )
        assert celery_task_mock.retry.call_count == 0
    
    def test_transient_error_triggers_retry(self, celery_task_mock, smtp_mock):
        smtp_mock.send.side_effect = SMTPConnectionError("Timeout")
        apply_via_email.apply(args=["app-id"])
        assert celery_task_mock.retry.call_count == 1
```

#### Circuit Breaker Tests

```python
class TestCircuitBreaker:
    
    def test_circuit_opens_after_threshold(self, redis_mock):
        cb = CircuitBreaker()
        for i in range(5):
            cb.record_failure("example.com")
        assert cb.is_open("example.com") is True
    
    def test_circuit_closes_after_recovery_timeout(self, redis_mock):
        cb = CircuitBreaker()
        redis_mock.get.side_effect = ["open", str(time.time() - 120)]
        # opened_at was 120s ago, recovery_timeout=60, so should be half_open
        assert cb.is_open("example.com") is False
    
    def test_request_blocked_when_circuit_open(self):
        cb = CircuitBreaker()
        cb._state = "open"
        with pytest.raises(CircuitOpenError):
            cb.check("example.com")
```

#### Form Field Mapper Tests

```python
class TestFormFieldMapper:
    
    def test_maps_standard_linkedin_fields(self, driver_mock):
        driver_mock.find_elements.return_value = [
            MockElement(name="first_name", type="text"),
            MockElement(name="last_name", type="text"),
            MockElement(name="email", type="email"),
        ]
        mapper = FormFieldMapper()
        fields = mapper.discover_fields(driver_mock)
        assert "first_name" in fields
        assert "last_name" in fields
        assert "email" in fields
    
    def test_handles_camelcase_field_names(self, driver_mock):
        driver_mock.find_elements.return_value = [
            MockElement(name="firstName", type="text"),
        ]
        mapper = FormFieldMapper()
        fields = mapper.discover_fields(driver_mock)
        assert "first_name" in fields  # Normalized
    
    def test_unknown_field_not_in_result(self, driver_mock):
        driver_mock.find_elements.return_value = [
            MockElement(name="some_unknown_field_xyz", type="text"),
        ]
        mapper = FormFieldMapper()
        fields = mapper.discover_fields(driver_mock)
        assert len(fields) == 0
```

---

## 4. Integration Tests

**Target:** Test component interactions with real databases, real Redis, mocked external services.  
**Environment:** Docker Compose test environment  
**Framework:** pytest + testcontainers-python  

### 4.1 Test Database Setup

```python
# conftest.py
import pytest
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        run_migrations(pg.get_connection_url())
        yield pg

@pytest.fixture(scope="session")
def redis_container():
    with RedisContainer("redis:7-alpine") as redis:
        yield redis

@pytest.fixture(autouse=True)
async def clean_db(postgres_container):
    """Truncate all tables before each test."""
    async with get_db_connection(postgres_container.get_connection_url()) as conn:
        await conn.execute("TRUNCATE applications, email_sends, confirmations CASCADE")
    yield
```

### 4.2 Integration Test Cases

#### Email Integration Tests

```python
class TestEmailIntegration:
    
    @pytest.mark.asyncio
    async def test_email_creates_db_record(self, db, smtp_sandbox):
        """Verify email send creates email_sends record in DB."""
        app_id = await create_test_application(db)
        await EmailApplicationSystem().submit(app_id)
        
        record = await db.fetchone(
            "SELECT * FROM email_sends WHERE application_id = $1", app_id
        )
        assert record is not None
        assert record["status"] == "sent"
    
    @pytest.mark.asyncio
    async def test_email_updates_application_status(self, db, smtp_sandbox):
        app_id = await create_test_application(db, status="queued")
        await EmailApplicationSystem().submit(app_id)
        
        app = await db.fetchone("SELECT status FROM applications WHERE application_id = $1", app_id)
        assert app["status"] == "applied"
    
    @pytest.mark.asyncio
    async def test_email_failure_increments_retry_count(self, db, smtp_error_mock):
        app_id = await create_test_application(db)
        
        with pytest.raises(SMTPError):
            await EmailApplicationSystem().submit(app_id)
        
        app = await db.fetchone("SELECT retry_count FROM applications WHERE application_id = $1", app_id)
        assert app["retry_count"] == 1
```

#### Database Operations Tests

```python
class TestDatabaseOperations:
    
    @pytest.mark.asyncio
    async def test_unique_constraint_prevents_duplicate(self, db):
        await create_application(db, user_id="u1", job_id="j1")
        with pytest.raises(asyncpg.UniqueViolationError):
            await create_application(db, user_id="u1", job_id="j1")
    
    @pytest.mark.asyncio
    async def test_status_history_logged_on_update(self, db):
        app_id = await create_application(db, status="queued")
        await update_application_status(db, app_id, "applied")
        
        history = await db.fetch(
            "SELECT * FROM application_status_history WHERE application_id = $1", app_id
        )
        assert len(history) == 1
        assert history[0]["from_status"] == "queued"
        assert history[0]["to_status"] == "applied"
    
    @pytest.mark.asyncio
    async def test_updated_at_trigger_fires(self, db):
        app_id = await create_application(db)
        original_time = (await db.fetchone(
            "SELECT updated_at FROM applications WHERE application_id = $1", app_id
        ))["updated_at"]
        
        await asyncio.sleep(0.01)
        await update_application_status(db, app_id, "applied")
        
        new_time = (await db.fetchone(
            "SELECT updated_at FROM applications WHERE application_id = $1", app_id
        ))["updated_at"]
        
        assert new_time > original_time
```

---

## 5. End-to-End Tests

**Environment:** Full Docker Compose stack (API + Celery + Selenium + PG + Redis)  
**Purpose:** Verify the complete pipeline works from API call to confirmation  

### 5.1 E2E Web Form Test

```python
class TestFullWebFormPipeline:
    """Uses a local HTML test form server (no external dependencies)."""
    
    @pytest.fixture(scope="class")
    def test_form_server(self):
        """Serve a realistic job application form locally."""
        server = create_test_form_server(port=8765)
        yield f"http://localhost:8765/apply"
        server.shutdown()
    
    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_complete_form_submission(self, api_client, test_form_server):
        # Submit application via API
        response = await api_client.post("/api/v1/applications/submit", json={
            **build_valid_webform_request(url=test_form_server),
        })
        assert response.status_code == 202
        app_id = response.json()["data"]["application_id"]
        
        # Wait for processing (max 60 seconds)
        await wait_for_status(api_client, app_id, target="applied", timeout=60)
        
        # Verify final state
        status_response = await api_client.get(f"/api/v1/applications/{app_id}/status")
        data = status_response.json()["data"]
        
        assert data["status"] == "applied"
        assert data["confirmation"] is not None
        assert data["confirmation"]["evidence_url"] is not None  # Screenshot exists
```

### 5.2 Mock Form Server

The E2E tests use a local form server serving realistic HTML:

```html
<!-- test_form.html — used by E2E tests -->
<!DOCTYPE html>
<html>
<body>
  <form id="application-form" action="/submit" method="POST">
    <input type="text" name="first_name" required>
    <input type="text" name="last_name" required>
    <input type="email" name="email" required>
    <input type="tel" name="phone">
    <input type="file" name="resume" accept=".pdf">
    <textarea name="cover_letter"></textarea>
    <button type="submit">Apply Now</button>
  </form>
</body>
</html>

<!-- confirmation.html — served after successful POST -->
<!DOCTYPE html>
<html>
<body>
  <h1>Application Received!</h1>
  <p>Your application reference: <strong id="app-ref">APP-TEST-12345</strong></p>
  <p>Thank you for applying. We will be in touch.</p>
</body>
</html>
```

---

## 6. Contract Tests

Verify this module's API contract against what other agents expect:

```python
class TestOrchestratorContract:
    """Ensure our output payload matches the orchestrator's expectations."""
    
    def test_success_output_matches_contract(self):
        output = ApplicationResult(
            application_id="...",
            status="applied",
            submitted_at=datetime.utcnow(),
            confirmation={...},
        )
        # Validate against JSON Schema from api_contracts.md
        validate_against_schema(output.dict(), "application_result_schema.json")
    
    def test_error_output_matches_contract(self):
        output = ApplicationResult(
            application_id="...",
            status="failed",
            error={"code": "...", "message": "...", "retry_count": 3},
        )
        validate_against_schema(output.dict(), "application_result_schema.json")
```

---

## 7. Load & Performance Tests

**Tool:** Locust  
**Targets:**

| Test | Target | Pass Criteria |
|------|--------|---------------|
| Submit 100 applications/minute | API throughput | P99 < 500ms response |
| 10 concurrent web form sessions | Selenium Grid load | All complete without crash |
| Redis rate counter under 1000 req/s | Redis performance | No counter drift |
| DB 1000 writes/minute | PostgreSQL throughput | P99 < 50ms write latency |

```python
# locustfile.py
from locust import HttpUser, task, between

class ApplicationUser(HttpUser):
    wait_time = between(0.5, 2.0)
    
    @task
    def submit_application(self):
        self.client.post(
            "/api/v1/applications/submit",
            json=build_valid_email_request(),
            headers={"Authorization": f"Bearer {TEST_JWT}"}
        )
    
    @task(3)
    def check_status(self):
        self.client.get(f"/api/v1/applications/{SAMPLE_APP_ID}/status")
```

---

## 8. Security Tests

```python
class TestSecurityEnforcement:
    
    def test_unauthorized_request_rejected(self, api_client):
        response = api_client.post("/api/v1/applications/submit", json={...})
        # No auth header
        assert response.status_code == 401
    
    def test_path_traversal_rejected(self, api_client, auth_header):
        response = api_client.post("/api/v1/applications/submit", 
            json={"resume": {"filename": "../../etc/passwd", ...}},
            headers=auth_header
        )
        assert response.status_code == 422
    
    def test_untrusted_storage_url_rejected(self, api_client, auth_header):
        response = api_client.post("/api/v1/applications/submit",
            json={"resume": {"storage_url": "https://evil.com/resume.pdf", ...}},
            headers=auth_header
        )
        assert response.status_code == 422
    
    def test_unknown_domain_blocked_in_browser(self):
        with pytest.raises(ForbiddenDomainError):
            validate_application_url("https://phishing-site.xyz/apply")
    
    def test_rate_limit_returns_429(self, api_client, auth_header, redis_at_limit):
        response = api_client.post("/api/v1/applications/submit",
            json=build_valid_email_request(),
            headers=auth_header
        )
        assert response.status_code == 429
        assert "RATE_LIMIT_EXCEEDED" in response.json()["error"]["code"]
    
    def test_duplicate_application_returns_409(self, api_client, auth_header, existing_application):
        response = api_client.post("/api/v1/applications/submit",
            json=build_request_for_existing_application(),
            headers=auth_header
        )
        assert response.status_code == 409
```

---

## 9. CI/CD Pipeline

```yaml
# .github/workflows/member04-tests.yml
name: Member 04 — Application Automation Tests

on:
  push:
    paths: ['member_04/**']
  pull_request:
    paths: ['member_04/**']

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run unit tests
        run: |
          pytest tests/unit/ -v --cov=member_04 --cov-fail-under=85
        timeout-minutes: 5

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_PASSWORD: test
      redis:
        image: redis:7-alpine
    steps:
      - uses: actions/checkout@v4
      - name: Run integration tests
        run: pytest tests/integration/ -v
        timeout-minutes: 15

  security-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run security tests
        run: pytest tests/unit/test_security.py -v
      - name: Run bandit security scan
        run: bandit -r member_04/ -f json -o bandit_report.json

  e2e-tests:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Start full stack
        run: docker-compose -f docker-compose.test.yml up -d
      - name: Wait for services
        run: sleep 30
      - name: Run E2E tests
        run: pytest tests/e2e/ -v -m e2e
        timeout-minutes: 30
      - name: Collect logs on failure
        if: failure()
        run: docker-compose logs > e2e_failure_logs.txt
```

---

## 10. Test Data Management

```python
# tests/fixtures/factories.py

def build_valid_email_request(**overrides) -> dict:
    """Factory for a valid email application request."""
    return {
        "user_id": "550e8400-e29b-41d4-a716-446655440000",
        "job_id": "7f3e4e20-f56c-4b77-8f81-1234567890ab",
        "job_metadata": {
            "company_name": "Test Corp",
            "role_title": "Software Engineer",
            "platform": "email",
            "application_method": "email",
            "contact_email": "jobs@testcorp.example.com",
            "deadline": None,
        },
        "resume": {
            "version_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "storage_url": "https://our-storage.example.com/resumes/test.pdf",
            "filename": "Test_Resume.pdf",
        },
        "cover_letter": {
            "version_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
            "storage_url": "https://our-storage.example.com/covers/test.pdf",
            "content_text": "Dear Hiring Manager, I am excited to apply...",
        },
        "guardrails": {
            "manual_approval_required": False,
            "max_retries": 3,
            "priority": "normal",
        },
        **overrides,
    }
```

---

*Next Document: `task_breakdown.md` — implementation task decomposition and sprint plan*
