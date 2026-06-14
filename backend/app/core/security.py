# app/core/security.py
"""Core security and cryptographic utilities.

Includes:
- Password hashing and verification via bcrypt.
- RFC 6238 TOTP generation and verification for MFA.
- Symmetric encryption/decryption for sensitive at-rest data (e.g., MFA secrets).
"""

import base64
import hashlib
import hmac
import os
import struct
import time
from typing import Any

import bcrypt
from cryptography.fernet import Fernet

from app.core.config import get_settings


# ── Password Hashing (bcrypt) ──────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a password using bcrypt with an adaptive work factor."""
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False


# ── MFA Secret Encryption (Fernet) ──────────────────────────────────────────────

def _get_encryption_key() -> bytes:
    """Derive a 32-byte base64-encoded Fernet key from the JWT secret key."""
    settings = get_settings()
    # Use SHA-256 to ensure a deterministic 32-byte key regardless of input key length
    key_bytes = hashlib.sha256(settings.jwt_secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(key_bytes)


def encrypt_mfa_secret(secret_plaintext: str) -> str:
    """Encrypt the base32 MFA secret at rest using Fernet."""
    f = Fernet(_get_encryption_key())
    encrypted_bytes = f.encrypt(secret_plaintext.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_mfa_secret(secret_ciphertext: str) -> str:
    """Decrypt the base32 MFA secret using Fernet."""
    f = Fernet(_get_encryption_key())
    decrypted_bytes = f.decrypt(secret_ciphertext.encode("utf-8"))
    return decrypted_bytes.decode("utf-8")


# ── Multi-Factor Authentication (RFC 6238 TOTP) ─────────────────────────────────

def generate_totp_secret() -> str:
    """Generate a standard base32-encoded random TOTP secret (160 bits)."""
    # 20 bytes = 160 bits of entropy
    random_bytes = os.urandom(20)
    return base64.b32encode(random_bytes).decode("utf-8").replace("=", "")


def get_hotp_token(secret_base32: str, interval_index: int) -> int:
    """Generate a 6-digit HOTP token for a given interval index (RFC 4226)."""
    # Clean padding and decode base32
    secret_base32 = secret_base32.upper()
    # Add padding if needed
    missing_padding = len(secret_base32) % 8
    if missing_padding:
        secret_base32 += "=" * (8 - missing_padding)
    
    key = base64.b32decode(secret_base32, casefold=True)
    msg = struct.pack(">Q", interval_index)
    
    # Compute HMAC-SHA1
    hmac_hash = hmac.new(key, msg, hashlib.sha1).digest()
    
    # Dynamic truncation
    offset = hmac_hash[19] & 15
    binary_val = (
        ((hmac_hash[offset] & 127) << 24)
        | (hmac_hash[offset + 1] << 16)
        | (hmac_hash[offset + 2] << 8)
        | hmac_hash[offset + 3]
    )
    
    return binary_val % 1000000


def verify_totp_token(secret_base32: str, token: str, window: int = 1) -> bool:
    """Verify a 6-digit TOTP token with a default clock drift window of 30 seconds.

    If window=1, checks current time interval and +/- 1 interval (total 90s range).
    """
    try:
        token_val = int(token.strip())
    except ValueError:
        return False

    current_time = int(time.time())
    # 30-second time steps as per standard RFC 6238
    time_step = 30
    current_interval = current_time // time_step

    # Check intervals in window to handle network delay / clock drift
    for i in range(-window, window + 1):
        if get_hotp_token(secret_base32, current_interval + i) == token_val:
            return True
            
    return False


def get_totp_provisioning_uri(secret_base32: str, username: str, issuer: str = "AI-Career-Assistant") -> str:
    """Generate a standard otpauth:// URL for setting up authenticator apps."""
    import urllib.parse
    label = f"{issuer}:{username}"
    params = {
        "secret": secret_base32,
        "issuer": issuer,
        "algorithm": "SHA1",
        "digits": 6,
        "period": 30
    }
    return f"otpauth://totp/{urllib.parse.quote(label)}?{urllib.parse.urlencode(params)}"
