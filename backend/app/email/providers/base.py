from app.email.schemas.email import EmailRequest, EmailResponse, EmailFailure

class BaseEmailProvider:
    """Base class defining the interface for all email delivery providers."""

    async def send_email(self, request: EmailRequest) -> EmailResponse | EmailFailure:
        """Send an email using the provider. Must be overridden by subclasses."""
        raise NotImplementedError
