from typing import Tuple, List
from infra.profile_context import ProfileContext

class ContextValidator:
    """Enforces pipeline state continuity and metadata constraints on ProfileContext runtime objects."""

    VALID_STATES = {
        "IDLE", "STATE_PARSING", "STATE_DISCOVERY", "STATE_VERIFICATION",
        "STATE_MATCHING", "STATE_SELECTION_WAIT", "STATE_CUSTOMIZATION",
        "STATE_GUARDRAIL_CHECK", "STATE_APPLICATION", "STATE_TRACKING",
        "STATE_PREPARATION", "STATE_COMPLETED", "STATE_PARSING_FAILED",
        "STATE_DISCOVERY_FAILED", "STATE_VERIFICATION_FAILED",
        "STATE_MATCHING_FAILED", "STATE_CUSTOMIZATION_FAILED",
        "STATE_GUARDRAIL_BREACH", "STATE_APPLICATION_FAILED"
    }

    @classmethod
    def validate_state_continuity(cls, context: ProfileContext) -> Tuple[bool, List[str]]:
        """
        Ensures state machine variables and sequential execution dependencies are valid.
        Returns a tuple of (is_valid, list_of_mismatch_strings).
        """
        errors = []
        state = context.pipeline_state

        # Check state identification registry
        if state not in cls.VALID_STATES:
            errors.append(f"Invalid state ID encountered in current context: '{state}'")

        # Validate that CV profile is populated once parsing finishes
        if state not in ("IDLE", "STATE_PARSING", "STATE_PARSING_FAILED"):
            if not context.profile_data.name or not context.profile_data.email:
                errors.append(f"State '{state}' requires populated user profile details.")

        # Validate that jobs queue exists after discovery and company verification
        if state in ("STATE_MATCHING", "STATE_SELECTION_WAIT", "STATE_CUSTOMIZATION", "STATE_GUARDRAIL_CHECK"):
            if not context.job_queue:
                errors.append(f"State '{state}' requires a populated job recommendation queue.")

        # Validate application records exist once submission runs
        if state in ("STATE_APPLICATION", "STATE_TRACKING", "STATE_PREPARATION", "STATE_COMPLETED"):
            if not context.active_applications:
                errors.append(f"State '{state}' requires at least one tracking entry in active_applications.")

        return len(errors) == 0, errors
