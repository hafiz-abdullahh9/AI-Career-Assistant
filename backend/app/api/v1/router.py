"""
API v1 router — aggregates all v1 sub-routers into one include.
"""
from fastapi import APIRouter

from app.api.v1.applications import router as applications_router
from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.approvals import router as approvals_router
from app.api.v1.audit import router as audit_router

# Top-level router for v1 — included in main.py with prefix /api/v1
v1_router = APIRouter()

v1_router.include_router(health_router)
v1_router.include_router(auth_router)
v1_router.include_router(applications_router)
v1_router.include_router(approvals_router)
v1_router.include_router(audit_router)

