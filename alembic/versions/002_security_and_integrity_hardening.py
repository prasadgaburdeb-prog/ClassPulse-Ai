"""Security and data integrity hardening

Revision ID: 002_security_hardening
Revises: 001_initial_schema
Create Date: 2026-11-14 12:05:00

Purpose:
    Hardens database schema for enhanced authentication security, longitudinal auditability,
    data integrity, and import idempotency without breaking existing student profiles or records.
    Adds:
    - users.password_changed_at for session invalidation on password change (FR-AUTH-05, SEC-010)
    - import_jobs.initiating_user_id and file_hash for deduplication and audit tracking (DATA-004)
    - prediction_history.is_tentative and provenance for ML explainability (ML-005, ML-023)
    - audit_events.actor_id, target, status, details for security logging (SEC-AUD-01)
    - students: composite unique constraint (tenant_id, student_id) for tenant isolation

Expected Data Impact:
    Zero data loss. Non-destructive column additions with sensible defaults. Existing records
    and tenant boundaries are fully preserved.

Locking Considerations:
    Uses Alembic batch mode (`batch_alter_table`) for SQLite table recreation/rebuild.
    On SQLite, creates temporary shadow tables with table-level locking.
    On MySQL (InnoDB), `ALTER TABLE ... ADD COLUMN` operates with online DDL where supported,
    briefly acquiring exclusive metadata locks at start and completion.

Rollback Limitations:
    Downgrade drops the hardened columns (password_changed_at, file_hash, is_tentative, provenance,
    actor_id, target, status, details). Data accumulated in these added columns after migration
    will be discarded upon downgrade. Does not delete core user or student records.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '002_security_hardening'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # 1. users: password_changed_at
    if "users" in tables:
        cols = {c["name"] for c in inspector.get_columns("users")}
        if "password_changed_at" not in cols:
            with op.batch_alter_table("users") as batch_op:
                batch_op.add_column(sa.Column("password_changed_at", sa.DateTime(), nullable=True))

    # 2. import_jobs: initiating_user_id, file_hash
    if "import_jobs" in tables:
        cols = {c["name"] for c in inspector.get_columns("import_jobs")}
        with op.batch_alter_table("import_jobs") as batch_op:
            if "initiating_user_id" not in cols:
                batch_op.add_column(sa.Column("initiating_user_id", sa.Integer(), nullable=True))
            if "file_hash" not in cols:
                batch_op.add_column(sa.Column("file_hash", sa.String(64), nullable=True))

    # 3. prediction_history: is_tentative, provenance
    if "prediction_history" in tables:
        cols = {c["name"] for c in inspector.get_columns("prediction_history")}
        with op.batch_alter_table("prediction_history") as batch_op:
            if "is_tentative" not in cols:
                batch_op.add_column(sa.Column("is_tentative", sa.Boolean(), server_default=sa.false()))
            if "provenance" not in cols:
                batch_op.add_column(sa.Column("provenance", sa.String(100), server_default="benchmark"))

    # 4. audit_events: actor_id, target, status, details
    if "audit_events" in tables:
        cols = {c["name"] for c in inspector.get_columns("audit_events")}
        with op.batch_alter_table("audit_events") as batch_op:
            if "actor_id" not in cols:
                batch_op.add_column(sa.Column("actor_id", sa.Integer(), nullable=True))
            if "target" not in cols:
                batch_op.add_column(sa.Column("target", sa.String(120), nullable=True))
            if "status" not in cols:
                batch_op.add_column(sa.Column("status", sa.String(30), server_default="success"))
            if "details" not in cols:
                batch_op.add_column(sa.Column("details", sa.Text(), nullable=True))

    # 5. create import_previews table
    if "import_previews" not in tables:
        op.create_table(
            "import_previews",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("preview_id", sa.String(64), unique=True, index=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), index=True, nullable=False),
            sa.Column("initiating_user_id", sa.Integer(), nullable=True),
            sa.Column("filename", sa.String(255), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("status", sa.String(30), server_default="pending"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
        )

    # 6. create revoked_tokens table
    if "revoked_tokens" not in tables:
        op.create_table(
            "revoked_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("jti", sa.String(64), unique=True, index=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=True),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
        )

    # 7. create rate_limits table
    if "rate_limits" not in tables:
        op.create_table(
            "rate_limits",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("rate_key", sa.String(120), index=True, nullable=False),
            sa.Column("attempt_timestamp", sa.Float(), index=True, nullable=False),
        )

    # 8. enforce unique index on students (tenant_id, student_id)
    if "students" in tables:
        try:
            op.create_index("uq_tenant_student_id", "students", ["tenant_id", "student_id"], unique=True)
        except Exception:
            pass


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # 1. drop index
    if "students" in tables:
        try:
            op.drop_index("uq_tenant_student_id", table_name="students")
        except Exception:
            pass

    # 2. drop tables
    if "rate_limits" in tables:
        op.drop_table("rate_limits")

    if "revoked_tokens" in tables:
        op.drop_table("revoked_tokens")

    if "import_previews" in tables:
        op.drop_table("import_previews")

    # 3. drop added columns using batch_alter_table for SQLite compatibility
    if "audit_events" in tables:
        cols = {c["name"] for c in inspector.get_columns("audit_events")}
        with op.batch_alter_table("audit_events") as batch_op:
            for col in ["details", "status", "target", "actor_id"]:
                if col in cols:
                    batch_op.drop_column(col)

    if "prediction_history" in tables:
        cols = {c["name"] for c in inspector.get_columns("prediction_history")}
        with op.batch_alter_table("prediction_history") as batch_op:
            for col in ["provenance", "is_tentative"]:
                if col in cols:
                    batch_op.drop_column(col)

    if "import_jobs" in tables:
        cols = {c["name"] for c in inspector.get_columns("import_jobs")}
        with op.batch_alter_table("import_jobs") as batch_op:
            for col in ["file_hash", "initiating_user_id"]:
                if col in cols:
                    batch_op.drop_column(col)

    if "users" in tables:
        cols = {c["name"] for c in inspector.get_columns("users")}
        if "password_changed_at" in cols:
            with op.batch_alter_table("users") as batch_op:
                batch_op.drop_column("password_changed_at")
