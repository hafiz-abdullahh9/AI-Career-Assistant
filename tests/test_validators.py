import pytest
from datetime import datetime
from validators.schema_validator import SchemaValidator
from validators.response_validator import ResponseValidator
from validators.context_validator import ContextValidator
from infra.profile_context import ProfileData, JobItem, ProfileContext

def test_schema_validator_success():
    """Verifies valid schema inputs succeed."""
    data = {
        "name": "Bob",
        "email": "bob@example.com",
        "skills": ["Python"],
        "experience": [],
        "education": [],
        "raw_cv_text": "Bob CV"
    }
    is_valid, errs = SchemaValidator.validate_data(ProfileData, data)
    assert is_valid is True
    assert len(errs) == 0

def test_schema_validator_failure():
    """Verifies schema validation catches missing or bad fields."""
    data = {
        "name": "Bob",
        # email missing
        "skills": "not-a-list" # should be a list
    }
    is_valid, errs = SchemaValidator.validate_data(ProfileData, data)
    assert is_valid is False
    assert len(errs) > 0

def test_response_validator_success():
    """Verifies that standard success and error envelope payloads pass validation."""
    success_payload = {
        "status": "SUCCESS",
        "data": {"key": "val"},
        "timestamp": "2026-06-14T02:32:00Z"
    }
    is_valid, errs = ResponseValidator.validate_envelope(success_payload)
    assert is_valid is True

    error_payload = {
        "status": "ERROR",
        "error": {
            "code": "API_UNAVAILABLE",
            "message": "Out of memory",
            "retryable": True,
            "recovery_action": "RETRY_WITH_BACKOFF"
        },
        "timestamp": "2026-06-14T02:32:00Z"
    }
    is_valid, errs = ResponseValidator.validate_envelope(error_payload)
    assert is_valid is True

def test_response_validator_failure():
    """Verifies that broken envelopes fail validation."""
    broken_payload = {
        "status": "INVALID",
        "timestamp": "bad-time"
    }
    is_valid, errs = ResponseValidator.validate_envelope(broken_payload)
    assert is_valid is False
    assert len(errs) > 0

def test_context_validator_continuity():
    """Verifies state machine continuity validation."""
    profile = ProfileData(name="Bob", email="bob@example.com", raw_cv_text="CV")
    
    # State requires jobs queue, but it's empty
    context = ProfileContext(
        user_id="usr-1",
        profile_data=profile,
        job_queue=[],
        pipeline_state="STATE_MATCHING"
    )
    is_valid, errs = ContextValidator.validate_state_continuity(context)
    assert is_valid is False
    assert any("requires a populated job recommendation queue" in e for e in errs)
