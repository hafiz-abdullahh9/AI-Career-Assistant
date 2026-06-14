"""
Exhaustive State Machine Tests

Validates EVERY state transition in the ApplicationStatus state machine.
These tests are the canonical specification of what transitions are legal.

Tests are organized as:
  - legal_transitions_from_{state}: all valid paths out of a state
  - illegal_transitions_from_{state}: all invalid paths that must be rejected
"""
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock

from app.core.exceptions import InvalidStatusTransitionError, NotFoundError
from app.models.schemas import ApplicationStatus, VALID_TRANSITIONS
from app.models.orm import Application, ApplicationStatusHistory


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_mock_application(status: ApplicationStatus) -> MagicMock:
    """Create a mock Application ORM object in a given status."""
    app = MagicMock(spec=Application)
    app.application_id = uuid.UUID("9d3e4e20-f56c-4b77-8f81-abcdef012345")
    app.status = status.value
    app.company_name = "Test Corp"
    app.role_title = "Engineer"
    app.method = "email"
    app.retry_count = 0
    app.max_retries = 3
    return app


# ── Completeness Tests ─────────────────────────────────────────────────────────

class TestStateMachineCompleteness:
    """Every status must appear in VALID_TRANSITIONS."""

    def test_all_statuses_covered(self):
        for status in ApplicationStatus:
            assert status in VALID_TRANSITIONS, (
                f"ApplicationStatus.{status} is missing from VALID_TRANSITIONS. "
                "Add it with its allowed outbound transitions (or empty set if terminal)."
            )

    def test_all_transition_targets_are_valid_statuses(self):
        """Every status referenced as a transition target must be a valid enum value."""
        valid_values = set(ApplicationStatus)
        for from_status, allowed_set in VALID_TRANSITIONS.items():
            for to_status in allowed_set:
                assert to_status in valid_values, (
                    f"Transition target '{to_status}' in {from_status} transitions "
                    "is not a valid ApplicationStatus value."
                )

    def test_no_self_transitions_defined(self):
        """A status should not transition to itself (would be a no-op / bug)."""
        for status, allowed in VALID_TRANSITIONS.items():
            assert status not in allowed, (
                f"Self-transition detected: {status} → {status}. "
                "Status transitions must change state."
            )


# ── Terminal State Tests ───────────────────────────────────────────────────────

class TestTerminalStates:
    """Terminal states must have NO outbound transitions."""

    TERMINAL_STATES = [
        ApplicationStatus.FAILED,
        ApplicationStatus.DUPLICATE,
        ApplicationStatus.LIMIT_EXCEEDED,
        ApplicationStatus.EXPIRED,
        ApplicationStatus.ACCEPTED,
        ApplicationStatus.REJECTED,
    ]

    @pytest.mark.parametrize("status", TERMINAL_STATES)
    def test_terminal_state_has_no_outbound_transitions(self, status: ApplicationStatus):
        allowed = VALID_TRANSITIONS[status]
        assert len(allowed) == 0, (
            f"{status} should be terminal but has outbound transitions: {allowed}"
        )


# ── Legal Transition Tests ─────────────────────────────────────────────────────

class TestLegalTransitions:
    """Every legal transition in the state machine must pass validation."""

    @pytest.mark.parametrize("from_status,to_status", [
        (from_s, to_s)
        for from_s, allowed_set in VALID_TRANSITIONS.items()
        for to_s in allowed_set
    ])
    def test_legal_transition_is_in_allowed_set(
        self,
        from_status: ApplicationStatus,
        to_status: ApplicationStatus,
    ):
        allowed = VALID_TRANSITIONS[from_status]
        assert to_status in allowed, (
            f"Expected {from_status} → {to_status} to be legal, but it is not."
        )

    def test_happy_path_queued_to_processing(self):
        assert ApplicationStatus.PROCESSING in VALID_TRANSITIONS[ApplicationStatus.QUEUED]

    def test_happy_path_processing_to_applied(self):
        assert ApplicationStatus.APPLIED in VALID_TRANSITIONS[ApplicationStatus.PROCESSING]

    def test_failure_path_processing_to_failed(self):
        assert ApplicationStatus.FAILED in VALID_TRANSITIONS[ApplicationStatus.PROCESSING]

    def test_captcha_path_processing_to_captcha_required(self):
        assert ApplicationStatus.CAPTCHA_REQUIRED in VALID_TRANSITIONS[ApplicationStatus.PROCESSING]

    def test_captcha_resolution_path(self):
        assert ApplicationStatus.PROCESSING in VALID_TRANSITIONS[ApplicationStatus.CAPTCHA_REQUIRED]

    def test_post_application_interview_path(self):
        assert ApplicationStatus.INTERVIEW in VALID_TRANSITIONS[ApplicationStatus.APPLIED]

    def test_post_application_rejection_path(self):
        assert ApplicationStatus.REJECTED in VALID_TRANSITIONS[ApplicationStatus.APPLIED]

    def test_interview_can_lead_to_acceptance(self):
        assert ApplicationStatus.ACCEPTED in VALID_TRANSITIONS[ApplicationStatus.INTERVIEW]

    def test_interview_can_lead_to_rejection(self):
        assert ApplicationStatus.REJECTED in VALID_TRANSITIONS[ApplicationStatus.INTERVIEW]


# ── Illegal Transition Tests ───────────────────────────────────────────────────

class TestIllegalTransitions:
    """Transitions that must be explicitly blocked."""

    ILLEGAL_TRANSITIONS = [
        # Cannot skip states
        (ApplicationStatus.QUEUED, ApplicationStatus.APPLIED,
         "Cannot skip PROCESSING"),
        (ApplicationStatus.QUEUED, ApplicationStatus.INTERVIEW,
         "Cannot skip multiple states"),
        (ApplicationStatus.QUEUED, ApplicationStatus.ACCEPTED,
         "Cannot skip directly to ACCEPTED"),

        # Cannot go backwards
        (ApplicationStatus.PROCESSING, ApplicationStatus.QUEUED,
         "Cannot go backwards"),
        (ApplicationStatus.APPLIED, ApplicationStatus.QUEUED,
         "Cannot requeue after applied"),
        (ApplicationStatus.APPLIED, ApplicationStatus.PROCESSING,
         "Cannot reprocess after applied"),

        # Terminal states cannot transition
        (ApplicationStatus.FAILED, ApplicationStatus.QUEUED,
         "FAILED is terminal"),
        (ApplicationStatus.FAILED, ApplicationStatus.PROCESSING,
         "FAILED is terminal"),
        (ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED,
         "ACCEPTED is terminal"),
        (ApplicationStatus.REJECTED, ApplicationStatus.ACCEPTED,
         "REJECTED is terminal"),
        (ApplicationStatus.DUPLICATE, ApplicationStatus.QUEUED,
         "DUPLICATE is terminal"),
        (ApplicationStatus.LIMIT_EXCEEDED, ApplicationStatus.QUEUED,
         "LIMIT_EXCEEDED is terminal"),
        (ApplicationStatus.EXPIRED, ApplicationStatus.QUEUED,
         "EXPIRED is terminal"),
    ]

    @pytest.mark.parametrize("from_status,to_status,reason", ILLEGAL_TRANSITIONS)
    def test_illegal_transition_not_in_allowed_set(
        self,
        from_status: ApplicationStatus,
        to_status: ApplicationStatus,
        reason: str,
    ):
        allowed = VALID_TRANSITIONS[from_status]
        assert to_status not in allowed, (
            f"Illegal transition {from_status} → {to_status} is unexpectedly ALLOWED. "
            f"Reason it should be blocked: {reason}"
        )


# ── Service-Level Transition Tests ────────────────────────────────────────────

class TestServiceTransitionValidation:
    """Verify the ApplicationService correctly enforces the state machine."""

    @pytest.fixture
    def service_with_app(self, mock_db_session, mock_redis):
        """Return a service pre-loaded with a specific application status."""
        from app.services.application_service import ApplicationService
        return ApplicationService(db=mock_db_session, redis=mock_redis)

    def _mock_app_in_status(self, status: ApplicationStatus, mock_db_session):
        """Configure mock_db_session.execute to return an app in the given status."""
        app = make_mock_application(status)
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=app)
        mock_db_session.execute = AsyncMock(return_value=result)
        return app

    @pytest.mark.asyncio
    async def test_service_allows_queued_to_processing(
        self, service_with_app, mock_db_session
    ):
        app = self._mock_app_in_status(ApplicationStatus.QUEUED, mock_db_session)
        # Should not raise
        result = await service_with_app.transition_status(
            application_id=str(app.application_id),
            new_status=ApplicationStatus.PROCESSING,
            reason="Test",
        )
        assert result.status == ApplicationStatus.PROCESSING.value

    @pytest.mark.asyncio
    async def test_service_rejects_queued_to_applied(
        self, service_with_app, mock_db_session
    ):
        app = self._mock_app_in_status(ApplicationStatus.QUEUED, mock_db_session)
        with pytest.raises(InvalidStatusTransitionError) as exc_info:
            await service_with_app.transition_status(
                application_id=str(app.application_id),
                new_status=ApplicationStatus.APPLIED,
            )
        assert "INVALID_STATUS_TRANSITION" in exc_info.value.error_code
        assert "queued" in exc_info.value.message.lower()
        assert "applied" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_service_rejects_failed_to_processing(
        self, service_with_app, mock_db_session
    ):
        app = self._mock_app_in_status(ApplicationStatus.FAILED, mock_db_session)
        with pytest.raises(InvalidStatusTransitionError):
            await service_with_app.transition_status(
                application_id=str(app.application_id),
                new_status=ApplicationStatus.PROCESSING,
            )

    @pytest.mark.asyncio
    async def test_service_raises_not_found_for_missing_app(
        self, service_with_app, mock_db_session
    ):
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db_session.execute = AsyncMock(return_value=result)

        with pytest.raises(NotFoundError) as exc_info:
            await service_with_app.transition_status(
                application_id=str(uuid.uuid4()),
                new_status=ApplicationStatus.PROCESSING,
            )
        assert "NOT_FOUND" in exc_info.value.error_code

    @pytest.mark.asyncio
    async def test_error_details_include_allowed_transitions(
        self, service_with_app, mock_db_session
    ):
        """The error details must list the allowed transitions for debugging."""
        app = self._mock_app_in_status(ApplicationStatus.FAILED, mock_db_session)
        with pytest.raises(InvalidStatusTransitionError) as exc_info:
            await service_with_app.transition_status(
                application_id=str(app.application_id),
                new_status=ApplicationStatus.QUEUED,
            )
        assert "allowed" in exc_info.value.details
        assert isinstance(exc_info.value.details["allowed"], list)
