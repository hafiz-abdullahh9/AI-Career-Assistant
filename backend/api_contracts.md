# API Contracts — Member 4: Application Automation Agent
**Project:** AI Career Assistant Multi-Agent System 2026  
**Module Owner:** Member 4  
**Status:** Planning Phase  
**Last Updated:** 2026-06-12  
**Base URL:** `/api/v1`  
**Auth:** Bearer JWT (all endpoints unless noted)  

---

## 1. API Design Principles

1. **RESTful resource naming** — nouns, not verbs
2. **Async by default** — submit returns `202 Accepted` with tracking URL
3. **Consistent error envelope** — all errors follow the same JSON shape
4. **Idempotency keys** — POST endpoints support `Idempotency-Key` header
5. **Pagination** — list endpoints return cursor-based pagination
6. **OpenAPI 3.1** — auto-generated from FastAPI, served at `/docs`

---

## 2. Standard Response Envelopes

### Success

```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "request_id": "uuid4",
    "timestamp": "ISO8601"
  }
}
```

### Error

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable description",
    "details": [ { "field": "...", "issue": "..." } ]
  },
  "meta": {
    "request_id": "uuid4",
    "timestamp": "ISO8601"
  }
}
```

### Paginated List

```json
{
  "success": true,
  "data": [ ... ],
  "pagination": {
    "cursor": "base64_encoded_cursor",
    "has_more": true,
    "total_count": 142
  }
}
```

---

## 3. Application Submission Endpoints

### POST `/applications/submit`
Submit a new job application for processing.

**Headers:**
```
Authorization: Bearer {jwt}
Idempotency-Key: {uuid4}   (optional but recommended)
Content-Type: application/json
```

**Request Body:**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "job_id": "7f3e4e20-f56c-4b77-8f81-1234567890ab",
  "job_metadata": {
    "company_name": "Acme Corp",
    "role_title": "Senior Python Engineer",
    "platform": "greenhouse",
    "application_method": "web_form",
    "application_url": "https://boards.greenhouse.io/acme/jobs/12345",
    "contact_email": null,
    "deadline": "2026-07-01T23:59:59Z"
  },
  "resume": {
    "version_id": "a1b2c3d4-...",
    "storage_url": "https://s3.example.com/resumes/user_id/v3.pdf",
    "filename": "Jane_Doe_Resume_v3.pdf"
  },
  "cover_letter": {
    "version_id": "b2c3d4e5-...",
    "storage_url": "https://s3.example.com/covers/user_id/acme_v1.pdf",
    "content_text": "Dear Hiring Manager, ..."
  },
  "guardrails": {
    "manual_approval_required": false,
    "max_retries": 3,
    "priority": "normal"
  }
}
```

**Response — 202 Accepted:**
```json
{
  "success": true,
  "data": {
    "application_id": "9d3e4e20-...",
    "status": "queued",
    "tracking_url": "/api/v1/applications/9d3e4e20-.../status",
    "estimated_completion_seconds": 120
  }
}
```

**Error Responses:**

| Status | Code | Condition |
|--------|------|-----------|
| 400 | `VALIDATION_ERROR` | Invalid request body |
| 403 | `UNVERIFIED_JOB` | Job not in verified list |
| 409 | `DUPLICATE_APPLICATION` | Already applied to this job |
| 410 | `JOB_EXPIRED` | Job deadline has passed |
| 422 | `ASSET_UNREACHABLE` | Cannot access resume/cover letter URL |
| 429 | `RATE_LIMIT_EXCEEDED` | Daily limit reached |

---

### GET `/applications/{application_id}/status`
Get current status of a specific application.

**Response — 200 OK:**
```json
{
  "success": true,
  "data": {
    "application_id": "9d3e4e20-...",
    "user_id": "550e8400-...",
    "job_id": "7f3e4e20-...",
    "company_name": "Acme Corp",
    "role_title": "Senior Python Engineer",
    "method": "web_form",
    "status": "applied",
    "queued_at": "2026-06-12T10:00:00Z",
    "applied_at": "2026-06-12T10:02:34Z",
    "retry_count": 0,
    "confirmation": {
      "type": "form_success_message",
      "external_ref_id": "APP-2026-78523",
      "evidence_url": "https://s3.example.com/screenshots/9d3e.../confirmation.webp"
    }
  }
}
```

---

### GET `/applications`
List all applications for a user, with filtering and pagination.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `user_id` | UUID | Required | Filter by user |
| `status` | string | null | Filter by status enum value |
| `method` | string | null | `email` or `web_form` |
| `company` | string | null | Partial match search |
| `from_date` | ISO8601 | null | Filter applied_at >= date |
| `to_date` | ISO8601 | null | Filter applied_at <= date |
| `cursor` | string | null | Pagination cursor |
| `limit` | integer | 20 | Max 100 |
| `sort` | string | `applied_at_desc` | Sort order |

**Response — 200 OK:**
```json
{
  "success": true,
  "data": [
    {
      "application_id": "...",
      "company_name": "Acme Corp",
      "role_title": "Senior Python Engineer",
      "status": "applied",
      "method": "web_form",
      "applied_at": "2026-06-12T10:02:34Z",
      "confirmation_id": "APP-2026-78523"
    }
  ],
  "pagination": {
    "cursor": "eyJhcHBsaWVkX2F0IjoiMjAyNi0wNi0xMiJ9",
    "has_more": false,
    "total_count": 14
  }
}
```

---

### PATCH `/applications/{application_id}/status`
Manually update application status (e.g., user marks interview, rejection).

**Request Body:**
```json
{
  "status": "interview",
  "reason": "Received interview invite email from recruiter",
  "changed_by": "user"
}
```

**Response — 200 OK:**
```json
{
  "success": true,
  "data": {
    "application_id": "...",
    "previous_status": "applied",
    "new_status": "interview",
    "updated_at": "2026-06-12T15:30:00Z"
  }
}
```

---

### DELETE `/applications/{application_id}`
Soft-delete an application record.

**Response — 200 OK:**
```json
{
  "success": true,
  "data": {
    "application_id": "...",
    "deleted_at": "2026-06-12T15:30:00Z"
  }
}
```

---

## 4. Approval Workflow Endpoints

### GET `/applications/{application_id}/approval`
Get approval request status.

**Response — 200 OK:**
```json
{
  "success": true,
  "data": {
    "request_id": "...",
    "application_id": "...",
    "status": "pending",
    "expires_at": "2026-06-13T10:00:00Z",
    "approval_url": "/api/v1/approvals/{token}/approve",
    "reject_url": "/api/v1/approvals/{token}/reject"
  }
}
```

---

### POST `/approvals/{token}/approve`
User approves a pending application. No auth required (token serves as auth).

**Response — 200 OK:**
```json
{
  "success": true,
  "data": {
    "application_id": "...",
    "approved_at": "2026-06-12T11:00:00Z",
    "message": "Application has been queued for submission."
  }
}
```

---

### POST `/approvals/{token}/reject`
User rejects a pending application.

**Request Body:**
```json
{
  "reason": "Salary too low"
}
```

**Response — 200 OK:**
```json
{
  "success": true,
  "data": {
    "application_id": "...",
    "rejected_at": "2026-06-12T11:00:00Z"
  }
}
```

---

## 5. Confirmation Endpoints

### GET `/applications/{application_id}/confirmations`
Get all confirmation evidence for an application.

**Response — 200 OK:**
```json
{
  "success": true,
  "data": [
    {
      "confirmation_id": "...",
      "type": "form_success_message",
      "external_ref_id": "APP-2026-78523",
      "evidence_url": "https://s3.example.com/screenshots/...",
      "captured_at": "2026-06-12T10:02:35Z",
      "extracted_data": {
        "application_reference": "APP-2026-78523",
        "confirmation_message": "Your application has been received."
      }
    }
  ]
}
```

---

## 6. Rate Limit Endpoints

### GET `/users/{user_id}/rate-limits`
Get current rate limit status for a user.

**Response — 200 OK:**
```json
{
  "success": true,
  "data": {
    "user_id": "...",
    "date": "2026-06-12",
    "daily_limit": 50,
    "applications_today": 12,
    "remaining": 38,
    "resets_at": "2026-06-13T00:00:00Z"
  }
}
```

---

## 7. Analytics & Dashboard Endpoints

### GET `/users/{user_id}/statistics`
Get application statistics summary.

**Response — 200 OK:**
```json
{
  "success": true,
  "data": {
    "total_applications": 142,
    "by_status": {
      "applied": 120,
      "interview": 8,
      "rejected": 10,
      "accepted": 2,
      "failed": 2
    },
    "by_method": {
      "email": 45,
      "web_form": 97
    },
    "success_rate": 0.845,
    "avg_confirmation_rate": 0.72,
    "applications_this_week": 15,
    "applications_this_month": 62,
    "top_platforms": [
      { "platform": "greenhouse", "count": 45 },
      { "platform": "linkedin", "count": 38 }
    ]
  }
}
```

---

## 8. Internal / Service-to-Service Endpoints

These endpoints are for internal agent communication only (service mesh, not public):

### POST `/internal/applications/{application_id}/result`
Called by Celery worker to post automation result back to API.

**Headers:**
```
X-Internal-Secret: {shared_secret}
```

**Request Body:**
```json
{
  "status": "applied",
  "applied_at": "2026-06-12T10:02:34Z",
  "confirmation": {
    "type": "form_success_message",
    "external_ref_id": "APP-2026-78523",
    "evidence_url": "s3://bucket/screenshots/..."
  },
  "error": null,
  "retry_count": 0
}
```

---

### POST `/internal/webhook/orchestrator`
Called by this service to notify orchestrator of completion.

**Payload:** Same as output contract in `automation_architecture.md` Section 6.2.

---

## 9. WebSocket Endpoint (Live Tracking)

### WS `/ws/applications/{application_id}/live`
Real-time status updates for a specific application.

**Events emitted:**
```json
{ "event": "status_change",  "data": { "status": "processing" }, "timestamp": "..." }
{ "event": "field_filled",   "data": { "field": "email", "success": true }, "timestamp": "..." }
{ "event": "form_submitted",  "data": { "success": true }, "timestamp": "..." }
{ "event": "completed",      "data": { "status": "applied", "confirmation_id": "..." }, "timestamp": "..." }
{ "event": "error",          "data": { "code": "...", "message": "..." }, "timestamp": "..." }
```

---

## 10. Error Code Reference

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 400 | Request body schema invalid |
| `UNAUTHORIZED` | 401 | Missing or invalid JWT |
| `FORBIDDEN` | 403 | Insufficient permissions |
| `UNVERIFIED_JOB` | 403 | Job not in verified list |
| `NOT_FOUND` | 404 | Resource not found |
| `DUPLICATE_APPLICATION` | 409 | Already applied to this job |
| `JOB_EXPIRED` | 410 | Job deadline passed |
| `ASSET_UNREACHABLE` | 422 | Cannot access file URL |
| `RATE_LIMIT_EXCEEDED` | 429 | Daily application cap hit |
| `INTERNAL_ERROR` | 500 | Unexpected server error |
| `AUTOMATION_FAILED` | 500 | Browser/email automation error |
| `CAPTCHA_BLOCKED` | 503 | CAPTCHA cannot be solved |

---

## 11. Versioning Strategy

- Current: `v1` — all endpoints prefixed `/api/v1/`
- Breaking changes → new major version (`v2`)
- `v1` supported for minimum 12 months after `v2` release
- Deprecation header: `Deprecation: true` + `Sunset: {date}`

---

*Next Document: `retry_and_error_strategy.md` — comprehensive retry & error handling design*
