from typing import Type, Dict, Any, Tuple, List
from pydantic import ValidationError
from infra.profile_context import ProfileData, JobItem, ApplicationItem, ProfileContext

class SchemaValidator:
    """Lightweight passive schema validator to enforce pydantic compliance on tool data inputs."""

    @staticmethod
    def validate_data(model_cls: Type, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validates dictionary data against Pydantic schema model.
        Returns a tuple of (is_valid, list_of_error_strings).
        """
        try:
            if hasattr(model_cls, "model_validate"): # Support Pydantic V2
                model_cls.model_validate(data)
            else:
                model_cls.parse_obj(data)
            return True, []
        except ValidationError as e:
            errors = []
            for error in e.errors():
                loc = " -> ".join(str(field) for field in error.get("loc", []))
                msg = error.get("msg", "Validation mismatch")
                errors.append(f"[{loc}]: {msg}")
            return False, errors
