"""RBAC seeding script (idempotent)

Creates fixed roles and baseline permissions, then assigns permissions
according to the recommended mapping. The script can be safely re‑run –
it uses INSERT ... ON CONFLICT DO NOTHING for the key tables and checks
existing assignments before inserting into the association tables.
"""
import os
import pathlib
import sys
from sqlalchemy import create_engine, insert, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert

# Ensure project root is in PYTHONPATH for import of app package
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.models.rbac import Role, Permission, role_permissions

# ----- Configuration -----
FIXED_ROLES = ["admin", "operator", "auditor", "viewer"]
BASELINE_PERMISSIONS = [
    "approve_execution",
    "cancel_execution",
    "manage_users",
    "manage_roles",
    "manage_sessions",
    "view_replay",
    "view_audits",
    "resolve_escalations",
    "manage_queues",
    "access_dashboard",
]
# Mapping of role -> list of permission names
ROLE_PERMISSIONS_MAP = {
    "admin": BASELINE_PERMISSIONS,
    "operator": [
        "approve_execution",
        "cancel_execution",
        "manage_queues",
        "access_dashboard",
        "view_replay",
    ],
    "auditor": ["view_audits", "view_replay"],
    "viewer": ["access_dashboard"],
}


def get_engine():
    # Use synchronous driver for seeding (replace asyncpg with psycopg2 if present)
    db_url = get_settings().database_url.replace("+asyncpg", "+psycopg2")
    return create_engine(db_url)


def upsert_role(sess: Session, name: str) -> Role:
    stmt = pg_insert(Role.__table__).values(name=name).on_conflict_do_nothing(index_elements=[Role.__table__.c.name])
    sess.execute(stmt)
    # Return the persisted instance
    return sess.execute(select(Role).where(Role.name == name)).scalar_one()


def upsert_permission(sess: Session, name: str) -> Permission:
    # Use the permission name as the action, with a generic 'global' resource
    stmt = pg_insert(Permission.__table__).values(action=name, resource='global').on_conflict_do_nothing(
        index_elements=[Permission.__table__.c.action, Permission.__table__.c.resource]
    )
    sess.execute(stmt)
    return sess.execute(select(Permission).where(
        Permission.action == name,
        Permission.resource == 'global'
    )).scalar_one()


def assign_permission_to_role(sess: Session, role_id: int, permission_id: int):
    # role_permissions association table has (role_id, permission_id) primary key
    stmt = pg_insert(role_permissions).values(role_id=role_id, permission_id=permission_id).on_conflict_do_nothing(index_elements=[role_permissions.c.role_id, role_permissions.c.permission_id])
    sess.execute(stmt)


def main():
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        # Seed roles
        for role_name in FIXED_ROLES:
            upsert_role(session, role_name)
        # Seed permissions
        for perm_name in BASELINE_PERMISSIONS:
            upsert_permission(session, perm_name)
        session.commit()
        # Assign permissions to roles
        for role_name, perms in ROLE_PERMISSIONS_MAP.items():
            role = session.execute(select(Role).where(Role.name == role_name)).scalar_one()
            for perm_name in perms:
                perm = session.execute(select(Permission).where(
                    Permission.action == perm_name,
                    Permission.resource == 'global'
                )).scalar_one()
                assign_permission_to_role(session, role.id, perm.id)
        session.commit()
        print("RBAC seeding completed successfully (idempotent).")

if __name__ == "__main__":
    main()
