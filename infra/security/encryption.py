import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from core.config import settings
from core.exceptions import SecurityException

class TokenEncryptor:
    def __init__(self, key_b64: str = None):
        """Initializes the encryptor with a 32-byte key for AES-256-GCM encryption."""
        if not key_b64:
            key_b64 = settings.ENCRYPTION_KEY
        try:
            self.key = base64.b64decode(key_b64)
            if len(self.key) != 32:
                raise ValueError("Decoded encryption key must be exactly 32 bytes (256 bits).")
            self.aesgcm = AESGCM(self.key)
        except Exception as e:
            raise SecurityException(f"Failed to initialize encryption layer: {str(e)}")

    def encrypt(self, plaintext: str) -> str:
        """Encrypts plaintext string using AES-256-GCM and returns a Base64-encoded string."""
        if not plaintext:
            return ""
        try:
            nonce = os.urandom(12) # Standard 96-bit nonce for GCM
            ciphertext = self.aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
            # Combine nonce and ciphertext then base64 encode
            return base64.b64encode(nonce + ciphertext).decode('utf-8')
        except Exception as e:
            raise SecurityException(f"Token encryption failed: {str(e)}")

    def decrypt(self, ciphertext_b64: str) -> str:
        """Decrypts a Base64-encoded ciphertext string back to plaintext."""
        if not ciphertext_b64:
            return ""
        try:
            raw_data = base64.b64decode(ciphertext_b64)
            if len(raw_data) < 12:
                raise ValueError("Ciphertext data too short to contain nonce header.")
            nonce = raw_data[:12]
            ciphertext = raw_data[12:]
            plaintext = self.aesgcm.decrypt(nonce, ciphertext, None)
            return plaintext.decode('utf-8')
        except Exception as e:
            raise SecurityException(f"Token decryption failed: {str(e)}")
