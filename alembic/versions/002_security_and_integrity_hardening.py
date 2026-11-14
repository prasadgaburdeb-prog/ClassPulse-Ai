"""Security and data integrity hardening

Revision ID: 002_security_hardening
Revises: 001_initial_schema
Create Date: 2026-11-14 12:05:00

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
            op.add_column("users", sa.Column("password_changed_at", sa.DateTime(), nullable=True))

    # 2. import_jobs: initiating_user_id, file_hash
    if "import_jobs" in tables:
        cols = {c["name"] for c in inspector.get_columns("import_jobs")}
        if "initiating_user_id" not in cols:
            op.add_column("import_jobs", sa.Column("initiating_user_id", sa.Integer(), nullable=True))
        if "file_hash" not in cols:
            op.add_column("import_jobs", sa.Column("file_hash", sa.String(64), nullable=True))

    # 3. prediction_history: is_tentative, provenance
    if "prediction_history" in tables:
        cols = {c["name"] for c in inspector.get_columns("prediction_history")}
        if "is_tentative" not in cols:
            op.add_column("prediction_history", sa.Column("is_tentative", sa.Boolean(), server_default=sa.false()))
        if "provenance" not in cols:
            op.add_column("prediction_history", sa.Column("provenance", sa.String(100), server_default="benchmark"))

    # 4. audit_events: actor_id, target, status, details
    if "audit_events" in tables:
        cols = {c["name"] for c in inspector.get_columns("audit_events")}
        if "actor_id" not in cols:
            op.add_column("audit_events", sa.Column("actor_id", sa.Integer(), nullable=True))
        if "target" not in cols:
            op.add_column("audit_events", sa.Column("target", sa.String(120), nullable=True))
        if "status" not in cols:
            op.add_column("audit_events", sa.Column("status", sa.String(30), server_default="success"))
        if "details" not in cols:
            op.add_column("audit_events", sa.Column("details", sa.Text(), nullable=True))

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
    try:
        op.drop_index("uq_tenant_student_id", table_name="students")
    except Exception:
        pass
    op.drop_table("rate_limits")
    op.drop_table("revoked_tokens")
    op.drop_table("import_previews")
