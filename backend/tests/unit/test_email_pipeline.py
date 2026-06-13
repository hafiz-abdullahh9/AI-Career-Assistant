import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.exceptions import (
    EmailTimeoutError,
    EmailConnectionResetError,
    TemporarySMTPFailureError,
    EmailAuthFailureError,
    InvalidRecipientError,
    InvalidAttachmentError,
    MalformedEmailError,
    RetryableEmailError,
    PermanentEmailError,
    InvalidStatusTransitionError,
)
from app.email.services.email_service import EmailService
from app.email.schemas.email import EmailResponse, EmailFailure
from app.models.orm import Application, EmailSend
from app.models.schemas import ApplicationStatus, VALID_TRANSITIONS


@pytest.fixture
def email_service(mock_db_session) -> EmailService:
    return EmailService(db=mock_db_session)


@pytest.fixture
def mock_application() -> Application:
    app = MagicMock(spec=Application)
    app.application_id = uuid.uuid4()
    app.user_id = uuid.uuid4()
    app.job_id = uuid.uuid4()
    app.company_name = "MockCorp"
    app.role_title = "Data Scientist"
    app.contact_email = "hr@mockcorp.example.com"
    app.status = ApplicationStatus.EMAIL_QUEUED.value
    app.retry_count = 0
    app.metadata_ = {
        "candidate_name": "Alice Bob",
        "resume": {
            "version_id": str(uuid.uuid4()),
            "storage_url": "https://storage.example.com/resume.pdf",
            "filename": "alice_resume.pdf"
        },
        "cover_letter": {
            "version_id": str(uuid.uuid4()),
            "storage_url": "https://storage.example.com/letter.pdf",
            "filename": "alice_letter.pdf",
            "content_text": "Please consider me for the role."
        }
    }
    return app


# ── Step 1: Template Rendering Tests ──────────────────────────────────────────

def test_template_rendering_success(email_service):
    """Verify that templates render HTML and Plain Text with injected variables."""
    body_text, body_html = email_service.render_templates(
        candidate_name="Alice Bob",
        company_name="MockCorp",
        role="Data Scientist",
        custom_message="Please consider me.",
        contact_name="HR Manager"
    )

    assert "Alice Bob" in body_text
    assert "MockCorp" in body_text
    assert "Data Scientist" in body_text
    assert "Please consider me." in body_text
    assert "HR Manager" in body_text

    assert "Alice Bob" in body_html
    assert "MockCorp" in body_html
    assert "Data Scientist" in body_html
    assert "Please consider me." in body_html
    assert "HR Manager" in body_html


# ── Step 2: Attachment Validation Tests ────────────────────────────────────────

@pytest.mark.asyncio
async def test_prepare_attachments_valid(email_service, mock_application):
    """Verify that valid attachments are accepted."""
    with patch.object(email_service, "download_asset", new_callable=AsyncMock) as mock_download:
        # Return valid PDF and DOCX bytes respectively
        mock_download.side_effect = [b"%PDF-1.4...", b"PK\x03\x04doccontent..."]
        
        # Change second attachment filename to DOCX
        mock_application.metadata_["cover_letter"]["filename"] = "letter.docx"

        attachments = await email_service.prepare_attachments(mock_application)
        assert len(attachments) == 2
        assert attachments[0].filename == "alice_resume.pdf"
        assert attachments[1].filename == "letter.docx"


@pytest.mark.asyncio
async def test_prepare_attachments_invalid_pdf(email_service, mock_application):
    """Verify that invalid PDF content is rejected."""
    with patch.object(email_service, "download_asset", new_callable=AsyncMock) as mock_download:
        mock_download.return_value = b"Not a PDF header"

        with pytest.raises(InvalidAttachmentError, match="PDF magic bytes"):
            await email_service.prepare_attachments(mock_application)


@pytest.mark.asyncio
async def test_prepare_attachments_invalid_docx(email_service, mock_application):
    """Verify that invalid DOCX content is rejected."""
    with patch.object(email_service, "download_asset", new_callable=AsyncMock) as mock_download:
        # First download (resume) succeeds
        # Second download (cover letter) is docx but invalid zip archive bytes
        mock_download.side_effect = [b"%PDF-1.4...", b"Not a docx PK zip archive"]
        mock_application.metadata_["cover_letter"]["filename"] = "letter.docx"

        with pytest.raises(InvalidAttachmentError, match="PK ZIP archive magic bytes"):
            await email_service.prepare_attachments(mock_application)


# ── Step 3: Provider Selection Tests ───────────────────────────────────────────

def test_provider_selection_gmail(email_service):
    """Selecting domain with gmail.com selects GmailEmailProvider."""
    provider = email_service.select_provider("user@gmail.com")
    from app.email.providers.gmail import GmailEmailProvider
    assert isinstance(provider, GmailEmailProvider)


def test_provider_selection_smtp(email_service):
    """Selecting other domains selects SMTPEmailProvider."""
    provider = email_service.select_provider("user@example.com")
    from app.email.providers.smtp import SMTPEmailProvider
    assert isinstance(provider, SMTPEmailProvider)


# ── Step 4: Retry Classification & Error Handling Tests ───────────────────────

def test_classify_and_raise_error_transient_timeout(email_service):
    failure = EmailFailure(
        success=False,
        error_code="SMTPConnectTimeout",
        error_message="Connection timed out",
        provider="smtp",
        retryable=True,
        latency_ms=100.0,
        timestamp=0.0
    )
    with pytest.raises(EmailTimeoutError):
        email_service.classify_and_raise_error(failure)


def test_classify_and_raise_error_transient_connection(email_service):
    failure = EmailFailure(
        success=False,
        error_code="ConnectionResetError",
        error_message="Connection reset by peer",
        provider="smtp",
        retryable=True,
        latency_ms=50.0,
        timestamp=0.0
    )
    with pytest.raises(EmailConnectionResetError):
        email_service.classify_and_raise_error(failure)


def test_classify_and_raise_error_permanent_auth(email_service):
    failure = EmailFailure(
        success=False,
        error_code="SMTPAuthenticationError",
        error_message="Invalid credentials",
        provider="smtp",
        retryable=False,
        latency_ms=50.0,
        timestamp=0.0
    )
    with pytest.raises(EmailAuthFailureError):
        email_service.classify_and_raise_error(failure)


def test_classify_and_raise_error_permanent_recipient(email_service):
    failure = EmailFailure(
        success=False,
        error_code="SMTPRecipientsRefused",
        error_message="Recipient refused: 550 User unknown",
        provider="smtp",
        retryable=False,
        latency_ms=50.0,
        timestamp=0.0
    )
    with pytest.raises(InvalidRecipientError):
        email_service.classify_and_raise_error(failure)


# ── Step 5: Database Persistence & End-to-End Orchestration Tests ────────────

@pytest.mark.asyncio
async def test_send_application_email_success(email_service, mock_application, mock_db_session):
    """Verify successful send writes EmailSend to DB and returns successfully."""
    # Mock download_asset
    with patch.object(email_service, "download_asset", new_callable=AsyncMock) as mock_download:
        mock_download.return_value = b"%PDF-1.4..."
        
        # Mock smtp provider send_email
        mock_provider = MagicMock()
        mock_provider.send_email = AsyncMock(return_value=EmailResponse(
            success=True,
            message_id="SMTP-123456",
            message="Sent successfully",
            provider="smtp",
            latency_ms=120.0,
            timestamp=0.0
        ))
        
        with patch.object(email_service, "select_provider", return_value=mock_provider):
            res = await email_service.send_application_email(
                application=mock_application,
                candidate_name="Alice Bob"
            )
            
            assert res.success is True
            assert res.message_id == "SMTP-123456"
            
            # Assert add was called on DB session for EmailSend log
            assert mock_db_session.add.call_count >= 1
            logged_obj = mock_db_session.add.call_args[0][0]
            assert isinstance(logged_obj, EmailSend)
            assert logged_obj.status == "sent"
            assert logged_obj.provider == "smtp"
            assert logged_obj.recipient == mock_application.contact_email


# ── Step 6: Status Transitions Validation Tests ────────────────────────────────

def test_invalid_transitions_email_states():
    """Verify illegal transitions involving email-specific states are blocked."""
    # EMAIL_SENT is terminal for application layer, can only transition to user manual states
    allowed_from_sent = VALID_TRANSITIONS[ApplicationStatus.EMAIL_SENT]
    assert ApplicationStatus.REJECTED in allowed_from_sent
    assert ApplicationStatus.INTERVIEW in allowed_from_sent
    assert ApplicationStatus.ACCEPTED in allowed_from_sent
    assert ApplicationStatus.QUEUED not in allowed_from_sent
    assert ApplicationStatus.PROCESSING not in allowed_from_sent

    # EMAIL_FAILED can only transition to EMAIL_SENDING (for retries) or FAILED (permanent failure)
    allowed_from_failed = VALID_TRANSITIONS[ApplicationStatus.EMAIL_FAILED]
    assert ApplicationStatus.EMAIL_SENDING in allowed_from_failed
    assert ApplicationStatus.FAILED in allowed_from_failed
    assert ApplicationStatus.EMAIL_SENT not in allowed_from_failed
