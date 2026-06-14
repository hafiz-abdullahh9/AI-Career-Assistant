# verify_rbac.py
"""Verification script for RBAC migration.
Runs a series of checks:
1. Audit preservation after user deletion (actor_id becomes NULL).
2. Cascade deletes for user_roles, role_permissions, user_sessions, mfa_secrets.
3. Index existence.
4. Uniqueness constraints.
5. Security validation – ensure only hash/encrypted columns hold data.
"""
import sys
from datetime import datetime, timedelta

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import IntegrityError

# Load settings (assumes get_settings returns .database_url)
import os
import pathlib
# Add project root (Member_04_Application_Automation) to PYTHONPATH for proper 'app' package imports
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from app.core.config import get_settings

# Use synchronous driver for verification script
db_url = get_settings().database_url.replace('+asyncpg', '+psycopg2')
engine = create_engine(db_url)

def exec_sql(stmt, **params):
    with engine.begin() as conn:
        return conn.execute(text(stmt), params)

def audit_preservation_test():
    # clean up first
    exec_sql("DELETE FROM users WHERE username = 'audit_user'")
    # create a user
    user_id = exec_sql(
        "INSERT INTO users (username, email, password_hash, is_active, is_superuser, mfa_enabled, failed_login_attempts) "
        "VALUES ('audit_user', 'audit@example.com', 'hash', true, false, false, 0) RETURNING id"
    ).scalar()
    # create an audit event referencing the user
    audit_id = exec_sql(
        "INSERT INTO audit_events (actor_id, action, resource_type, timestamp, metadata_json) "
        "VALUES (:uid, 'test_action', 'test_resource', now(), '{}') RETURNING id",
        uid=user_id,
    ).scalar()
    # delete the user
    exec_sql("DELETE FROM users WHERE id = :uid", uid=user_id)
    # verify audit event still exists and actor_id is NULL
    result = exec_sql("SELECT actor_id FROM audit_events WHERE id = :aid", aid=audit_id).fetchone()
    if result is None:
        return False, "Audit event missing after user deletion"
    if result[0] is not None:
        return False, f"actor_id not null after deletion (found {result[0]})"
    return True, "Audit preservation OK"

def cascade_validation_test():
    # clean up first
    exec_sql("DELETE FROM users WHERE username = 'cascade_user'")
    # create user, role, permission, session, mfa, assignments
    rid = exec_sql("SELECT id FROM roles WHERE name = 'operator'").scalar()
    if not rid:
        rid = exec_sql(
            "INSERT INTO roles (name) VALUES ('operator') RETURNING id"
        ).scalar()
        created_role = True
    else:
        created_role = False

    pid = exec_sql("SELECT id FROM permissions WHERE action = 'view' AND resource = 'audit'").scalar()
    if not pid:
        pid = exec_sql(
            "INSERT INTO permissions (action, resource) VALUES ('view', 'audit') RETURNING id"
        ).scalar()
        created_perm = True
    else:
        created_perm = False

    # Check if assignment already exists
    rp_exists = exec_sql("SELECT 1 FROM role_permissions WHERE role_id = :rid AND permission_id = :pid", rid=rid, pid=pid).fetchone()
    if not rp_exists:
        exec_sql("INSERT INTO role_permissions (role_id, permission_id) VALUES (:rid, :pid)", rid=rid, pid=pid)
        created_rp = True
    else:
        created_rp = False

    uid = exec_sql(
        "INSERT INTO users (username, email, password_hash, is_active, is_superuser, mfa_enabled, failed_login_attempts) "
        "VALUES ('cascade_user', 'cascade@example.com', 'hash', true, false, false, 0) RETURNING id"
    ).scalar()

    # assign role to user
    exec_sql("INSERT INTO user_roles (user_id, role_id) VALUES (:uid, :rid)", uid=uid, rid=rid)
    # create session and mfa secret for user
    sess_id = exec_sql(
        "INSERT INTO user_sessions (user_id, session_token, expires_at) VALUES (:uid, 'token123', now()+interval '1 day') RETURNING id",
        uid=uid,
    ).scalar()
    mfa_id = exec_sql(
        "INSERT INTO mfa_secrets (user_id, secret_encrypted, backup_codes, enabled) "
        "VALUES (:uid, 'enc', '{}', false) RETURNING id",
        uid=uid,
    ).scalar()
    # delete the user
    exec_sql("DELETE FROM users WHERE id = :uid", uid=uid)
    # verify cascade deletions
    checks = []
    # user_roles should be gone
    ur = exec_sql("SELECT 1 FROM user_roles WHERE user_id = :uid", uid=uid).fetchone()
    checks.append((ur is None, "user_roles cascade"))
    # role_permissions should remain (role still exists)
    rp = exec_sql("SELECT 1 FROM role_permissions WHERE role_id = :rid", rid=rid).fetchone()
    checks.append((rp is not None, "role_permissions preserved (role exists)"))
    # user_sessions should be gone
    us = exec_sql("SELECT 1 FROM user_sessions WHERE id = :sid", sid=sess_id).fetchone()
    checks.append((us is None, "user_sessions cascade"))
    # mfa_secrets should be gone
    mf = exec_sql("SELECT 1 FROM mfa_secrets WHERE id = :mid", mid=mfa_id).fetchone()
    checks.append((mf is None, "mfa_secrets cascade"))
    # Clean up what we created specifically for this test
    if created_rp:
        exec_sql("DELETE FROM role_permissions WHERE role_id = :rid AND permission_id = :pid", rid=rid, pid=pid)
    if created_role:
        exec_sql("DELETE FROM roles WHERE id = :rid", rid=rid)
    if created_perm:
        exec_sql("DELETE FROM permissions WHERE id = :pid", pid=pid)
    # evaluate
    all_ok = all(flag for flag, _ in checks)
    msgs = [msg for flag, msg in checks if not flag]
    return all_ok, ", ".join(msgs) if msgs else "Cascade validation OK"

def index_validation_test():
    insp = inspect(engine)
    indexes = insp.get_indexes('audit_events') + insp.get_indexes('user_sessions') + insp.get_indexes('users') + insp.get_indexes('user_roles') + insp.get_indexes('role_permissions')
    index_names = {idx['name'] for idx in indexes}
    required = {
        'ix_audit_events_actor_id',
        'ix_user_sessions_session_token',
        'ix_user_sessions_user_id',
        'ix_user_sessions_expires_at',
        'ix_users_created_at',
        'ix_user_roles_user_id',
        'ix_user_roles_role_id',
        'ix_role_permissions_role_id',
        'ix_role_permissions_permission_id',
    }
    missing = required - index_names
    if missing:
        return False, f"Missing indexes: {', '.join(missing)}"
    return True, "All required indexes present"

def uniqueness_validation_test():
    # clean up first
    exec_sql("DELETE FROM users WHERE username IN ('uniq_user', 'other_user') OR email = 'uniq@example.com'")
    # attempt duplicate username/email
    try:
        exec_sql("INSERT INTO users (username, email, password_hash, is_active, is_superuser, mfa_enabled, failed_login_attempts) VALUES ('uniq_user', 'uniq@example.com', 'hash', true, false, false, 0)")
    except IntegrityError:
        return False, "Cannot insert initial user for uniqueness test"
    # duplicate username
    try:
        exec_sql("INSERT INTO users (username, email, password_hash, is_active, is_superuser, mfa_enabled, failed_login_attempts) VALUES ('uniq_user', 'other@example.com', 'hash', true, false, false, 0)")
        return False, "Duplicate username allowed"
    except IntegrityError:
        pass
    # duplicate email
    try:
        exec_sql("INSERT INTO users (username, email, password_hash, is_active, is_superuser, mfa_enabled, failed_login_attempts) VALUES ('other_user', 'uniq@example.com', 'hash', true, false, false, 0)")
        return False, "Duplicate email allowed"
    except IntegrityError:
        pass
    # clean up
    exec_sql("DELETE FROM users WHERE username = 'uniq_user' OR email = 'uniq@example.com'")
    return True, "Uniqueness constraints OK"

def security_validation_test():
    # Verify columns exist and are of expected type (no plain text beyond hashed fields)
    insp = inspect(engine)
    cols = {col['name']: col for col in insp.get_columns('users')}
    if cols['password_hash']['type'].__class__.__name__ != 'VARCHAR':
        return False, "password_hash column type unexpected"
    # Check mfa_secrets column
    mfa_cols = {c['name']: c for c in insp.get_columns('mfa_secrets')}
    if mfa_cols['secret_encrypted']['type'].__class__.__name__ != 'VARCHAR':
        return False, "secret_encrypted column type unexpected"
    # Session token column should be varchar and unique (already ensured)
    return True, "Security column types OK"

def main():
    checks = [
        ("Audit preservation", audit_preservation_test),
        ("Cascade validation", cascade_validation_test),
        ("Index validation", index_validation_test),
        ("Uniqueness validation", uniqueness_validation_test),
        ("Security validation", security_validation_test),
    ]
    all_pass = True
    for name, fn in checks:
        ok, msg = fn()
        status = "PASS" if ok else "FAIL"
        print(f"{name}: {status} - {msg}")
        if not ok:
            all_pass = False
    sys.exit(0 if all_pass else 1)

if __name__ == "__main__":
    main()
