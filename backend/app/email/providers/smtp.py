import asyncio
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from app.email.providers.base import BaseEmailProvider
from app.email.schemas.email import EmailRequest, EmailResponse, EmailFailure
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

class SMTPEmailProvider(BaseEmailProvider):
    """SMTP Email Provider wrapping standard smtplib in a non-blocking asyncio thread execution context."""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def send_email(self, request: EmailRequest) -> EmailResponse | EmailFailure:
        start_time = time.monotonic()
        try:
            res = await asyncio.to_thread(self._send_sync, request)
            latency = (time.monotonic() - start_time) * 1000.0
            return EmailResponse(
                success=True,
                message_id=res.get("message_id"),
                message="Email sent successfully via SMTP",
                provider="smtp",
                latency_ms=latency,
                timestamp=time.time(),
            )
        except Exception as e:
            latency = (time.monotonic() - start_time) * 1000.0
            retryable = self._is_retryable_exception(e)
            logger.error(
                "email.smtp_send_failed",
                error=str(e),
                error_type=type(e).__name__,
                retryable=retryable,
                application_id=request.metadata.application_id,
            )
            return EmailFailure(
                success=False,
                error_code=type(e).__name__,
                error_message=str(e),
                provider="smtp",
                retryable=retryable,
                latency_ms=latency,
                timestamp=time.time(),
            )

    def _send_sync(self, request: EmailRequest) -> dict:
        # Construct email message
        msg = MIMEMultipart("alternative" if not request.attachments else "mixed")
        msg["Subject"] = request.subject
        msg["From"] = self.settings.smtp_email
        msg["To"] = request.to_email
        
        # Attach text and html parts
        body_text_part = MIMEText(request.body_text, "plain", "utf-8")
        if request.body_html:
            if request.attachments:
                # If mixed (attachments), we wrap plain and html inside an alternative part
                alt_part = MIMEMultipart("alternative")
                alt_part.attach(body_text_part)
                alt_part.attach(MIMEText(request.body_html, "html", "utf-8"))
                msg.attach(alt_part)
            else:
                msg.attach(body_text_part)
                msg.attach(MIMEText(request.body_html, "html", "utf-8"))
        else:
            msg.attach(body_text_part)
            
        # Attach files
        for att in request.attachments:
            maintype, subtype = att.mime_type.split("/", 1)
            part = MIMEBase(maintype, subtype)
            part.set_payload(att.content)
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={att.filename}"
            )
            msg.attach(part)
            
        # SMTP connection parameters
        host = self.settings.smtp_host
        port = self.settings.smtp_port
        username = self.settings.smtp_email
        password = self.settings.smtp_password
        use_tls = self.settings.smtp_tls

        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=10.0)
        else:
            server = smtplib.SMTP(host, port, timeout=10.0)
            if use_tls:
                server.starttls()
                
        try:
            if username and password:
                server.login(username, password)
            server.sendmail(username, [request.to_email], msg.as_string())
            # Generate local message_id as SMTP sendmail doesn't return SMTP conversation ID
            message_id = f"SMTP-{time.time()}-{username}"
            return {"message_id": message_id}
        finally:
            try:
                server.quit()
            except Exception:
                pass

    def _is_retryable_exception(self, e: Exception) -> bool:
        """
        Differentiate transient (retryable) vs permanent (non-retryable) errors.
        
        Retryable: timeout, temporary connection drop, 4xx transient SMTP response
        Permanent: invalid credentials, invalid recipient address (550), syntax errors
        """
        msg = str(e).lower()
        if isinstance(e, (smtplib.SMTPConnectError, smtplib.SMTPHeloError)):
            return True
            
        if isinstance(e, smtplib.SMTPAuthenticationError):
            return False
            
        if isinstance(e, smtplib.SMTPRecipientsRefused):
            return False
            
        if isinstance(e, smtplib.SMTPSenderRefused):
            return False
            
        if isinstance(e, smtplib.SMTPDataError):
            if hasattr(e, "smtp_code"):
                code = getattr(e, "smtp_code")
                # 4xx is transient, 5xx is permanent
                if 400 <= code < 500:
                    return True
                return False
            return False

        if isinstance(e, (asyncio.TimeoutError, ConnectionError, TimeoutError, OSError)):
            return True
            
        return False
