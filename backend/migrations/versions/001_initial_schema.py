"""
Initial database schema — Phase A Foundation.

Creates:
  1. applications          — central tracking table
  2. application_status_history — immutable audit log
  3. application_logs      — per-application event log

Revision: 001_initial_schema
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# Alembic revision identifiers
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enable pgcrypto for gen_random_uuid() ──────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ── applications ──────────────────────────────────────────────────────
    op.create_table(
        "applications",
        sa.Column(
            "application_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", UUID(as_uuid=True), nullable=False),

        # Job context snapshot
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("role_title", sa.String(255), nullable=False),
        sa.Column("platform", sa.String(100), nullable=True),
        sa.Column("application_url", sa.Text, nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),

        # Method & status
        sa.Column("method", sa.String(50), nullable=False),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="queued",
        ),

        # Asset references
        sa.Column("resume_version_id", UUID(as_uuid=True), nullable=True),
        sa.Column("cover_letter_version_id", UUID(as_uuid=True), nullable=True),

        # Timing
        sa.Column(
            "queued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),

        # Confirmation
        sa.Column("confirmation_id", sa.String(255), nullable=True),

        # Retry
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer, nullable=False, server_default="3"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),

        # Task ref
        sa.Column("celery_task_id", sa.String(255), nullable=True),

        # Soft delete
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),

        # Flexible metadata
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),

        # Audit
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Unique constraint: one application per (user, job)
    op.create_unique_constraint(
        "uq_applications_user_job",
        "applications",
        ["user_id", "job_id"],
    )

    # Query-hot indexes
    op.create_index("idx_applications_user_id", "applications", ["user_id"])
    op.create_index("idx_applications_status", "applications", ["status"])
    op.create_index(
        "idx_applications_queued_at",
        "applications",
        [sa.text("queued_at DESC")],
    )
    op.create_index(
        "idx_applications_user_status",
        "applications",
        ["user_id", "status"],
    )

    # ── application_status_history ─────────────────────────────────────────
    op.create_table(
        "application_status_history",
        sa.Column(
            "history_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "application_id",
            UUID(as_uuid=True),
            sa.ForeignKey("applications.application_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(50), nullable=True),
        sa.Column("to_status", sa.String(50), nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("changed_by", sa.String(100), nullable=False, server_default="system"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "idx_status_history_app_id",
        "application_status_history",
        ["application_id"],
    )
    op.create_index(
        "idx_status_history_created_at",
        "application_status_history",
        [sa.text("created_at DESC")],
    )

    # ── application_logs ───────────────────────────────────────────────────
    op.create_table(
        "application_logs",
        sa.Column(
            "log_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "application_id",
            UUID(as_uuid=True),
            sa.ForeignKey("applications.application_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("event", sa.String(100), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("context", JSONB, nullable=False, server_default="{}"),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "idx_app_logs_application_id",
        "application_logs",
        ["application_id"],
    )
    op.create_index(
        "idx_app_logs_created_at",
        "application_logs",
        [sa.text("created_at DESC")],
    )

    # ── updated_at trigger ─────────────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_applications_updated_at
        BEFORE UPDATE ON applications
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_applications_updated_at ON applications")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")
    op.drop_table("application_logs")
    op.drop_table("application_status_history")
    op.drop_table("applications")
