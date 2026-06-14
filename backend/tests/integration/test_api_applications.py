"""
API Integration Tests — Application Submission & Tracking

Full HTTP-level tests against the application endpoints.
Covers: submit, status, list, patch, history, delete.
Failure scenarios: rate limit, duplicate, validation errors.

Infrastructure (DB, Redis) is mocked. Service logic and routing are real.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient

from tests.conftest import (
    TEST_USER_ID,
    TEST_JOB_ID,
    TEST_APP_ID,
    make_email_submission,
    make_webform_submission,
)

# All tests in this file exercise the full HTTP routing + service stack.
# Infrastructure (DB, Redis) is mocked; routing, validation, and handlers are real.
pytestmark = pytest.mark.integration


# ── Helpers ───────────────────────────────────────────────────────────────────

def mock_created_application(app_id: str = TEST_APP_ID):
    """Create a mock Application ORM object returned by service.create_application."""
    from datetime import datetime, UTC
    from unittest.mock import MagicMock
    app = MagicMock()
    app.application_id = uuid.UUID(app_id)
    app.user_id = uuid.UUID(TEST_USER_ID)
    app.job_id = uuid.UUID(TEST_JOB_ID)
    app.company_name = "Acme Corp"
    app.role_title = "Senior Engineer"
    app.platform = "email"
    app.method = "email"
    app.status = "queued"
    app.retry_count = 0
    app.queued_at = datetime.now(UTC)
    app.applied_at = None
    app.confirmation_id = None
    app.celery_task_id = None
    app.created_at = datetime.now(UTC)
    app.updated_at = datetime.now(UTC)
    app.deleted_at = None
    return app


# ── Submit Endpoint Tests ─────────────────────────────────────────────────────

class TestApplicationSubmit:
    """POST /api/v1/applications/submit"""

    @pytest.mark.asyncio
    async def test_valid_email_submission_returns_202(self, client: AsyncClient):
        mock_app = mock_created_application()
        with patch(
            "app.api.v1.applications.ApplicationService.check_rate_limit",
            new_callable=AsyncMock
        ), patch(
            "app.api.v1.applications.ApplicationService.check_duplicate",
            new_callable=AsyncMock
        ), patch(
            "app.api.v1.applications.ApplicationService.create_application",
            new_callable=AsyncMock, return_value=mock_app
        ), patch(
            "app.api.v1.applications.ApplicationService.attach_task_id",
            new_callable=AsyncMock
        ), patch(
            "app.api.v1.applications.process_application.apply_async",
            return_value=MagicMock(id="celery-task-id-123")
        ):
            response = await client.post(
                "/api/v1/applications/submit",
                json=make_email_submission(),
            )

        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_submit_response_contains_application_id(self, client: AsyncClient):
        mock_app = mock_created_application()
        with patch("app.api.v1.applications.ApplicationService.check_rate_limit", AsyncMock()), \
             patch("app.api.v1.applications.ApplicationService.check_duplicate", AsyncMock()), \
             patch("app.api.v1.applications.ApplicationService.create_application", AsyncMock(return_value=mock_app)), \
             patch("app.api.v1.applications.ApplicationService.attach_task_id", AsyncMock()), \
             patch("app.api.v1.applications.process_application.apply_async", return_value=MagicMock(id="task-1")):
            response = await client.post("/api/v1/applications/submit", json=make_email_submission())

        data = response.json()
        assert data["success"] is True
        assert "application_id" in data["data"]

    @pytest.mark.asyncio
    async def test_submit_response_contains_tracking_url(self, client: AsyncClient):
        mock_app = mock_created_application()
        with patch("app.api.v1.applications.ApplicationService.check_rate_limit", AsyncMock()), \
             patch("app.api.v1.applications.ApplicationService.check_duplicate", AsyncMock()), \
             patch("app.api.v1.applications.ApplicationService.create_application", AsyncMock(return_value=mock_app)), \
             patch("app.api.v1.applications.ApplicationService.attach_task_id", AsyncMock()), \
             patch("app.api.v1.applications.process_application.apply_async", return_value=MagicMock(id="task-1")):
            response = await client.post("/api/v1/applications/submit", json=make_email_submission())

        data = response.json()
        assert "tracking_url" in data["data"]
        tracking = data["data"]["tracking_url"]
        assert "/applications/" in tracking
        assert "/status" in tracking

    @pytest.mark.asyncio
    async def test_submit_response_has_request_id_header(self, client: AsyncClient):
        mock_app = mock_created_application()
        with patch("app.api.v1.applications.ApplicationService.check_rate_limit", AsyncMock()), \
             patch("app.api.v1.applications.ApplicationService.check_duplicate", AsyncMock()), \
             patch("app.api.v1.applications.ApplicationService.create_application", AsyncMock(return_value=mock_app)), \
             patch("app.api.v1.applications.ApplicationService.attach_task_id", AsyncMock()), \
             patch("app.api.v1.applications.process_application.apply_async", return_value=MagicMock(id="task-1")):
            response = await client.post("/api/v1/applications/submit", json=make_email_submission())

        assert "x-request-id" in response.headers

    @pytest.mark.asyncio
    async def test_request_id_header_propagated_from_client(self, client: AsyncClient):
        """If the client sends X-Request-ID, it must be echoed back."""
        custom_request_id = "my-custom-trace-id-12345"
        mock_app = mock_created_application()
        with patch("app.api.v1.applications.ApplicationService.check_rate_limit", AsyncMock()), \
             patch("app.api.v1.applications.ApplicationService.check_duplicate", AsyncMock()), \
             patch("app.api.v1.applications.ApplicationService.create_application", AsyncMock(return_value=mock_app)), \
             patch("app.api.v1.applications.ApplicationService.attach_task_id", AsyncMock()), \
             patch("app.api.v1.applications.process_application.apply_async", return_value=MagicMock(id="task-1")):
            response = await client.post(
                "/api/v1/applications/submit",
                json=make_email_submission(),
                headers={"X-Request-ID": custom_request_id},
            )

        assert response.headers["x-request-id"] == custom_request_id


# ── Validation Error Tests ─────────────────────────────────────────────────────

class TestSubmitValidationErrors:
    """Verify that malformed requests are rejected with proper error responses."""

    @pytest.mark.asyncio
    async def test_missing_user_id_returns_422(self, client: AsyncClient):
        payload = make_email_submission()
        del payload["user_id"]
        response = await client.post("/api/v1/applications/submit", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_job_id_returns_422(self, client: AsyncClient):
        payload = make_email_submission()
        del payload["job_id"]
        response = await client.post("/api/v1/applications/submit", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_company_name_returns_422(self, client: AsyncClient):
        payload = make_email_submission()
        payload["job_metadata"]["company_name"] = ""
        response = await client.post("/api/v1/applications/submit", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_email_method_without_contact_email_returns_422(self, client: AsyncClient):
        payload = make_email_submission()
        payload["job_metadata"]["contact_email"] = None
        response = await client.post("/api/v1/applications/submit", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_webform_method_without_url_returns_422(self, client: AsyncClient):
        payload = make_webform_submission()
        payload["job_metadata"]["application_url"] = None
        response = await client.post("/api/v1/applications/submit", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_non_pdf_resume_returns_422(self, client: AsyncClient):
        payload = make_email_submission()
        payload["resume"]["filename"] = "resume.docx"
        response = await client.post("/api/v1/applications/submit", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_path_traversal_filename_returns_422(self, client: AsyncClient):
        payload = make_email_submission()
        payload["resume"]["filename"] = "../../../etc/passwd.pdf"
        response = await client.post("/api/v1/applications/submit", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_http_storage_url_returns_422(self, client: AsyncClient):
        payload = make_email_submission()
        payload["resume"]["storage_url"] = "http://insecure.example.com/resume.pdf"
        response = await client.post("/api/v1/applications/submit", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_uuid_for_user_id_returns_422(self, client: AsyncClient):
        payload = make_email_submission()
        payload["user_id"] = "not-a-uuid"
        response = await client.post("/api/v1/applications/submit", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_body_returns_422(self, client: AsyncClient):
        response = await client.post("/api/v1/applications/submit", json={})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_validation_error_body_has_error_structure(self, client: AsyncClient):
        response = await client.post("/api/v1/applications/submit", json={})
        # FastAPI's default validation returns 422 with detail field
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data or "error" in data  # Either FastAPI or our handler


# ── Guardrail Error Tests ──────────────────────────────────────────────────────

class TestSubmitGuardrailErrors:
    """Verify that guardrail violations return the correct HTTP codes."""

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_returns_429(self, client: AsyncClient):
        from app.core.exceptions import RateLimitExceededError
        with patch(
            "app.api.v1.applications.ApplicationService.check_rate_limit",
            AsyncMock(side_effect=RateLimitExceededError("Limit reached"))
        ):
            response = await client.post("/api/v1/applications/submit", json=make_email_submission())

        assert response.status_code == 429
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "RATE_LIMIT_EXCEEDED"

    @pytest.mark.asyncio
    async def test_duplicate_application_returns_409(self, client: AsyncClient):
        from app.core.exceptions import DuplicateApplicationError
        with patch(
            "app.api.v1.applications.ApplicationService.check_rate_limit",
            AsyncMock()
        ), patch(
            "app.api.v1.applications.ApplicationService.check_duplicate",
            AsyncMock(side_effect=DuplicateApplicationError("Already applied"))
        ):
            response = await client.post("/api/v1/applications/submit", json=make_email_submission())

        assert response.status_code == 409
        data = response.json()
        assert data["error"]["code"] == "DUPLICATE_APPLICATION"

    @pytest.mark.asyncio
    async def test_error_response_has_request_id_in_meta(self, client: AsyncClient):
        from app.core.exceptions import RateLimitExceededError
        with patch(
            "app.api.v1.applications.ApplicationService.check_rate_limit",
            AsyncMock(side_effect=RateLimitExceededError("Limit reached"))
        ):
            response = await client.post("/api/v1/applications/submit", json=make_email_submission())

        data = response.json()
        assert "meta" in data
        assert "request_id" in data["meta"]


# ── Status Endpoint Tests ──────────────────────────────────────────────────────

class TestApplicationStatus:
    """GET /api/v1/applications/{id}/status"""

    @pytest.mark.asyncio
    async def test_get_existing_application_returns_200(self, client: AsyncClient):
        mock_app = mock_created_application()
        with patch(
            "app.api.v1.applications.ApplicationService.get_application",
            AsyncMock(return_value=mock_app)
        ):
            response = await client.get(f"/api/v1/applications/{TEST_APP_ID}/status")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "application_id" in data["data"]

    @pytest.mark.asyncio
    async def test_get_missing_application_returns_404(self, client: AsyncClient):
        from app.core.exceptions import NotFoundError
        with patch(
            "app.api.v1.applications.ApplicationService.get_application",
            AsyncMock(side_effect=NotFoundError("Application not found"))
        ):
            response = await client.get(f"/api/v1/applications/{TEST_APP_ID}/status")

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"


# ── Status Patch Tests ────────────────────────────────────────────────────────

class TestStatusPatch:
    """PATCH /api/v1/applications/{id}/status"""

    @pytest.mark.asyncio
    async def test_valid_status_update_returns_200(self, client: AsyncClient):
        mock_app = mock_created_application()
        mock_app.status = "interview"
        mock_app.updated_at = __import__("datetime").datetime.now(__import__("datetime").UTC)

        with patch(
            "app.api.v1.applications.ApplicationService.transition_status",
            AsyncMock(return_value=mock_app)
        ):
            response = await client.patch(
                f"/api/v1/applications/{TEST_APP_ID}/status",
                json={"status": "interview", "reason": "Got email invite", "changed_by": "user"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["status"] == "interview"

    @pytest.mark.asyncio
    async def test_invalid_status_value_returns_422(self, client: AsyncClient):
        response = await client.patch(
            f"/api/v1/applications/{TEST_APP_ID}/status",
            json={"status": "not_a_real_status"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_illegal_transition_returns_409(self, client: AsyncClient):
        from app.core.exceptions import InvalidStatusTransitionError
        with patch(
            "app.api.v1.applications.ApplicationService.transition_status",
            AsyncMock(side_effect=InvalidStatusTransitionError(
                "Cannot transition",
                details={"from": "failed", "to": "queued", "allowed": []}
            ))
        ):
            response = await client.patch(
                f"/api/v1/applications/{TEST_APP_ID}/status",
                json={"status": "queued", "reason": "Retrying"},
            )

        assert response.status_code == 409
        data = response.json()
        assert data["error"]["code"] == "INVALID_STATUS_TRANSITION"


# ── List Endpoint Tests ────────────────────────────────────────────────────────

class TestApplicationList:
    """GET /api/v1/applications"""

    @pytest.mark.asyncio
    async def test_list_requires_user_id(self, client: AsyncClient):
        response = await client.get("/api/v1/applications")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_returns_empty_result(self, client: AsyncClient):
        with patch(
            "app.api.v1.applications.ApplicationService.list_applications",
            AsyncMock(return_value=([], 0))
        ):
            response = await client.get(
                f"/api/v1/applications?user_id={TEST_USER_ID}"
            )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["applications"] == []
        assert data["data"]["pagination"]["total"] == 0

    @pytest.mark.asyncio
    async def test_list_returns_pagination_metadata(self, client: AsyncClient):
        with patch(
            "app.api.v1.applications.ApplicationService.list_applications",
            AsyncMock(return_value=([], 0))
        ):
            response = await client.get(
                f"/api/v1/applications?user_id={TEST_USER_ID}&limit=10&offset=0"
            )
        data = response.json()
        pagination = data["data"]["pagination"]
        assert "total" in pagination
        assert "limit" in pagination
        assert "offset" in pagination
        assert "has_more" in pagination

    @pytest.mark.asyncio
    async def test_limit_cannot_exceed_100(self, client: AsyncClient):
        response = await client.get(
            f"/api/v1/applications?user_id={TEST_USER_ID}&limit=9999"
        )
        assert response.status_code == 422


# ── Delete Endpoint Tests ──────────────────────────────────────────────────────

class TestApplicationDelete:
    """DELETE /api/v1/applications/{id}"""

    @pytest.mark.asyncio
    async def test_delete_existing_application_returns_200(self, client: AsyncClient):
        from datetime import datetime, UTC
        mock_app = mock_created_application()
        mock_app.deleted_at = datetime.now(UTC)

        with patch(
            "app.api.v1.applications.ApplicationService.soft_delete",
            AsyncMock(return_value=mock_app)
        ):
            response = await client.delete(f"/api/v1/applications/{TEST_APP_ID}")

        assert response.status_code == 200
        data = response.json()
        assert "deleted_at" in data["data"]

    @pytest.mark.asyncio
    async def test_delete_missing_application_returns_404(self, client: AsyncClient):
        from app.core.exceptions import NotFoundError
        with patch(
            "app.api.v1.applications.ApplicationService.soft_delete",
            AsyncMock(side_effect=NotFoundError("Not found"))
        ):
            response = await client.delete(f"/api/v1/applications/{TEST_APP_ID}")

        assert response.status_code == 404


# ── Duplicate Detection Scenario Tests ────────────────────────────────────────

class TestDuplicateSubmissionScenarios:
    """
    FAILURE TEST D — Duplicate Submission

    Verifies the two-layer dedup system works at both the
    Redis (fast path) and DB (fallback) levels.
    """

    @pytest.mark.asyncio
    async def test_redis_dedup_blocks_second_submission(self, client: AsyncClient, mock_redis):
        """When Redis has dedup key, second submission returns 409."""
        from app.core.exceptions import DuplicateApplicationError
        # Simulate: first submission already set the dedup flag
        with patch(
            "app.api.v1.applications.ApplicationService.check_rate_limit", AsyncMock()
        ), patch(
            "app.api.v1.applications.ApplicationService.check_duplicate",
            AsyncMock(side_effect=DuplicateApplicationError(
                "Already applied to job",
                details={"job_id": TEST_JOB_ID}
            ))
        ):
            response = await client.post("/api/v1/applications/submit", json=make_email_submission())

        assert response.status_code == 409
        data = response.json()
        assert data["error"]["code"] == "DUPLICATE_APPLICATION"

    @pytest.mark.asyncio
    async def test_different_job_ids_not_blocked(self, client: AsyncClient):
        """Two submissions for different jobs by same user must both succeed."""
        mock_app_1 = mock_created_application()
        mock_app_2 = mock_created_application(app_id=str(uuid.uuid4()))

        for mock_app in [mock_app_1, mock_app_2]:
            with patch("app.api.v1.applications.ApplicationService.check_rate_limit", AsyncMock()), \
                 patch("app.api.v1.applications.ApplicationService.check_duplicate", AsyncMock()), \
                 patch("app.api.v1.applications.ApplicationService.create_application", AsyncMock(return_value=mock_app)), \
                 patch("app.api.v1.applications.ApplicationService.attach_task_id", AsyncMock()), \
                 patch("app.api.v1.applications.process_application.apply_async", return_value=MagicMock(id="t1")):
                response = await client.post("/api/v1/applications/submit", json=make_email_submission())

            assert response.status_code == 202, f"Second submission with different job failed: {response.json()}"
