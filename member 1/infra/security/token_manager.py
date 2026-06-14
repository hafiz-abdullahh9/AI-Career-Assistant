from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Column, String, DateTime
from core.database import Base
from infra.security.encryption import TokenEncryptor
from core.exceptions import SecurityException

class OAuthCredential(Base):
    """SQLAlchemy persistent model for OAuth tokens with encryption constraints"""
    __tablename__ = "oauth_credentials"

    user_id = Column(String, primary_key=True, index=True)
    provider = Column(String, primary_key=True)  # e.g., "gmail", "linkedin"
    encrypted_access_token = Column(String, nullable=False)
    encrypted_refresh_token = Column(String, nullable=True)
    token_expiry = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class TokenManager:
    def __init__(self, encryptor: TokenEncryptor = None):
        """Initializes the manager with a cryptographic encryptor utility."""
        self.encryptor = encryptor or TokenEncryptor()

    async def save_tokens(
        self,
        db: AsyncSession,
        user_id: str,
        provider: str,
        access_token: str,
        refresh_token: str = None,
        expiry: datetime = None
    ) -> None:
        """Encrypts credentials using AES-256-GCM and persists them to the PostgreSQL database."""
        try:
            enc_access = self.encryptor.encrypt(access_token)
            enc_refresh = self.encryptor.encrypt(refresh_token) if refresh_token else None

            # Retrieve existing credential or create a new database row
            cred = await db.get(OAuthCredential, (user_id, provider))
            if cred:
                cred.encrypted_access_token = enc_access
                cred.encrypted_refresh_token = enc_refresh
                cred.token_expiry = expiry
            else:
                cred = OAuthCredential(
                    user_id=user_id,
                    provider=provider,
                    encrypted_access_token=enc_access,
                    encrypted_refresh_token=enc_refresh,
                    token_expiry=expiry
                )
                db.add(cred)
            await db.commit()
        except Exception as e:
            await db.rollback()
            raise SecurityException(f"Failed to save encrypted OAuth credentials: {str(e)}")

    async def get_tokens(self, db: AsyncSession, user_id: str, provider: str) -> dict:
        """Loads and decrypts OAuth credentials from database, returning plain text credentials."""
        try:
            cred = await db.get(OAuthCredential, (user_id, provider))
            if not cred:
                return {}

            access_token = self.encryptor.decrypt(cred.encrypted_access_token)
            refresh_token = (
                self.encryptor.decrypt(cred.encrypted_refresh_token)
                if cred.encrypted_refresh_token
                else None
            )

            return {
                "user_id": cred.user_id,
                "provider": cred.provider,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expiry": cred.token_expiry
            }
        except Exception as e:
            raise SecurityException(f"Failed to decrypt and retrieve credentials: {str(e)}")
