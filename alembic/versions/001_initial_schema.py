"""Initial baseline schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-11-14 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "tenants" not in tables:
        op.create_table(
            "tenants",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(120), unique=True, nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("email", sa.String(191), unique=True, index=True, nullable=False),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("full_name", sa.String(120), server_default=""),
            sa.Column("role", sa.String(30), server_default="owner"),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("last_login_at", sa.DateTime(), nullable=True),
        )

    if "students" not in tables:
        op.create_table(
            "students",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("student_id", sa.String(120), index=True, nullable=False),
            sa.Column("name", sa.String(150), server_default=""),
            sa.Column("course_id", sa.String(80), server_default="General"),
            sa.Column("batch_id", sa.String(80), server_default="Standard"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    if "import_jobs" not in tables:
        op.create_table(
            "import_jobs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("filename", sa.String(255), nullable=False),
            sa.Column("status", sa.String(30), nullable=False),
            sa.Column("accepted_rows", sa.Integer(), server_default="0"),
            sa.Column("rejected_rows", sa.Integer(), server_default="0"),
            sa.Column("summary_json", sa.Text(), server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    if "records" not in tables:
        op.create_table(
            "records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("import_id", sa.Integer(), sa.ForeignKey("import_jobs.id"), nullable=False, index=True),
            sa.Column("record_type", sa.String(30), index=True, nullable=False),
            sa.Column("data_json", sa.Text(), nullable=False),
        )

    if "prediction_history" not in tables:
        op.create_table(
            "prediction_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("student_id", sa.String(120), index=True, nullable=False),
            sa.Column("pass_probability", sa.Float(), nullable=False),
            sa.Column("risk_level", sa.String(50), nullable=False),
            sa.Column("predicted_outcome", sa.String(50), nullable=False),
            sa.Column("avg_mock_score", sa.Float(), nullable=True),
            sa.Column("attendance_rate", sa.Float(), nullable=False),
            sa.Column("financial_risk_level", sa.String(50), server_default="Clear"),
            sa.Column("model_version", sa.String(50), server_default="v2.1.0-benchmark"),
            sa.Column("factors_json", sa.Text(), server_default="[]"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    if "audit_events" not in tables:
        op.create_table(
            "audit_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("event", sa.String(80), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("prediction_history")
    op.drop_table("records")
    op.drop_table("import_jobs")
    op.drop_table("students")
    op.drop_table("users")
    op.drop_table("tenants")
