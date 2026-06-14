# tests/unit/test_rbac.py
"""
Unit tests for the Role-Based Access Control (RBAC) models and seeding infrastructure.
These tests run without requiring a live database connection by checking model definitions,
constraints, metadata, and mocking database interactions.
"""

import uuid
from datetime import datetime, timedelta, UTC
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Table, UniqueConstraint, ForeignKey
from sqlalchemy.orm import relationship

from app.models.rbac import (
    User,
    Role,
    Permission,
    UserSession,
    MfaSecret,
    AuditEvent,
    user_roles,
    role_permissions,
)
from scripts.seed_rbac import (
    upsert_role,
    upsert_permission,
    assign_permission_to_role,
)


class TestRbacModels:
    """Validates properties, relationships, and metadata of RBAC models."""

    def test_role_enum_and_creation(self):
        """Verifies that Roles can be constructed and support RoleEnum."""
        assert hasattr(Role, "RoleEnum")
        assert Role.RoleEnum.admin.value == "admin"
        assert Role.RoleEnum.operator.value == "operator"
        assert Role.RoleEnum.auditor.value == "auditor"
        assert Role.RoleEnum.viewer.value == "viewer"

        role = Role(
            name=Role.RoleEnum.operator,
            description="Operator with job submission access"
        )
        assert role.name == "operator"
        assert role.description == "Operator with job submission access"

    def test_permission_uniqueness_metadata(self):
        """Ensures that uniqueness constraint exists on action and resource."""
        # Find unique constraint on permissions table
        constraints = Permission.__table__.constraints
        unique_constraints = [c for c in constraints if isinstance(c, UniqueConstraint)]
        
        # Verify there is a unique constraint on (action, resource)
        found = False
        for uc in unique_constraints:
            cols = {col.name for col in uc.columns}
            if cols == {"action", "resource"}:
                found = True
                break
        
        assert found, "UniqueConstraint('action', 'resource') not found on permissions table."

    def test_assignment_relationships(self):
        """Verifies relationship structures between User, Role, and Permission."""
        user = User(
            username="test_user",
            email="test@example.com",
            password_hash="hashed_pw"
        )
        role = Role(name=Role.RoleEnum.auditor)
        permission = Permission(action="view", resource="audit")

        # Assign permission to role and role to user
        role.permissions.append(permission)
        user.roles.append(role)

        assert role in user.roles
        assert permission in role.permissions
        assert user in role.users
        assert role in permission.roles

    def test_user_session_lifecycle(self):
        """Verifies properties and constraints on UserSession."""
        user_id = uuid.uuid4()
        expires_at = datetime.now(UTC) + timedelta(days=1)
        session = UserSession(
            user_id=user_id,
            session_token="sec_token_123",
            expires_at=expires_at,
            device_info="Test Device",
            ip_address="127.0.0.1",
            user_agent="Mozilla/5.0"
        )

        assert session.user_id == user_id
        assert session.session_token == "sec_token_123"
        assert session.expires_at == expires_at
        assert session.device_info == "Test Device"
        assert session.ip_address == "127.0.0.1"
        assert session.user_agent == "Mozilla/5.0"

    def test_audit_event_immutability_and_actor(self):
        """Checks AuditEvent properties and SET NULL ondelete behavior."""
        # Check foreign keys on audit_events
        fk_actor = None
        for fk in AuditEvent.__table__.foreign_keys:
            if fk.parent.name == "actor_id":
                fk_actor = fk
                break

        assert fk_actor is not None, "actor_id foreign key not found on audit_events table"
        assert fk_actor.ondelete == "SET NULL", "actor_id foreign key must have ON DELETE SET NULL constraint"

    def test_cascade_delete_configuration(self):
        """Checks relationship cascades and association table cascade constraints."""
        # Check cascade definitions in User relationships (looking for delete & delete-orphan)
        user_sessions_rel = User.__mapper__.relationships["sessions"]
        assert "delete-orphan" in user_sessions_rel.cascade
        assert "delete" in user_sessions_rel.cascade

        user_mfa_rel = User.__mapper__.relationships["mfa_secret"]
        assert "delete-orphan" in user_mfa_rel.cascade
        assert "delete" in user_mfa_rel.cascade

        # Check ON DELETE CASCADE on association tables
        for table in (user_roles, role_permissions):
            for fk in table.foreign_keys:
                assert fk.ondelete == "CASCADE", f"FK {fk} on {table.name} must have ON DELETE CASCADE"


class TestIdempotentSeeding:
    """Verifies that the seeding script runs upsert logic correctly."""

    @patch("scripts.seed_rbac.pg_insert")
    def test_upsert_role(self, mock_pg_insert):
        """Checks that upsert_role generates the expected PostgreSQL UPSERT statement."""
        mock_sess = MagicMock()
        mock_stmt = MagicMock()
        
        # Configure mocks to simulate PG insert statement construction with values()
        mock_pg_insert.return_value = mock_stmt
        mock_stmt.values.return_value = mock_stmt
        mock_stmt.on_conflict_do_nothing.return_value = mock_stmt

        # Run upsert
        upsert_role(mock_sess, "operator")

        # Verify pg_insert was called with Role table
        mock_pg_insert.assert_called_once_with(Role.__table__)
        # Verify on_conflict_do_nothing was called with the 'name' column as conflict target
        mock_stmt.on_conflict_do_nothing.assert_called_once_with(
            index_elements=[Role.__table__.c.name]
        )
        # Verify execution
        mock_sess.execute.assert_any_call(mock_stmt)

    @patch("scripts.seed_rbac.pg_insert")
    def test_upsert_permission(self, mock_pg_insert):
        """Checks that upsert_permission generates the expected PostgreSQL UPSERT statement."""
        mock_sess = MagicMock()
        mock_stmt = MagicMock()

        mock_pg_insert.return_value = mock_stmt
        mock_stmt.values.return_value = mock_stmt
        mock_stmt.on_conflict_do_nothing.return_value = mock_stmt

        # Run upsert
        upsert_permission(mock_sess, "approve_execution")

        # Verify pg_insert was called with Permission table
        mock_pg_insert.assert_called_once_with(Permission.__table__)
        # Verify conflict index elements are action and resource
        mock_stmt.on_conflict_do_nothing.assert_called_once_with(
            index_elements=[Permission.__table__.c.action, Permission.__table__.c.resource]
        )
        # Verify execution
        mock_sess.execute.assert_any_call(mock_stmt)

    @patch("scripts.seed_rbac.pg_insert")
    def test_assign_permission_to_role(self, mock_pg_insert):
        """Checks that assign_permission_to_role runs insert on association table with conflict guard."""
        mock_sess = MagicMock()
        mock_stmt = MagicMock()

        mock_pg_insert.return_value = mock_stmt
        mock_stmt.values.return_value = mock_stmt
        mock_stmt.on_conflict_do_nothing.return_value = mock_stmt

        role_id = uuid.uuid4()
        perm_id = uuid.uuid4()

        # Run assignment
        assign_permission_to_role(mock_sess, role_id, perm_id)

        # Verify pg_insert was called with role_permissions association table
        mock_pg_insert.assert_called_once_with(role_permissions)
        # Verify on_conflict_do_nothing index elements
        mock_stmt.on_conflict_do_nothing.assert_called_once_with(
            index_elements=[role_permissions.c.role_id, role_permissions.c.permission_id]
        )
        # Verify execution
        mock_sess.execute.assert_called_once_with(mock_stmt)
