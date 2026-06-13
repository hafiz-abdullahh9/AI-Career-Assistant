# State Machine — Application Status Lifecycle

## Overview

Every job application follows a strict state machine.
Transitions are enforced at the **service layer** — no code can write an invalid
status to the database without raising `InvalidStatusTransitionError`.

The source of truth is `VALID_TRANSITIONS` in [`app/models/schemas.py`](../app/models/schemas.py).

---

## Complete State Diagram

```
                        ┌─────────────────────────────┐
          (entry)       │                             │
             │          │   ┌──────────────────┐      │
             ▼          │   │  PENDING_APPROVAL │      │
         ┌───────┐      │   └────────┬─────────┘      │
         │QUEUED │──────┘            │ user approves  │
         └───┬───┘                   ▼                │
             │           ┌──────────────────────┐     │
             │           │      PROCESSING       │◄────┘
             └──────────►│                      │
                         └──┬───────┬───────────┘
                            │       │       │
                  success   │  fail │  captcha?
                            │       │       │
                    ┌───────┘  ┌────┘  ┌────┘
                    ▼          ▼       ▼
                ┌───────┐ ┌────────┐ ┌──────────────────┐
                │APPLIED│ │ FAILED │ │ CAPTCHA_REQUIRED  │
                └───┬───┘ └────────┘ └─────────┬────────┘
                    │     (terminal)            │
                    │                  solved   │ failed
                    │                   ┌───────┘
                    ▼                   ▼
              ┌──────────┐        ┌─────────┐
              │INTERVIEW │   back to PROCESSING or FAILED
              └──┬────┬──┘
                 │    │
           offer │    │ no
                 ▼    ▼
           ┌────────┐ ┌──────────┐
           │ACCEPTED│ │ REJECTED │
           └────────┘ └──────────┘
           (terminal)  (terminal)

Immediate terminal states (set during guardrail phase):
  DUPLICATE       — already applied to this job
  LIMIT_EXCEEDED  — daily application limit reached
  EXPIRED         — job posting deadline passed
  ASSET_ERROR     → QUEUED (resume/cover letter unreachable, can retry)
```

---

## State Definitions

| Status | Set By | Meaning |
|--------|--------|---------|
| `queued` | Orchestrator submission | Application accepted, waiting in Celery queue |
| `processing` | Celery worker start | Worker has picked up the task and is running |
| `pending_approval` | Guardrail check | Manual review required before submitting |
| `applied` | Worker success | Submission confirmed on the employer's platform |
| `captcha_required` | Worker detection | Browser hit a CAPTCHA — needs manual or solver |
| `failed` | Worker failure / max retries | Permanent failure, no more retries |
| `duplicate` | Guardrail check | Already applied to this job (idempotency guard) |
| `limit_exceeded` | Guardrail check | User hit daily submission limit |
| `expired` | Guardrail check | Job posting deadline has passed |
| `asset_error` | Worker detection | Resume/cover letter file cannot be accessed |
| `rejected` | User update | Employer rejected the application |
| `interview` | User update | User received an interview invitation |
| `accepted` | User update | User received and accepted an offer |

---

## Transition Table

| From → | To | Who sets it | When |
|--------|----|-------------|------|
| `queued` | `processing` | Celery worker | Task picked up from queue |
| `queued` | `pending_approval` | Guardrail check | Manual review required |
| `queued` | `limit_exceeded` | Guardrail check | Daily limit reached |
| `queued` | `duplicate` | Guardrail check | Already applied |
| `queued` | `expired` | Guardrail check | Job deadline past |
| `pending_approval` | `queued` | User | Approved for submission |
| `pending_approval` | `failed` | User | Rejected / cancelled |
| `processing` | `applied` | Worker | Successful submission |
| `processing` | `failed` | Worker | Automation failed |
| `processing` | `captcha_required` | Worker | CAPTCHA detected |
| `processing` | `asset_error` | Worker | File unreachable |
| `captcha_required` | `processing` | Solver / User | CAPTCHA resolved |
| `captcha_required` | `failed` | Timeout | CAPTCHA unresolvable |
| `asset_error` | `queued` | Worker retry | File now accessible |
| `applied` | `rejected` | User | Got rejection |
| `applied` | `interview` | User | Got interview invite |
| `applied` | `accepted` | User | Got offer (skip interview) |
| `interview` | `accepted` | User | Accepted offer |
| `interview` | `rejected` | User | Post-interview rejection |

---

## Terminal States

The following states have **no outbound transitions**.
Once an application reaches these states, it cannot be moved:

```
FAILED         — Permanent failure after max retries
DUPLICATE      — Idempotency violation
LIMIT_EXCEEDED — Daily cap hit (new submission required next day)
EXPIRED        — Job deadline passed
ACCEPTED       — Offer accepted (final positive outcome)
REJECTED       — Rejection received (can create new application)
```

> **Why not allow re-queuing from FAILED?**
> If automatic retries were exhausted and all failed, allowing re-queue would
> create an infinite retry loop. The correct approach is to file a NEW application
> with a fresh application_id, which starts a clean audit trail.

---

## Enforcement Implementation

The state machine is enforced in `ApplicationService.transition_status()`:

```python
def transition_status(self, application_id, new_status, ...):
    application = await self._get_application(application_id)
    current = ApplicationStatus(application.status)
    allowed = VALID_TRANSITIONS.get(current, set())

    if new_status not in allowed:
        raise InvalidStatusTransitionError(
            f"Cannot transition from '{current}' to '{new_status}'.",
            details={"from": current.value, "to": new_status.value, "allowed": [...]},
        )

    application.status = new_status.value
    # ... write history, write log ...
```

This means:
- **Routes** cannot bypass the check (they use the service).
- **Celery tasks** cannot bypass the check (they use the service).
- **Tests** can verify every illegal transition raises the correct exception.

---

## Adding a New State

To add a new application status:

1. Add the value to `ApplicationStatus` enum in `schemas.py`
2. Add its entry to `VALID_TRANSITIONS` (even if empty = terminal)
3. Add transitions FROM other states that lead to it
4. Write a migration to update the DB CHECK constraint if applicable
5. Update this document

> **The state machine completeness test will fail if step 2 is missed.**
> See `tests/unit/test_status_machine.py::TestStateMachineCompleteness`.
