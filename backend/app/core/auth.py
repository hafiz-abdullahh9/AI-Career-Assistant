# app/core/auth.py
"""FastAPI Authentication and RBAC dependencies.

Provides:
- get_current_user: extracts Bearer token, validates session, returns User.
- RequiresPermission: checks if current user has the required action:resource permission.
- RequiresRole: checks if current user belongs to one of the specified roles.
"""

from typing import Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.redis import get_redis
from app.models.rbac import User
from app.services.session_manager import SessionManager

# Initialize HTTP Bearer security scheme
security_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    token_creds: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> User:
    """FastAPI dependency to authenticate requests using Bearer token.

    Validates session token via SessionManager (checking Redis cache & DB).
    Returns the User ORM object with roles/permissions loaded.
    """
    raw_token = token_creds.credentials
    sm = SessionManager(redis_client=redis)
    
    user = await sm.validate_session(db, raw_token)
    if not user:
        raise UnauthorizedError("Invalid or expired session token")

    if not user.is_active:
        raise UnauthorizedError("User account is inactive")

    return user


class RequiresPermission:
    """FastAPI dependency class constructor to check RBAC permissions.

    Usage:
        @router.post("/execute", dependencies=[Depends(RequiresPermission("approve_execution", "global"))])
    """

    def __init__(self, action: str, resource: str):
        self.action = action
        self.resource = resource

    async def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        # Superusers bypass all permission checks
        if current_user.is_superuser:
            return current_user

        # Scan roles and permissions
        for role in current_user.roles:
            for perm in role.permissions:
                # Permission action matches, and resource matches specifically or is 'global'
                if perm.action == self.action and (perm.resource == self.resource or perm.resource == "global"):
                    return current_user

        raise ForbiddenError(f"Required permission '{self.action}' on '{self.resource}' not granted.")


class RequiresRole:
    """FastAPI dependency class constructor to restrict access to specific roles.

    Usage:
        @router.get("/admin/dashboard", dependencies=[Depends(RequiresRole("admin"))])
    """

    def __init__(self, *allowed_roles: str):
        self.allowed_roles = allowed_roles

    async def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if current_user.is_superuser:
            return current_user

        # Get role names as strings
        user_role_names = [
            r.name.value if hasattr(r.name, "value") else str(r.name)
            for r in current_user.roles
        ]

        for role in self.allowed_roles:
            if role in user_role_names:
                return current_user

        raise ForbiddenError(f"Access denied. Requires one of roles: {', '.join(self.allowed_roles)}")
