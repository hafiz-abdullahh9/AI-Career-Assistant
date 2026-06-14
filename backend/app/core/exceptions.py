"""
Custom exception hierarchy for the Application Automation Agent.

Design rules:
  1. All domain exceptions inherit from AppBaseError.
  2. Each exception carries a machine-readable error_code.
  3. HTTP status codes are defined here, not in route handlers.
  4. Route handlers catch AppBaseError and convert to JSON automatically.
"""
from typing import Any


class AppBaseError(Exception):
    """
    Base class for all application-domain exceptions.

    Attributes:
        error_code:  Machine-readable snake_case code (used in API error responses).
        message:     Human-readable description.
        status_code: Suggested HTTP status code.
        details:     Optional structured context (field errors, etc.).
    """

    error_code: str = "INTERNAL_ERROR"
    status_code: int = 500

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


# ── Validation ─────────────────────────────────────────────────────────────────

class ValidationError(AppBaseError):
    error_code = "VALIDATION_ERROR"
    status_code = 400


class BadRequestError(AppBaseError):
    error_code = "BAD_REQUEST"
    status_code = 400


# ── Authorization ──────────────────────────────────────────────────────────────

class UnauthorizedError(AppBaseError):
    error_code = "UNAUTHORIZED"
    status_code = 401


class ForbiddenError(AppBaseError):
    error_code = "FORBIDDEN"
    status_code = 403


# ── Resource state ─────────────────────────────────────────────────────────────

class NotFoundError(AppBaseError):
    error_code = "NOT_FOUND"
    status_code = 404


class ConflictError(AppBaseError):
    error_code = "CONFLICT"
    status_code = 409


# ── Guardrail violations ───────────────────────────────────────────────────────

class RateLimitExceededError(AppBaseError):
    """Raised when a user hits their daily application limit."""
    error_code = "RATE_LIMIT_EXCEEDED"
    status_code = 429


class UnverifiedJobError(AppBaseError):
    """Raised when the target job has not been verified by the Job Verification Agent."""
    error_code = "UNVERIFIED_JOB"
    status_code = 403


class DuplicateApplicationError(AppBaseError):
    """Raised when the user has already applied to this specific job."""
    error_code = "DUPLICATE_APPLICATION"
    status_code = 409


class JobExpiredError(AppBaseError):
    """Raised when the job's application deadline has passed."""
    error_code = "JOB_EXPIRED"
    status_code = 410


class AssetUnreachableError(AppBaseError):
    """Raised when resume or cover letter files cannot be accessed."""
    error_code = "ASSET_UNREACHABLE"
    status_code = 422


# ── Automation errors ──────────────────────────────────────────────────────────

class AutomationError(AppBaseError):
    """Base for all automation-layer errors."""
    error_code = "AUTOMATION_ERROR"
    status_code = 500


class TransientAutomationError(AutomationError):
    """Temporary error that can be retried (network timeout, browser crash, etc.)."""
    error_code = "TRANSIENT_AUTOMATION_ERROR"


class PermanentAutomationError(AutomationError):
    """Permanent error that should NOT be retried (IP ban, invalid URL, etc.)."""
    error_code = "PERMANENT_AUTOMATION_ERROR"


class CaptchaBlockedError(AutomationError):
    """Raised when a CAPTCHA cannot be solved automatically."""
    error_code = "CAPTCHA_BLOCKED"
    status_code = 503


# ── Infrastructure ─────────────────────────────────────────────────────────────

class DatabaseError(AppBaseError):
    error_code = "DATABASE_ERROR"
    status_code = 500


class RedisError(AppBaseError):
    error_code = "REDIS_ERROR"
    status_code = 500


class InvalidStatusTransitionError(AppBaseError):
    """Raised when an illegal application status transition is attempted."""
    error_code = "INVALID_STATUS_TRANSITION"
    status_code = 409


# ── Email Service Errors ────────────────────────────────────────────────────────

class EmailError(AppBaseError):
    """Base exception for all email delivery issues."""
    error_code = "EMAIL_ERROR"
    status_code = 500


class RetryableEmailError(EmailError, TransientAutomationError):
    """Temporary email sending issues that should be retried."""
    error_code = "RETRYABLE_EMAIL_ERROR"


class PermanentEmailError(EmailError, PermanentAutomationError):
    """Permanent email delivery failures that should not be retried."""
    error_code = "PERMANENT_EMAIL_ERROR"


class EmailTimeoutError(RetryableEmailError):
    error_code = "EMAIL_TIMEOUT"


class TemporarySMTPFailureError(RetryableEmailError):
    error_code = "TEMPORARY_SMTP_FAILURE"


class EmailConnectionResetError(RetryableEmailError):
    error_code = "EMAIL_CONNECTION_RESET"


class EmailAuthFailureError(PermanentEmailError):
    error_code = "EMAIL_AUTH_FAILURE"


class InvalidRecipientError(PermanentEmailError):
    error_code = "INVALID_RECIPIENT"


class InvalidAttachmentError(PermanentEmailError):
    error_code = "INVALID_ATTACHMENT"


class MalformedEmailError(PermanentEmailError):
    error_code = "MALFORMED_EMAIL"

