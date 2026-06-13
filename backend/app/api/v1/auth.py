# app/api/v1/auth.py
"""Auth API router — handles registration, login, logout, MFA setup, MFA verification, and session management."""

import json
import uuid
from datetime import datetime, UTC
from typing import Optional

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, security_scheme
from app.core.database import get_db
from app.core.exceptions import UnauthorizedError, NotFoundError, BadRequestError, ConflictError
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.models.rbac import UserSession
from app.models.schemas import (
    MfaSetupResponse,
    MfaVerifyRequest,
    SuccessResponse,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
    UserSessionResponse,
)
from app.services.auth_service import AuthService
from app.services.mfa_service import MfaService
from app.services.session_manager import SessionManager

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _make_meta(request: Request) -> dict:
    """Build standard response meta from request context."""
    return {
        "request_id": getattr(request.state, "trace_id", str(uuid.uuid4())),
        "timestamp": datetime.now(UTC),
    }


class RevokeSessionRequest(BaseModel):
    session_id: uuid.UUID


# ── POST /auth/register ───────────────────────────────────────────────────────

@router.post(
    "/register",
    status_code=201,
    response_model=SuccessResponse,
    summary="Register a new user",
)
async def register(
    body: UserRegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse:
    ip_address = request.client.host if request.client else None
    auth_service = AuthService()
    
    user = await auth_service.register_user(
        db,
        body.username,
        body.email,
        body.password,
        ip_address=ip_address
    )
    # Save transaction changes
    await db.commit()

    user_resp = UserResponse.model_validate(user)

    return SuccessResponse(
        success=True,
        data=user_resp,
        meta=_make_meta(request)
    )


# ── POST /auth/login ──────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=SuccessResponse,
    summary="Authenticate credentials and log in",
)
async def login(
    body: UserLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> SuccessResponse:
    ip_address = request.client.host if request.client else None
    auth_service = AuthService()

    user = await auth_service.authenticate_user(
        db,
        body.username_or_email,
        body.password,
        ip_address=ip_address
    )

    if user.mfa_enabled:
        # Check challenge token
        mfa_token = uuid.uuid4().hex
        challenge_key = f"mfa:login:challenge:{mfa_token}"
        if redis:
            await redis.set(challenge_key, str(user.id), ex=300)
        await db.commit()

        token_resp = TokenResponse(
            access_token="",
            requires_mfa=True,
            mfa_token=mfa_token,
            user_id=user.id
        )
        return SuccessResponse(
            success=True,
            data=token_resp,
            meta=_make_meta(request)
        )

    # MFA not enabled. Create session
    sm = SessionManager(redis_client=redis)
    session, raw_token = await sm.create_session(
        db,
        user.id,
        device_info=request.headers.get("User-Agent"),
        ip_address=ip_address,
        user_agent=request.headers.get("User-Agent"),
    )
    await db.commit()

    token_resp = TokenResponse(
        access_token=raw_token,
        requires_mfa=False,
        user_id=user.id
    )
    return SuccessResponse(
        success=True,
        data=token_resp,
        meta=_make_meta(request)
    )


# ── POST /auth/logout ─────────────────────────────────────────────────────────

@router.post(
    "/logout",
    response_model=SuccessResponse,
    summary="Revoke current session",
)
async def logout(
    request: Request,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> SuccessResponse:
    # Extract Bearer token manually to revoke
    if not authorization.startswith("Bearer "):
        raise UnauthorizedError("Invalid authorization header")
    
    raw_token = authorization.split(" ")[1]
    
    # Retrieve current user to log audit event
    sm = SessionManager(redis_client=redis)
    user = await sm.validate_session(db, raw_token)
    
    success = await sm.revoke_session(db, raw_token)
    if success and user:
        auth_service = AuthService()
        ip_address = request.client.host if request.client else None
        await auth_service.log_audit_event(
            db,
            actor_id=user.id,
            action="logout_success",
            resource_type="user",
            resource_id=user.id,
            ip_address=ip_address,
            reason="User logged out successfully",
        )
    
    await db.commit()

    return SuccessResponse(
        success=True,
        data={"message": "Logged out successfully"},
        meta=_make_meta(request)
    )


# ── POST /auth/mfa/setup ──────────────────────────────────────────────────────

@router.post(
    "/mfa/setup",
    response_model=SuccessResponse,
    summary="Initialize MFA setup",
)
async def mfa_setup(
    request: Request,
    current_user=Depends(get_current_user),
    redis=Depends(get_redis),
) -> SuccessResponse:
    if current_user.mfa_enabled:
        raise ConflictError("MFA is already enabled")

    mfa_service = MfaService(redis_client=redis)
    secret, backup_codes, uri = mfa_service.generate_mfa_setup(current_user.username)

    # Temporarily store the setup secret in Redis until verified
    if redis:
        setup_key = f"mfa:setup:secret:{current_user.id}"
        await redis.set(setup_key, json.dumps({"secret": secret, "codes": backup_codes}), ex=900)

    setup_resp = MfaSetupResponse(
        provisioning_uri=uri,
        backup_codes=backup_codes,
        secret=secret
    )
    return SuccessResponse(
        success=True,
        data=setup_resp,
        meta=_make_meta(request)
    )


# ── POST /auth/mfa/verify ─────────────────────────────────────────────────────

@router.post(
    "/mfa/verify",
    response_model=SuccessResponse,
    summary="Verify MFA code to complete login or setup",
)
async def mfa_verify(
    body: MfaVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> SuccessResponse:
    ip_address = request.client.host if request.client else None
    auth_service = AuthService()

    # Case A: MFA validation during login challenge
    if body.mfa_token:
        challenge_key = f"mfa:login:challenge:{body.mfa_token}"
        if not redis:
            raise UnauthorizedError("Redis is required for MFA login")
            
        user_id_raw = await redis.get(challenge_key)
        if not user_id_raw:
            raise UnauthorizedError("MFA challenge token expired or invalid")

        # Redis client uses decode_responses=True, so result is str not bytes
        user_id_str = user_id_raw.decode("utf-8") if isinstance(user_id_raw, bytes) else user_id_raw
        user_id = uuid.UUID(user_id_str)
        mfa_service = MfaService(redis_client=redis)
        
        verified = await mfa_service.verify_mfa_code(db, user_id, body.code)
        if not verified:
            await auth_service.log_audit_event(
                db,
                actor_id=user_id,
                action="login_mfa_failed",
                resource_type="user",
                resource_id=user_id,
                ip_address=ip_address,
                reason="Invalid MFA token during login",
            )
            await db.commit()
            raise UnauthorizedError("Invalid MFA code")

        # Cleanup challenge
        await redis.delete(challenge_key)

        # Login succeeded, create session
        sm = SessionManager(redis_client=redis)
        session, raw_token = await sm.create_session(
            db,
            user_id,
            device_info=request.headers.get("User-Agent"),
            ip_address=ip_address,
            user_agent=request.headers.get("User-Agent"),
        )
        
        await auth_service.log_audit_event(
            db,
            actor_id=user_id,
            action="login_mfa_success",
            resource_type="user",
            resource_id=user_id,
            ip_address=ip_address,
            reason="User completed MFA and logged in",
        )
        await db.commit()

        token_resp = TokenResponse(
            access_token=raw_token,
            requires_mfa=False
        )
        return SuccessResponse(
            success=True,
            data=token_resp,
            meta=_make_meta(request)
        )

    # Case B: Completing MFA setup for already authenticated user
    # Require active user session
    current_user = await get_current_user(
        token_creds=await security_scheme(request),
        db=db,
        redis=redis
    )

    if current_user.mfa_enabled:
        raise ConflictError("MFA is already enabled")

    # Fetch stored setup secret from Redis
    setup_key = f"mfa:setup:secret:{current_user.id}"
    if not redis:
         raise UnauthorizedError("Redis is required for MFA setup")

    setup_data_raw = await redis.get(setup_key)
    if not setup_data_raw:
        raise UnauthorizedError("MFA setup session expired. Please restart setup.")

    # Redis client uses decode_responses=True, so result is str not bytes
    setup_data_str = setup_data_raw.decode("utf-8") if isinstance(setup_data_raw, bytes) else setup_data_raw
    setup_data = json.loads(setup_data_str)
    secret = setup_data["secret"]
    backup_codes = setup_data["codes"]

    mfa_service = MfaService(redis_client=redis)
    enabled = await mfa_service.enable_mfa(db, current_user.id, secret, body.code, backup_codes)

    if not enabled:
        await auth_service.log_audit_event(
            db,
            actor_id=current_user.id,
            action="mfa_setup_failed",
            resource_type="user",
            resource_id=current_user.id,
            ip_address=ip_address,
            reason="MFA code verification failed during setup",
        )
        await db.commit()
        raise UnauthorizedError("Invalid verification code")

    # Clear setup cache
    await redis.delete(setup_key)

    await auth_service.log_audit_event(
        db,
        actor_id=current_user.id,
        action="mfa_setup_success",
        resource_type="user",
        resource_id=current_user.id,
        ip_address=ip_address,
        reason="MFA setup verified and enabled",
    )
    await db.commit()

    return SuccessResponse(
        success=True,
        data={"message": "MFA enabled successfully"},
        meta=_make_meta(request)
    )


# ── GET /auth/sessions ────────────────────────────────────────────────────────

@router.get(
    "/sessions",
    response_model=SuccessResponse,
    summary="List active sessions for current user",
)
async def list_sessions(
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse:
    # Query database for all unrevoked sessions
    stmt = select(UserSession).where(
        UserSession.user_id == current_user.id,
        UserSession.revoked_at.is_(None)
    )
    res = await db.execute(stmt)
    sessions = res.scalars().all()

    session_list = [UserSessionResponse.model_validate(s) for s in sessions]

    return SuccessResponse(
        success=True,
        data=session_list,
        meta=_make_meta(request)
    )


# ── POST /auth/sessions/revoke ────────────────────────────────────────────────

@router.post(
    "/sessions/revoke",
    response_model=SuccessResponse,
    summary="Revoke a specific session",
)
async def revoke_session(
    body: RevokeSessionRequest,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> SuccessResponse:
    # Query session first to ensure it belongs to the current user
    stmt = select(UserSession).where(
        UserSession.id == body.session_id,
        UserSession.user_id == current_user.id
    )
    res = await db.execute(stmt)
    session = res.scalar_one_or_none()

    if not session:
        raise NotFoundError("Session not found")

    if session.revoked_at:
        raise BadRequestError("Session is already revoked")

    now = datetime.now(UTC)
    session.revoked_at = now

    # Remove from Redis
    if redis:
        try:
            cache_key = f"session:{session.session_token}"
            await redis.delete(cache_key)
        except Exception as exc:
            logger.error("auth.redis_session_revoke_failed", error=str(exc))

    auth_service = AuthService()
    ip_address = request.client.host if request.client else None
    await auth_service.log_audit_event(
        db,
        actor_id=current_user.id,
        action="session_revoked",
        resource_type="session",
        resource_id=session.id,
        ip_address=ip_address,
        reason=f"Revoked session {session.id}",
    )
    await db.commit()

    return SuccessResponse(
        success=True,
        data={"message": "Session revoked successfully"},
        meta=_make_meta(request)
    )
