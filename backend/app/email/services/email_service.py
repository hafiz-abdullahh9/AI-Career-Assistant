import asyncio
import os
import time
from datetime import UTC, datetime
from typing import Tuple, List, Optional
import httpx
from jinja2 import Environment, FileSystemLoader
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
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
)
from app.email.providers.smtp import SMTPEmailProvider
from app.email.providers.gmail import GmailEmailProvider
from app.email.schemas.email import EmailRequest, EmailResponse, EmailFailure, EmailAttachment, EmailMetadata
from app.email.utils.mime import validate_attachment_content
from app.models.orm import Application, EmailSend

logger = structlog.get_logger(__name__)

class EmailService:
    """
    Email Service orchestrating template rendering, attachment validation,
    provider selection, SMTP/Gmail delivery, and retry classification.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self.settings = get_settings()
        
        # Load jinja2 templates from templates directory
        template_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
            "templates"
        )
        self.jinja_env = Environment(loader=FileSystemLoader(template_dir))

    def select_provider(self, sender_email: str):
        """
        Select Gmail API client for 'gmail.com' domain, fallback to SMTP.
        """
        domain = sender_email.split("@")[-1].lower()
        if domain == "gmail.com":
            return GmailEmailProvider()
        return SMTPEmailProvider()

    def render_templates(
        self, 
        candidate_name: str, 
        company_name: str, 
        role: str, 
        custom_message: Optional[str] = None,
        contact_name: str = "Hiring Manager"
    ) -> Tuple[str, str]:
        """
        Render plain text and HTML bodies.
        """
        context = {
            "candidate_name": candidate_name,
            "company_name": company_name,
            "role_title": role,  # Allow fallback for template role_title
            "role": role,
            "custom_message": custom_message,
            "contact_name": contact_name,
        }
        try:
            text_template = self.jinja_env.get_template("application_email.txt")
            html_template = self.jinja_env.get_template("application_email.html")
            
            body_text = text_template.render(**context)
            body_html = html_template.render(**context)
            
            return body_text, body_html
        except Exception as e:
            logger.error("email.template_rendering_failed", error=str(e))
            raise MalformedEmailError(f"Template rendering failed: {e}")

    async def download_asset(self, url: str) -> bytes:
        """
        Download CV or cover letter from storage URL.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url)
                res.raise_for_status()
                return res.content
        except httpx.TimeoutException as e:
            logger.error("email.asset_download_timeout", url=url, error=str(e))
            raise EmailTimeoutError(f"Timeout while downloading asset: {e}")
        except Exception as e:
            logger.error("email.asset_download_failed", url=url, error=str(e))
            raise EmailConnectionResetError(f"Failed to download asset: {e}")

    async def prepare_attachments(self, application: Application) -> List[EmailAttachment]:
        """
        Retrieve and validate resume and cover letter attachments from application metadata.
        """
        attachments = []
        metadata = application.metadata_ or {}
        
        # 1. Prepare Resume
        resume_meta = metadata.get("resume")
        if resume_meta and "storage_url" in resume_meta:
            url = resume_meta["storage_url"]
            filename = resume_meta.get("filename", "Resume.pdf")
            content = await self.download_asset(url)
            
            # MIME verification
            mime_type = "application/pdf"
            if filename.lower().endswith(".docx"):
                mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            
            is_valid, reason = validate_attachment_content(content, filename, mime_type)
            if not is_valid:
                logger.error("email.attachment_validation_failed", filename=filename, reason=reason)
                raise InvalidAttachmentError(f"Resume validation failed: {reason}")
                
            attachments.append(EmailAttachment(
                filename=filename,
                content=content,
                mime_type=mime_type
            ))
            
        # 2. Prepare Cover Letter
        cl_meta = metadata.get("cover_letter")
        if cl_meta and "storage_url" in cl_meta:
            url = cl_meta["storage_url"]
            filename = cl_meta.get("filename", "Cover_Letter.pdf")
            content = await self.download_asset(url)
            
            # MIME verification
            mime_type = "application/pdf"
            if filename.lower().endswith(".docx"):
                mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            
            is_valid, reason = validate_attachment_content(content, filename, mime_type)
            if not is_valid:
                logger.error("email.attachment_validation_failed", filename=filename, reason=reason)
                raise InvalidAttachmentError(f"Cover letter validation failed: {reason}")
                
            attachments.append(EmailAttachment(
                filename=filename,
                content=content,
                mime_type=mime_type
            ))
            
        return attachments

    def classify_and_raise_error(self, failure: EmailFailure) -> None:
        """
        Classify transient (retryable) vs permanent exceptions and raise them.
        """
        err_msg = failure.error_message
        err_code = failure.error_code.lower()
        
        if failure.retryable:
            if "timeout" in err_code or "timeout" in err_msg.lower():
                raise EmailTimeoutError(f"SMTP Timeout: {err_msg}")
            if "connection" in err_code or "reset" in err_msg.lower() or "connection" in err_msg.lower():
                raise EmailConnectionResetError(f"SMTP Connection Failure: {err_msg}")
            raise TemporarySMTPFailureError(f"Transient SMTP Error: {err_msg}")
        else:
            if "authentication" in err_code or "credentials" in err_msg.lower() or "auth" in err_msg.lower():
                raise EmailAuthFailureError(f"SMTP Authentication Error: {err_msg}")
            if "recipient" in err_code or "550" in err_msg or "refused" in err_msg.lower():
                raise InvalidRecipientError(f"SMTP Recipient Refused: {err_msg}")
            if "data" in err_code or "malformed" in err_msg.lower():
                raise MalformedEmailError(f"SMTP Malformed Email payload: {err_msg}")
            raise PermanentEmailError(f"Permanent SMTP Error: {err_msg}")

    async def log_email_send(
        self,
        application_id: str,
        provider: str,
        recipient: str,
        subject: str,
        status: str,
        retry_count: int = 0,
        smtp_response: Optional[str] = None,
        error_message: Optional[str] = None,
        latency_ms: Optional[float] = None
    ) -> EmailSend:
        """
        Record the email attempt to the database.
        """
        import uuid
        email_send = EmailSend(
            application_id=uuid.UUID(application_id),
            provider=provider,
            recipient=recipient,
            subject=subject,
            status=status,
            retry_count=retry_count,
            smtp_response=smtp_response,
            error_message=error_message,
            latency_ms=latency_ms,
            sent_at=datetime.now(UTC) if status == "sent" else None
        )
        self._db.add(email_send)
        await self._db.flush()
        return email_send

    async def send_application_email(
        self,
        application: Application,
        candidate_name: str,
        custom_message: Optional[str] = None,
        contact_name: str = "Hiring Manager"
    ) -> EmailResponse:
        """
        Orchestrate the entire email send: render, validate attachments, select provider, and send.
        """
        app_id_str = str(application.application_id)
        recipient = application.contact_email or self.settings.smtp_email
        subject = f"Application for {application.role_title} — {candidate_name}"
        
        # 1. Render template
        body_text, body_html = self.render_templates(
            candidate_name=candidate_name,
            company_name=application.company_name,
            role=application.role_title,
            custom_message=custom_message,
            contact_name=contact_name
        )
        
        # 2. Download and validate attachments
        attachments = await self.prepare_attachments(application)
        
        # 3. Select provider
        sender_email = self.settings.smtp_email
        provider = self.select_provider(sender_email)
        
        # 4. Construct request
        email_req = EmailRequest(
            to_email=recipient,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            attachments=attachments,
            metadata=EmailMetadata(
                application_id=app_id_str,
                provider=provider.__class__.__name__
            )
        )
        
        # 5. Send Email
        start_time = time.monotonic()
        
        res = await provider.send_email(email_req)
        latency = (time.monotonic() - start_time) * 1000.0
        
        if isinstance(res, EmailFailure) or not res.success:
            failure_obj = res if isinstance(res, EmailFailure) else EmailFailure(
                success=False,
                error_code="SEND_FAILED",
                error_message=getattr(res, "message", "Email sending failed"),
                provider=getattr(res, "provider", "smtp"),
                retryable=True,
                latency_ms=latency,
                timestamp=time.time()
            )
            
            # DB logging of failure
            await self.log_email_send(
                application_id=app_id_str,
                provider=failure_obj.provider,
                recipient=recipient,
                subject=subject,
                status="failed",
                retry_count=application.retry_count,
                error_message=failure_obj.error_message,
                latency_ms=latency
            )
            
            # Raise classified error
            self.classify_and_raise_error(failure_obj)
            
        # Success path
        await self.log_email_send(
            application_id=app_id_str,
            provider=res.provider,
            recipient=recipient,
            subject=subject,
            status="sent",
            retry_count=application.retry_count,
            smtp_response=res.message,
            latency_ms=latency
        )
        
        return res
