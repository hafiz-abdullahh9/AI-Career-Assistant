from datetime import datetime
from typing import Dict, Any, Tuple, List

class ResponseValidator:
    """Enforces standard SUCCESS and ERROR JSON envelopes for all specialist tools."""

    REQUIRED_SUCCESS_KEYS = {"status", "data", "timestamp"}
    REQUIRED_ERROR_KEYS = {"status", "error", "timestamp"}
    REQUIRED_ERROR_DETAILS = {"code", "message", "retryable", "recovery_action"}

    @classmethod
    def validate_envelope(cls, payload: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validates that tool response dict conforms to global integration contracts.
        Returns a tuple of (is_valid, list_of_error_strings).
        """
        errors = []
        if not isinstance(payload, dict):
            return False, ["Response output must be a standard dictionary payload."]

        # Validate main status
        status = payload.get("status")
        if status not in ("SUCCESS", "ERROR"):
            errors.append("Field 'status' must be exactly 'SUCCESS' or 'ERROR'.")

        # Validate timestamp presence & formatting
        if "timestamp" not in payload:
            errors.append("Missing required envelope field: 'timestamp'.")
        else:
            try:
                ts = str(payload["timestamp"])
                # Handle Z offset formatting in older python versions
                if ts.endswith("Z"):
                    ts = ts[:-1] + "+00:00"
                datetime.fromisoformat(ts)
            except Exception:
                errors.append("Field 'timestamp' must be a valid ISO 8601 string.")

        # Validate envelope keys depending on status
        if status == "SUCCESS":
            for key in cls.REQUIRED_SUCCESS_KEYS:
                if key not in payload:
                    errors.append(f"Missing success envelope field: '{key}'.")
            if "data" in payload and not isinstance(payload["data"], dict):
                errors.append("Success payload 'data' field must be a dictionary.")

        elif status == "ERROR":
            for key in cls.REQUIRED_ERROR_KEYS:
                if key not in payload:
                    errors.append(f"Missing error envelope field: '{key}'.")
            
            error_content = payload.get("error")
            if isinstance(error_content, dict):
                for detail_key in cls.REQUIRED_ERROR_DETAILS:
                    if detail_key not in error_content:
                        errors.append(f"Missing detailed error key: 'error -> {detail_key}'.")
                if "retryable" in error_content and not isinstance(error_content["retryable"], bool):
                    errors.append("Field 'error -> retryable' must be a boolean.")
            else:
                errors.append("Error envelope 'error' field must be a dictionary.")

        return len(errors) == 0, errors
