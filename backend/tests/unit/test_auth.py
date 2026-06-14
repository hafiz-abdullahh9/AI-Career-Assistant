# tests/unit/test_auth.py
"""
Unit tests for the authentication foundation.

Covers:
- Password hashing and verification (bcrypt)
- TOTP generation and verification (RFC 6238)
- AuthService: user registration, authentication, and brute-force lockout
- SessionManager: session creation, Redis cache hit/miss, sliding window,
  absolute expiry, revocation, and bulk revocation
- MfaService: setup, enable, backup code verification, replay protection
- RBAC dependencies: RequiresPermission and RequiresRole guard logic

Notes on test design:
- SQLAlchemy ORM models are NOT constructed via `__new__` because that bypasses
  the instrumentation that sets up `_sa_instance_state`. Instead, services that
  return mutable ORM objects use MagicMock() objects whose attributes are freely
  writable, just as they would be on a fully-initialized ORM instance.
- `redis.asyncio` is injected into sys.modules before any import of `app.core.auth`
  so that the dependency resolves without a real Redis installation.
"""

import hashlib
import json
import sys
import uuid
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Patch redis.asyncio before any app.core.auth import ───────────────────────
# app.core.redis imports `redis.asyncio as aioredis` at module level.
# We inject a MagicMock so the module can be imported in unit-test environments
# that do not have a full Redis installation.
_mock_aioredis = MagicMock()
sys.modules.setdefault("redis", MagicMock())
sys.modules.setdefault("redis.asyncio", _mock_aioredis)
# ──────────────────────────────────────────────────────────────────────────────

from app.core.security import (
    decrypt_mfa_secret,
    encrypt_mfa_secret,
    generate_totp_secret,
    get_hotp_token,
    hash_password,
    verify_password,
    verify_totp_token,
)
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.services.auth_service import AuthService
from app.services.mfa_service import MfaService
from app.services.session_manager import SessionManager


# ── Lightweight ORM-compatible mock helpers ────────────────────────────────────

def _make_user(**kwargs) -> MagicMock:
    """
    Return a MagicMock that mimics a User ORM instance.

    MagicMock is used instead of User.__new__() because SQLAlchemy instrumented
    descriptors require _sa_instance_state to be present on the real object,
    but the service layer also does attribute mutations (user.failed_login_attempts += 1).
    MagicMock supports attribute read/write without those constraints.
    """
    user = MagicMock()
    user.id = kwargs.get("id", uuid.uuid4())
    user.username = kwargs.get("username", "testuser")
    user.email = kwargs.get("email", "test@example.com")
    user.password_hash = kwargs.get("password_hash", hash_password("correct_password"))
    user.is_active = kwargs.get("is_active", True)
    user.is_superuser = kwargs.get("is_superuser", False)
    user.mfa_enabled = kwargs.get("mfa_enabled", False)
    user.failed_login_attempts = kwargs.get("failed_login_attempts", 0)
    user.locked_until = kwargs.get("locked_until", None)
    user.last_login_at = kwargs.get("last_login_at", None)
    user.created_at = kwargs.get("created_at", datetime.now(UTC))
    user.updated_at = kwargs.get("updated_at", datetime.now(UTC))
    user.roles = kwargs.get("roles", [])
    return user


def _make_role(name: str = "operator") -> MagicMock:
    role = MagicMock()
    role.id = uuid.uuid4()
    role.name = name
    role.description = ""
    role.permissions = []
    role.users = []
    return role


def _make_permission(action: str, resource: str = "global") -> MagicMock:
    perm = MagicMock()
    perm.id = uuid.uuid4()
    perm.action = action
    perm.resource = resource
    perm.roles = []
    return perm


def _make_mfa_secret(**kwargs) -> MagicMock:
    mfa = MagicMock()
    mfa.user_id = kwargs.get("user_id", uuid.uuid4())
    mfa.secret_encrypted = kwargs.get("secret_encrypted", "encrypted_secret")
    mfa.backup_codes = kwargs.get("backup_codes", {"codes": []})
    mfa.enabled = kwargs.get("enabled", True)
    mfa.verified_at = kwargs.get("verified_at", None)
    return mfa


def _make_mock_db(return_value=None) -> AsyncMock:
    """Build an AsyncMock SQLAlchemy session with a configurable scalar result."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=return_value)
    result.scalar_one = MagicMock(return_value=return_value)
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    result.rowcount = 1
    db.execute = AsyncMock(return_value=result)
    return db


def _make_mock_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.exists = AsyncMock(return_value=0)
    return redis


# ══════════════════════════════════════════════════════════════════════════════
# 1. Password Hashing
# ══════════════════════════════════════════════════════════════════════════════

class TestPasswordHashing:
    """Validates bcrypt password hashing and constant-time verification."""

    def test_hash_produces_non_trivial_output(self):
        """Hashed value must differ from the plaintext input."""
        pw = "super_secure_password_123"
        hashed = hash_password(pw)
        assert hashed != pw
        assert len(hashed) > 30

    def test_verify_correct_password(self):
        """Correct password must pass verification."""
        pw = "correct_horse_battery_staple"
        assert verify_password(pw, hash_password(pw)) is True

    def test_verify_wrong_password(self):
        """Wrong password must fail verification."""
        hashed = hash_password("original_password")
        assert verify_password("wrong_password", hashed) is False

    def test_two_hashes_of_same_password_differ(self):
        """bcrypt salt ensures every hash is unique."""
        pw = "same_password"
        assert hash_password(pw) != hash_password(pw)

    def test_verify_empty_string_password(self):
        """Empty string hashes and verifies correctly."""
        pw = ""
        hashed = hash_password(pw)
        assert verify_password(pw, hashed) is True
        assert verify_password("not_empty", hashed) is False

    def test_verify_corrupted_hash_returns_false(self):
        """A malformed hash string must not raise; must return False."""
        result = verify_password("any_password", "not_a_valid_bcrypt_hash")
        assert result is False


# ══════════════════════════════════════════════════════════════════════════════
# 2. TOTP Security
# ══════════════════════════════════════════════════════════════════════════════

class TestTotpSecurity:
    """Validates RFC 6238 TOTP generation, verification, and edge cases."""

    def test_generate_totp_secret_is_base32(self):
        """Secret must be a non-empty base32 string."""
        secret = generate_totp_secret()
        assert isinstance(secret, str)
        assert len(secret) > 0
        valid_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")
        assert all(c in valid_chars for c in secret.upper())

    def test_generate_totp_secret_is_unique(self):
        """Each generated secret must be unique."""
        secrets_set = {generate_totp_secret() for _ in range(10)}
        assert len(secrets_set) == 10

    def test_verify_totp_current_interval(self):
        """Token generated for the current interval must verify successfully."""
        import time
        secret = generate_totp_secret()
        current_interval = int(time.time()) // 30
        token = str(get_hotp_token(secret, current_interval)).zfill(6)
        assert verify_totp_token(secret, token) is True

    def test_verify_totp_wrong_token_fails(self):
        """A randomly wrong token must fail (valid failure, not a logic error)."""
        secret = generate_totp_secret()
        # Use a far-future interval that is highly unlikely to match current time
        import time
        future_interval = int(time.time()) // 30 + 10000
        wrong_token = str(get_hotp_token(secret, future_interval)).zfill(6)
        # Verify with default window=1 (only checks ±1 from now)
        assert verify_totp_token(secret, wrong_token, window=1) is False

    def test_verify_totp_non_numeric_token_fails(self):
        """Non-numeric tokens must return False without raising."""
        secret = generate_totp_secret()
        assert verify_totp_token(secret, "abcdef") is False

    def test_verify_totp_empty_string_fails(self):
        """An empty token string must return False."""
        secret = generate_totp_secret()
        assert verify_totp_token(secret, "") is False

    def test_verify_totp_previous_interval_within_window(self):
        """Token from adjacent interval must still verify (drift tolerance)."""
        import time
        secret = generate_totp_secret()
        prev_interval = int(time.time()) // 30 - 1
        token = str(get_hotp_token(secret, prev_interval)).zfill(6)
        assert verify_totp_token(secret, token, window=1) is True


# ══════════════════════════════════════════════════════════════════════════════
# 3. MFA Secret Encryption
# ══════════════════════════════════════════════════════════════════════════════

class TestMfaSecretEncryption:
    """Validates Fernet symmetric encryption for MFA secret at rest."""

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypt then decrypt must return the original plaintext."""
        secret = generate_totp_secret()
        ciphertext = encrypt_mfa_secret(secret)
        assert decrypt_mfa_secret(ciphertext) == secret

    def test_ciphertext_differs_from_plaintext(self):
        """Encrypted output must not be the same as the plaintext."""
        secret = generate_totp_secret()
        assert encrypt_mfa_secret(secret) != secret

    def test_two_encryptions_of_same_secret_differ(self):
        """Fernet uses a random IV, so each encryption produces a unique ciphertext."""
        secret = generate_totp_secret()
        assert encrypt_mfa_secret(secret) != encrypt_mfa_secret(secret)


# ══════════════════════════════════════════════════════════════════════════════
# 4. AuthService — Registration
# ══════════════════════════════════════════════════════════════════════════════

class TestAuthServiceRegistration:
    """Unit tests for user registration logic in AuthService."""

    @pytest.mark.asyncio
    async def test_register_new_user_success(self):
        """A new user should be created, flushed, and returned."""
        operator_role = _make_role("operator")

        # Sequence of execute() calls:
        # 1. existing_user check → None
        # 2. role lookup → operator_role
        # 3. audit event flush → irrelevant
        results = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=operator_role)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.execute = AsyncMock(side_effect=results)

        service = AuthService()
        user = await service.register_user(db, "alice", "alice@example.com", "secure_pass")

        assert user.username == "alice"
        assert user.email == "alice@example.com"
        assert user.is_active is True
        assert user.mfa_enabled is False
        db.add.assert_called()

    @pytest.mark.asyncio
    async def test_register_duplicate_username_raises_conflict(self):
        """Registering with a taken username must raise ConflictError."""
        existing = _make_user(username="alice", email="other@example.com")
        db = _make_mock_db(return_value=existing)

        service = AuthService()
        with pytest.raises(ConflictError, match="Username is already taken"):
            await service.register_user(db, "alice", "new@example.com", "pass")

    @pytest.mark.asyncio
    async def test_register_duplicate_email_raises_conflict(self):
        """Registering with a taken email (different username) must raise ConflictError."""
        existing = _make_user(username="bob", email="alice@example.com")
        db = _make_mock_db(return_value=existing)

        service = AuthService()
        with pytest.raises(ConflictError, match="Email is already registered"):
            await service.register_user(db, "alice", "alice@example.com", "pass")


# ══════════════════════════════════════════════════════════════════════════════
# 5. AuthService — Authentication & Lockout
# ══════════════════════════════════════════════════════════════════════════════

class TestAuthServiceAuthentication:
    """Unit tests for login flow, brute-force lockout, and audit logging."""

    @pytest.mark.asyncio
    async def test_successful_login(self):
        """Valid credentials must return the user and reset failed_login_attempts."""
        user = _make_user(
            username="alice",
            email="alice@example.com",
            password_hash=hash_password("correct_password"),
            failed_login_attempts=2,
        )
        # All execute() calls (user lookup + audit event) return the same mock result
        db = AsyncMock()
        db.flush = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=user),
        ))

        service = AuthService()
        result = await service.authenticate_user(db, "alice", "correct_password")

        assert result is user
        assert user.failed_login_attempts == 0
        assert user.locked_until is None

    @pytest.mark.asyncio
    async def test_wrong_password_increments_failed_attempts(self):
        """Invalid password must increment failed_login_attempts and raise UnauthorizedError."""
        user = _make_user(
            password_hash=hash_password("correct_password"),
            failed_login_attempts=0,
        )
        db = AsyncMock()
        db.flush = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=user),
        ))

        service = AuthService(lockout_attempts=5)
        with pytest.raises(UnauthorizedError):
            await service.authenticate_user(db, "alice", "wrong_password")

        assert user.failed_login_attempts == 1

    @pytest.mark.asyncio
    async def test_account_locked_after_max_failures(self):
        """Reaching lockout_attempts must set locked_until and raise UnauthorizedError."""
        user = _make_user(
            password_hash=hash_password("correct_password"),
            failed_login_attempts=4,  # one more attempt will trigger lockout
        )
        db = AsyncMock()
        db.flush = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=user),
        ))

        service = AuthService(lockout_attempts=5)
        with pytest.raises(UnauthorizedError):
            await service.authenticate_user(db, "alice", "wrong_password")

        assert user.locked_until is not None
        assert user.locked_until > datetime.now(UTC)

    @pytest.mark.asyncio
    async def test_login_blocked_when_account_locked(self):
        """Login with correct credentials must still fail if account is locked."""
        locked_until = datetime.now(UTC) + timedelta(minutes=10)
        user = _make_user(
            password_hash=hash_password("correct_password"),
            locked_until=locked_until,
        )
        db = AsyncMock()
        db.flush = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=user),
        ))

        service = AuthService()
        with pytest.raises(UnauthorizedError, match="temporarily locked"):
            await service.authenticate_user(db, "alice", "correct_password")

    @pytest.mark.asyncio
    async def test_login_nonexistent_user_raises_unauthorized(self):
        """Lookup of unknown user must raise UnauthorizedError (no info leakage)."""
        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None),
        ))

        service = AuthService()
        with pytest.raises(UnauthorizedError, match="Invalid username or password"):
            await service.authenticate_user(db, "ghost_user", "any_password")


# ══════════════════════════════════════════════════════════════════════════════
# 6. SessionManager — Creation & Hashing
# ══════════════════════════════════════════════════════════════════════════════

class TestSessionManagerCreation:
    """Tests session token generation, hashing, and DB persistence."""

    def test_hash_token_is_deterministic(self):
        """The same raw token must always produce the same hash."""
        sm = SessionManager()
        token = "test_raw_token_abc123"
        assert sm.hash_token(token) == sm.hash_token(token)

    def test_hash_token_uses_sha256(self):
        """The hash must match a direct SHA-256 computation."""
        sm = SessionManager()
        token = "sample_token"
        expected = hashlib.sha256(token.encode("utf-8")).hexdigest()
        assert sm.hash_token(token) == expected

    def test_generate_token_is_unique(self):
        """Each generated token must be unique (high entropy)."""
        sm = SessionManager()
        tokens = {sm.generate_token() for _ in range(20)}
        assert len(tokens) == 20

    def test_generate_token_length(self):
        """Token must be a 64-character hex string (32 bytes)."""
        sm = SessionManager()
        token = sm.generate_token()
        assert len(token) == 64
        int(token, 16)  # Must be valid hex; raises ValueError if not

    @pytest.mark.asyncio
    async def test_create_session_adds_to_db_and_caches(self):
        """create_session must persist to DB and write to Redis cache."""
        user_id = uuid.uuid4()
        mock_redis = _make_mock_redis()

        db = AsyncMock()
        db.flush = AsyncMock()

        # Capture the UserSession added to the db so we can give it a fake id
        captured_session = None

        def capture_add(obj):
            nonlocal captured_session
            if hasattr(obj, "session_token"):
                obj.id = uuid.uuid4()
                captured_session = obj

        db.add = MagicMock(side_effect=capture_add)

        sm = SessionManager(redis_client=mock_redis)
        session, raw_token = await sm.create_session(db, user_id, ip_address="127.0.0.1")

        assert raw_token
        assert len(raw_token) == 64
        db.add.assert_called_once()
        db.flush.assert_called()
        mock_redis.set.assert_called_once()

        # Redis key must contain the hashed token
        call_key = mock_redis.set.call_args[0][0]
        assert call_key.startswith("session:")
        assert sm.hash_token(raw_token) in call_key

    @pytest.mark.asyncio
    async def test_create_session_works_without_redis(self):
        """create_session must succeed gracefully when Redis is not available."""
        user_id = uuid.uuid4()
        db = AsyncMock()
        db.flush = AsyncMock()

        def add_with_id(obj):
            if hasattr(obj, "session_token"):
                obj.id = uuid.uuid4()

        db.add = MagicMock(side_effect=add_with_id)

        sm = SessionManager(redis_client=None)
        session, raw_token = await sm.create_session(db, user_id)

        assert raw_token
        db.add.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# 7. SessionManager — Validation (Redis Cache Hit / Miss)
# ══════════════════════════════════════════════════════════════════════════════

class TestSessionManagerValidation:
    """Tests session validation with Redis cache hit and DB fallback."""

    @pytest.mark.asyncio
    async def test_validate_returns_none_on_cache_miss_and_no_db_session(self):
        """When Redis misses and DB has no session, validate_session returns None."""
        redis = _make_mock_redis()
        redis.get = AsyncMock(return_value=None)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None),
        ))

        sm = SessionManager(redis_client=redis)
        result = await sm.validate_session(db, "non_existent_token")
        assert result is None

    @pytest.mark.asyncio
    async def test_validate_uses_redis_cache_when_available(self):
        """When Redis has a valid cached session, the user is fetched from DB."""
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        now = datetime.now(UTC)

        cache_data = json.dumps({
            "session_id": str(session_id),
            "user_id": str(user_id),
            "expires_at": (now + timedelta(hours=1)).isoformat(),
            "last_activity_at": now.isoformat(),
            "created_at": now.isoformat(),
        }).encode("utf-8")

        redis = _make_mock_redis()
        redis.get = AsyncMock(return_value=cache_data)

        mock_user = _make_user(id=user_id)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_user),
            rowcount=1,
        ))

        sm = SessionManager(redis_client=redis)
        result = await sm.validate_session(db, "any_raw_token")
        assert result is mock_user

    @pytest.mark.asyncio
    async def test_validate_returns_none_for_revoked_session(self):
        """A session with revoked_at set must return None."""
        redis = _make_mock_redis()
        redis.get = AsyncMock(return_value=None)

        now = datetime.now(UTC)
        session = MagicMock()
        session.id = uuid.uuid4()
        session.user_id = uuid.uuid4()
        session.session_token = "hashed"
        session.revoked_at = now          # Already revoked
        session.expires_at = now + timedelta(hours=1)
        session.created_at = now - timedelta(hours=1)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=session),
        ))

        sm = SessionManager(redis_client=redis)
        result = await sm.validate_session(db, "test_token")
        assert result is None

    @pytest.mark.asyncio
    async def test_validate_evicts_expired_cached_session(self):
        """An expired session in Redis cache must be revoked and return None."""
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        now = datetime.now(UTC)

        # Session expired 5 minutes ago
        cache_data = json.dumps({
            "session_id": str(session_id),
            "user_id": str(user_id),
            "expires_at": (now - timedelta(minutes=5)).isoformat(),
            "last_activity_at": (now - timedelta(minutes=6)).isoformat(),
            "created_at": now.isoformat(),
        }).encode("utf-8")

        redis = _make_mock_redis()
        redis.get = AsyncMock(return_value=cache_data)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
        db.flush = AsyncMock()

        sm = SessionManager(redis_client=redis)
        result = await sm.validate_session(db, "expired_token")
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# 8. SessionManager — Revocation
# ══════════════════════════════════════════════════════════════════════════════

class TestSessionManagerRevocation:
    """Tests for single-session and bulk-session revocation."""

    @pytest.mark.asyncio
    async def test_revoke_session_returns_true_on_success(self):
        """revoke_session must return True when a session row is updated."""
        redis = _make_mock_redis()
        db = AsyncMock()
        db.flush = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(rowcount=1))

        sm = SessionManager(redis_client=redis)
        result = await sm.revoke_session(db, "raw_token_abc")

        assert result is True
        redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_revoke_session_returns_false_when_not_found(self):
        """revoke_session must return False when no rows are updated."""
        redis = _make_mock_redis()
        db = AsyncMock()
        db.flush = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(rowcount=0))

        sm = SessionManager(redis_client=redis)
        result = await sm.revoke_session(db, "non_existent_token")

        assert result is False

    @pytest.mark.asyncio
    async def test_revoke_session_deletes_redis_cache(self):
        """revoke_session must always attempt to delete from Redis cache."""
        redis = _make_mock_redis()
        db = AsyncMock()
        db.flush = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(rowcount=1))

        sm = SessionManager(redis_client=redis)
        raw_token = "token_to_revoke"
        await sm.revoke_session(db, raw_token)

        expected_key = f"session:{sm.hash_token(raw_token)}"
        redis.delete.assert_called_once_with(expected_key)

    @pytest.mark.asyncio
    async def test_revoke_all_user_sessions_returns_count(self):
        """revoke_all_user_sessions must return the number of revoked sessions."""
        user_id = uuid.uuid4()
        token_hashes = ["hash_a", "hash_b", "hash_c"]

        redis = _make_mock_redis()
        db = AsyncMock()
        db.flush = AsyncMock()

        fetch_result = MagicMock()
        fetch_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=token_hashes))
        )
        update_result = MagicMock()
        db.execute = AsyncMock(side_effect=[fetch_result, update_result])

        sm = SessionManager(redis_client=redis)
        count = await sm.revoke_all_user_sessions(db, user_id)

        assert count == 3
        redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_revoke_all_returns_zero_when_no_sessions(self):
        """revoke_all_user_sessions must return 0 if there are no active sessions."""
        user_id = uuid.uuid4()
        redis = _make_mock_redis()
        db = AsyncMock()

        fetch_result = MagicMock()
        fetch_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )
        db.execute = AsyncMock(return_value=fetch_result)

        sm = SessionManager(redis_client=redis)
        count = await sm.revoke_all_user_sessions(db, user_id)

        assert count == 0


# ══════════════════════════════════════════════════════════════════════════════
# 9. MfaService — Setup and Enable
# ══════════════════════════════════════════════════════════════════════════════

class TestMfaServiceSetup:
    """Tests for TOTP secret generation, MFA enrollment, and enable flow."""

    def test_generate_mfa_setup_returns_triple(self):
        """generate_mfa_setup must return (secret, backup_codes, provisioning_uri)."""
        svc = MfaService()
        secret, codes, uri = svc.generate_mfa_setup("alice")

        assert isinstance(secret, str) and len(secret) > 0
        assert len(codes) == 8
        assert uri.startswith("otpauth://totp/")

    def test_backup_code_hashing_is_consistent(self):
        """hash_backup_code must be deterministic and case-/whitespace-normalized."""
        svc = MfaService()
        code = "AbCd1234"
        h1 = svc.hash_backup_code(code)
        h2 = svc.hash_backup_code("  " + code.lower() + "  ")
        assert h1 == h2

    def test_backup_codes_are_unique(self):
        """Generated backup codes must all be distinct."""
        svc = MfaService()
        _, codes, _ = svc.generate_mfa_setup("alice")
        assert len(set(codes)) == len(codes)

    @pytest.mark.asyncio
    async def test_enable_mfa_returns_false_on_wrong_code(self):
        """enable_mfa must return False when the TOTP verification fails."""
        import time
        svc = MfaService()
        secret, codes, _ = svc.generate_mfa_setup("alice")
        user_id = uuid.uuid4()

        # Use a future interval token that cannot match the current time check
        future_interval = int(time.time()) // 30 + 10000
        wrong_code = str(get_hotp_token(secret, future_interval)).zfill(6)

        db = _make_mock_db()
        result = await svc.enable_mfa(db, user_id, secret, wrong_code, codes)
        assert result is False

    @pytest.mark.asyncio
    async def test_enable_mfa_returns_true_with_valid_code(self):
        """enable_mfa must return True when the correct TOTP code is provided."""
        import time

        svc = MfaService()
        secret, codes, _ = svc.generate_mfa_setup("alice")
        user_id = uuid.uuid4()

        current_interval = int(time.time()) // 30
        valid_code = str(get_hotp_token(secret, current_interval)).zfill(6)

        mock_user = _make_user(id=user_id)

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        # Sequence: MfaSecret lookup → None (no existing); User fetch → mock_user
        db.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),   # MfaSecret lookup
            MagicMock(scalar_one=MagicMock(return_value=mock_user)),       # User fetch
        ])

        result = await svc.enable_mfa(db, user_id, secret, valid_code, codes)
        assert result is True
        assert mock_user.mfa_enabled is True


# ══════════════════════════════════════════════════════════════════════════════
# 10. MfaService — Code Verification & Replay Protection
# ══════════════════════════════════════════════════════════════════════════════

class TestMfaServiceVerification:
    """Tests backup code consumption, replay protection, and failure cases."""

    @pytest.mark.asyncio
    async def test_verify_returns_false_when_mfa_not_enabled(self):
        """verify_mfa_code must return False if MFA record not found or disabled."""
        db = _make_mock_db(return_value=None)
        svc = MfaService()
        result = await svc.verify_mfa_code(db, uuid.uuid4(), "123456")
        assert result is False

    @pytest.mark.asyncio
    async def test_verify_backup_code_success_and_consumed(self):
        """A valid backup code must verify successfully and be removed from the list."""
        svc = MfaService()
        backup_code = "mybackupcode01"
        hashed = svc.hash_backup_code(backup_code)

        mfa_secret = _make_mfa_secret(
            backup_codes={"codes": [hashed, "other_code_hash"]},
            enabled=True,
        )

        db = AsyncMock()
        db.flush = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=mfa_secret),
        ))

        result = await svc.verify_mfa_code(db, mfa_secret.user_id, backup_code)

        assert result is True
        # Backup code must be consumed (removed from list)
        assert hashed not in mfa_secret.backup_codes["codes"]

    @pytest.mark.asyncio
    async def test_verify_invalid_backup_code_fails(self):
        """An unrecognized backup code must return False."""
        svc = MfaService()
        mfa_secret = _make_mfa_secret(
            backup_codes={"codes": ["hash_of_other_code"]},
            enabled=True,
        )

        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=mfa_secret),
        ))

        result = await svc.verify_mfa_code(db, mfa_secret.user_id, "wrong_backup_code")
        assert result is False

    @pytest.mark.asyncio
    async def test_replay_protection_blocks_reused_totp(self):
        """A TOTP token already stored in Redis replay cache must be rejected."""
        user_id = uuid.uuid4()
        secret = generate_totp_secret()

        mfa_secret = _make_mfa_secret(
            user_id=user_id,
            secret_encrypted=encrypt_mfa_secret(secret),
            backup_codes={"codes": []},
            enabled=True,
        )

        redis = _make_mock_redis()
        redis.exists = AsyncMock(return_value=1)  # Token already seen (replay!)

        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=mfa_secret),
        ))

        svc = MfaService(redis_client=redis)
        result = await svc.verify_mfa_code(db, user_id, "123456")
        assert result is False


# ══════════════════════════════════════════════════════════════════════════════
# 11. RBAC Dependency Guards
# ══════════════════════════════════════════════════════════════════════════════

class TestRbacDependencyGuards:
    """
    Tests for RequiresPermission and RequiresRole dependency guard logic.

    These tests import app.core.auth which transitively imports app.core.redis
    (which uses redis.asyncio). The sys.modules patch at the top of this module
    ensures that redis.asyncio resolves to a MagicMock, allowing the import chain
    to succeed without a live Redis installation.
    """

    @pytest.mark.asyncio
    async def test_requires_permission_allows_matching_permission(self):
        """A user with the matching permission must pass the guard."""
        from app.core.auth import RequiresPermission

        perm = _make_permission("approve_execution", "global")
        role = _make_role("operator")
        role.permissions = [perm]

        user = _make_user(is_superuser=False)
        user.roles = [role]

        guard = RequiresPermission("approve_execution", "global")
        result = await guard(current_user=user)
        assert result is user

    @pytest.mark.asyncio
    async def test_requires_permission_blocks_missing_permission(self):
        """A user without the required permission must get ForbiddenError."""
        from app.core.auth import RequiresPermission

        user = _make_user(is_superuser=False)
        user.roles = []

        guard = RequiresPermission("approve_execution", "global")
        with pytest.raises(ForbiddenError):
            await guard(current_user=user)

    @pytest.mark.asyncio
    async def test_requires_permission_superuser_bypass(self):
        """A superuser must bypass permission checks entirely."""
        from app.core.auth import RequiresPermission

        user = _make_user(is_superuser=True)
        user.roles = []

        guard = RequiresPermission("any_action", "any_resource")
        result = await guard(current_user=user)
        assert result is user

    @pytest.mark.asyncio
    async def test_requires_permission_global_resource_satisfies_specific(self):
        """A 'global' resource permission must satisfy any resource check."""
        from app.core.auth import RequiresPermission

        perm = _make_permission("view_replay", "global")
        role = _make_role("auditor")
        role.permissions = [perm]

        user = _make_user(is_superuser=False)
        user.roles = [role]

        guard = RequiresPermission("view_replay", "recordings")
        result = await guard(current_user=user)
        assert result is user

    @pytest.mark.asyncio
    async def test_requires_role_allows_matching_role(self):
        """A user with a role matching the allowed list must pass."""
        from app.core.auth import RequiresRole

        role = _make_role("admin")
        user = _make_user(is_superuser=False)
        user.roles = [role]

        guard = RequiresRole("admin", "operator")
        result = await guard(current_user=user)
        assert result is user

    @pytest.mark.asyncio
    async def test_requires_role_blocks_unlisted_role(self):
        """A user with an unlisted role must get ForbiddenError."""
        from app.core.auth import RequiresRole

        role = _make_role("viewer")
        user = _make_user(is_superuser=False)
        user.roles = [role]

        guard = RequiresRole("admin", "operator")
        with pytest.raises(ForbiddenError, match="Requires one of roles"):
            await guard(current_user=user)

    @pytest.mark.asyncio
    async def test_requires_role_superuser_bypass(self):
        """A superuser must bypass role checks entirely."""
        from app.core.auth import RequiresRole

        user = _make_user(is_superuser=True)
        user.roles = []

        guard = RequiresRole("admin")
        result = await guard(current_user=user)
        assert result is user

    @pytest.mark.asyncio
    async def test_requires_role_with_enum_role_name(self):
        """RequiresRole must handle role names stored as enum or plain string."""
        from app.core.auth import RequiresRole

        role = _make_role("auditor")
        user = _make_user(is_superuser=False)
        user.roles = [role]

        guard = RequiresRole("auditor")
        result = await guard(current_user=user)
        assert result is user
