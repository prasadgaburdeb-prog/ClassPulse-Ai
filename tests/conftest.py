import os
import pytest
from pathlib import Path
from alembic.config import Config
from alembic import command
from sqlalchemy import inspect
from app.database import engine

@pytest.fixture(scope="session", autouse=True)
def ensure_test_database_migrated():
    """Ensure database schema is migrated to head prior to running test suite."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    required_tables = {"tenants", "users", "students", "records", "revoked_tokens", "rate_limits"}
    if not required_tables.issubset(tables):
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
