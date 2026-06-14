# Security Guardrails — Member 4: Application Automation Agent
**Project:** AI Career Assistant Multi-Agent System 2026  
**Module Owner:** Member 4  
**Status:** Planning Phase  
**Last Updated:** 2026-06-12  

---

## 1. Security Design Principles

1. **Zero Trust** — Every request is verified, even internal ones.
2. **Least Privilege** — Each component gets only the permissions it needs.
3. **Secrets Never in Code** — All credentials fetched from secrets manager at runtime.
4. **Defense in Depth** — Multiple layers; one breach doesn't mean full compromise.
5. **Audit Everything** — Every credential access, automation action, and status change is logged.
6. **Fail Secure** — On uncertainty, deny and alert rather than permit.

---

## 2. Guardrail Layer 1: Application Rate Limiting

### 2.1 Daily Application Limits

The system enforces hard per-user daily caps to prevent account bans on job platforms.

```
Default limits (configurable per user/plan):
  • Standard plan:  20 applications/day
  • Pro plan:       50 applications/day
  • Enterprise:     100 applications/day

Enforcement:
  • Redis counter: rate:daily:{user_id}:{YYYYMMDD}
  • TTL: 48 hours (auto-expires)
  • INCR is atomic — no race conditions
  • Checked BEFORE creating application record
```

### 2.2 Platform-Specific Limits

Some job platforms flag rapid applications. Additional per-platform limits:

```python
PLATFORM_LIMITS = {
    "linkedin":   {"per_day": 10, "min_interval_seconds": 120},
    "indeed":     {"per_day": 15, "min_interval_seconds": 60},
    "greenhouse": {"per_day": 20, "min_interval_seconds": 30},
    "lever":      {"per_day": 20, "min_interval_seconds": 30},
    "default":    {"per_day": 20, "min_interval_seconds": 30},
}
```

### 2.3 Global System Limits

```python
GLOBAL_LIMITS = {
    "max_concurrent_browser_sessions": 10,
    "max_emails_per_hour_system_wide": 500,
    "max_celery_queue_size": 1000,        # Back-pressure
}
```

---

## 3. Guardrail Layer 2: Job Verification Enforcement

**Rule:** The system MUST NEVER apply to an unverified job.

```python
async def verify_job_is_approved(job_id: str) -> bool:
    """
    Cross-check with Job Verification Agent's result table.
    A job must have:
      1. verification_status = 'verified'
      2. verification_date within last 7 days
      3. is_active = TRUE
      4. Not flagged as scam/expired
    """
    job = await db.fetchone(
        "SELECT * FROM verified_jobs WHERE job_id = $1",
        job_id
    )
    if not job:
        raise UnverifiedJobError(f"Job {job_id} not found in verified list")
    if job.verification_status != 'verified':
        raise UnverifiedJobError(f"Job {job_id} status: {job.verification_status}")
    if job.verified_at < datetime.utcnow() - timedelta(days=7):
        raise UnverifiedJobError(f"Job {job_id} verification expired")
    return True
```

---

## 4. Guardrail Layer 3: Credential Security

### 4.1 What Credentials Are Involved

| Credential | Used For | Storage |
|------------|----------|---------|
| Gmail OAuth2 tokens | Sending emails | Secrets Manager |
| SMTP username/password | Fallback email | Secrets Manager |
| 2captcha API key | CAPTCHA solving | Secrets Manager |
| PostgreSQL connection string | Database | Secrets Manager |
| Redis URL | Queue/cache | Secrets Manager |
| S3 bucket credentials | File storage | IAM Role (no static creds) |
| JWT signing secret | API auth | Secrets Manager |
| Internal service shared secret | Service-to-service auth | Secrets Manager |

### 4.2 Secrets Manager Integration

```python
# Secrets are loaded at application startup — never hardcoded
import boto3

class SecretsManager:
    _cache: dict = {}
    
    @classmethod
    async def get(cls, secret_name: str) -> str:
        if secret_name in cls._cache:
            return cls._cache[secret_name]
        
        client = boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=secret_name)
        value = response["SecretString"]
        
        # Cache for 15 minutes (avoids per-request Secrets Manager calls)
        cls._cache[secret_name] = value
        asyncio.get_event_loop().call_later(900, cls._cache.pop, secret_name, None)
        
        return value
```

**Alternative for self-hosted:** HashiCorp Vault with AppRole auth.

### 4.3 Environment Variable Policy

```bash
# ALLOWED in .env / environment:
APP_ENV=production
LOG_LEVEL=INFO
SECRETS_MANAGER_REGION=us-east-1

# FORBIDDEN in .env / environment (must be in Secrets Manager):
# DATABASE_URL=postgresql://...    ← NEVER
# GMAIL_CLIENT_SECRET=...          ← NEVER
# SMTP_PASSWORD=...                ← NEVER
```

### 4.4 OAuth Token Lifecycle

```
1. User authorizes Gmail access → OAuth2 flow
2. Access token + refresh token stored in Secrets Manager
3. Access token used for sending (valid 1 hour)
4. Refresh token used to get new access token (valid indefinitely)
5. Token rotation:
   - On 401 response from Gmail API → refresh automatically
   - Refresh tokens rotated every 30 days (GCP best practice)
6. Revocation: User can revoke from settings → tokens deleted from SM
```

---

## 5. Guardrail Layer 4: Input Validation & Sanitization

### 5.1 Pydantic Schema Validation

All API inputs validated via Pydantic v2 models:

```python
from pydantic import BaseModel, validator, HttpUrl
from uuid import UUID

class ApplicationSubmitRequest(BaseModel):
    user_id: UUID
    job_id: UUID
    job_metadata: JobMetadata
    resume: ResumeAsset
    cover_letter: CoverLetterAsset
    guardrails: GuardrailConfig
    
    @validator('job_metadata')
    def validate_application_url(cls, v):
        if v.application_method == 'web_form' and not v.application_url:
            raise ValueError("application_url required for web_form method")
        if v.application_method == 'email' and not v.contact_email:
            raise ValueError("contact_email required for email method")
        return v

class ResumeAsset(BaseModel):
    version_id: UUID
    storage_url: HttpUrl           # Must be valid HTTPS URL
    filename: str
    
    @validator('filename')
    def validate_filename(cls, v):
        # Prevent path traversal attacks
        if '..' in v or '/' in v or '\\' in v:
            raise ValueError("Invalid filename")
        if not v.endswith('.pdf'):
            raise ValueError("Resume must be PDF")
        return v
    
    @validator('storage_url')
    def validate_storage_url(cls, v):
        # Only allow our own storage domains
        allowed_domains = ['s3.amazonaws.com', 'storage.googleapis.com', 'our-storage.example.com']
        if not any(d in str(v) for d in allowed_domains):
            raise ValueError("storage_url must be from approved storage provider")
        return v
```

### 5.2 HTML/Script Injection Prevention

Content written to emails or web forms is sanitized:

```python
import bleach

def sanitize_text_content(text: str) -> str:
    """Remove any HTML/script tags from user-supplied text."""
    return bleach.clean(text, tags=[], strip=True)
```

---

## 6. Guardrail Layer 5: Web Automation Safety

### 6.1 Domain Allowlist

The web form engine will ONLY navigate to domains that are whitelisted:

```python
DOMAIN_ALLOWLIST_SOURCES = [
    # Trusted ATS platforms
    "greenhouse.io",
    "lever.co",
    "workday.com",
    "taleo.net",
    "icims.com",
    "successfactors.com",
    "bamboohr.com",
    "smartrecruiters.com",
    
    # Job boards
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "monster.com",
    
    # Dynamic addition from verified_jobs table only
]

def validate_application_url(url: str) -> bool:
    """Reject any URL not from trusted domains."""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower()
    domain = domain.lstrip('www.')
    
    if not any(domain.endswith(allowed) for allowed in DOMAIN_ALLOWLIST_SOURCES):
        raise ForbiddenDomainError(
            f"Domain {domain} is not in the trusted domain list. "
            "Only navigate to URLs from verified job platforms."
        )
    return True
```

### 6.2 Form Data Leakage Prevention

- Browser sessions are isolated per application (no shared cookies/sessions)
- No sensitive data written to browser localStorage/sessionStorage
- Incognito/private mode equivalent enabled (disable cache persistence)
- Temp files deleted immediately after upload

### 6.3 Screenshot Redaction

Screenshots may capture sensitive user data. Before storing:

```python
def redact_sensitive_fields(screenshot_path: str) -> str:
    """
    Optionally blur sensitive areas in screenshots.
    Currently: blur password fields (if any appear in confirmation pages).
    """
    # Implementation: OpenCV blur on regions matching password input selectors
    # For v1: store as-is (access controlled), redaction in v2
    pass
```

### 6.4 Proof of Employment Verification

Before applying, the system confirms the target URL is a real job posting:

```python
async def verify_url_is_job_application(url: str, job_id: str) -> bool:
    """
    Cross-check URL against what the Job Verification Agent recorded.
    Prevents applying to manipulated/replaced URLs.
    """
    recorded_url = await db.fetchval(
        "SELECT application_url FROM verified_jobs WHERE job_id = $1", job_id
    )
    if recorded_url != url:
        raise SecurityError(
            "Application URL does not match verified job record. "
            "Possible URL tampering detected."
        )
    return True
```

---

## 7. Guardrail Layer 6: Manual Approval Mode

### 7.1 When Manual Approval Is Required

Users can configure this globally or per-application type:

```python
MANUAL_APPROVAL_TRIGGERS = [
    "always",                       # User wants to approve every application
    "high_value_companies",         # FAANG, top-tier companies
    "salary_above_threshold",       # When salary > user-defined threshold
    "new_platform",                 # First application to a new platform
    "first_N_applications",         # First 5 applications (new user caution)
]
```

### 7.2 Approval Request Lifecycle

```
Application arrives with manual_approval_required=True
  ↓
Create approval_request record (token-secured URL)
  ↓
Notify user (email + in-app notification)
  ↓
Application status = 'pending_approval'
  ↓
User reviews application details:
  - Company, role, resume version, cover letter preview
  - Method (email/web form)
  - Application URL or contact email
  ↓
User clicks "Approve" or "Reject"
  ↓
On APPROVE → enqueue Celery task → proceed normally
On REJECT → mark application 'rejected_by_user', no action
  ↓
Approval token expires after 24 hours (unactioned → auto-reject)
```

### 7.3 Approval Email Template

```
Subject: 🔔 Review Required: Application to {company} for {role}

Hi {user_name},

Your AI Career Assistant wants to submit an application on your behalf.

Company:   {company}
Role:      {role}
Method:    {email/web form}
{contact email or application URL}

📄 Resume: {resume_version}
📝 Cover Letter: {cover_letter_preview}

Please review and decide within 24 hours:

✅ [APPROVE APPLICATION]({approval_url})
❌ [REJECT APPLICATION]({reject_url})

This request expires: {expiry_time}
```

---

## 8. Guardrail Layer 7: Data Privacy

### 8.1 Data Minimization

- Only store what is needed for tracking and retry
- Never log full resume content or cover letter body
- Never log contact email passwords
- Email body preview capped at 500 characters in DB

### 8.2 Data Encryption

| Data | Encryption |
|------|-----------|
| Resume files in S3 | AES-256 at rest (S3 SSE) |
| DB columns (email, phone) | Application-level AES-128 for PII fields |
| Redis data | TLS in transit |
| PostgreSQL | TLS in transit + pgcrypto for sensitive fields |
| Screenshots | AES-256 at rest (S3 SSE) |

### 8.3 GDPR/Data Rights Support

| User Right | Implementation |
|-----------|---------------|
| Right to access | GET /users/{id}/data — returns all application records |
| Right to erasure | DELETE /users/{id} — soft-deletes all records, schedules permanent purge |
| Right to portability | GET /users/{id}/export — returns JSON export of all data |
| Consent management | Consent logged with timestamp at account creation |

---

## 9. Guardrail Layer 8: Audit Logging

Every sensitive action generates an audit log entry:

```python
class AuditEvent(BaseModel):
    event_id: str           # UUID
    timestamp: datetime
    actor: str              # 'system', 'user:{user_id}', 'admin:{admin_id}'
    action: str             # e.g., 'application.submitted', 'credential.accessed'
    resource_type: str      # e.g., 'application', 'email_credential'
    resource_id: str
    outcome: str            # 'success', 'failure', 'blocked'
    ip_address: str
    user_agent: str
    metadata: dict

# Audit events that MUST be logged:
AUDITED_ACTIONS = [
    "application.submitted",
    "application.approved",
    "application.rejected",
    "credential.accessed",
    "rate_limit.triggered",
    "circuit_breaker.opened",
    "captcha.encountered",
    "domain_blocklist.triggered",
    "manual_approval.requested",
    "data.exported",
    "user.deleted",
]
```

Audit logs are:
- Append-only (no updates or deletes)
- Stored separately from application logs
- Retained for 2 years minimum
- Monitored by SIEM (e.g., Datadog SIEM rules)

---

*Next Document: `testing_strategy.md` — comprehensive testing approach*
