from app.email.providers.base import BaseEmailProvider
from app.email.schemas.email import EmailRequest, EmailResponse, EmailFailure

class GmailEmailProvider(BaseEmailProvider):
    """Placeholder for Gmail API based email provider. Non-implemented for Phase B."""

    async def send_email(self, request: EmailRequest) -> EmailResponse | EmailFailure:
        raise NotImplementedError("Gmail API email provider is not implemented yet.")
