"""
Acceptance Tests for Database Migrations and Reversibility (AT-04 to AT-07, FR-DB-01 to FR-DB-05).
"""
import os
import shutil
import subprocess
import pytest
from pathlib import Path
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic.config import Config
from alembic import command

BASE_DIR = Path(__file__).resolve().parent.parent

def run_alembic_command(args: list[str], db_url: str):
    alembic_cfg = Config(str(BASE_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    return alembic_cfg

def test_at_04_alembic_isolation():
    """AT-04: Alembic commands shall not import application startup code that mutates schemas."""
    # Verify alembic/env.py imports from app.models and app.database, not app.main
    env_content = (BASE_DIR / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "from app.models import Base" in env_content
    assert "from app.database import DATABASE_URL" in env_content
    assert "from app.main import" not in env_content

def test_at_05_fresh_database_migration(tmp_path):
    """AT-05: All migrations upgrade an empty database to head."""
    db_file = tmp_path / "fresh_test.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    cfg = run_alembic_command(["upgrade", "head"], db_url)
    
    # Run upgrade head on completely empty DB
    command.upgrade(cfg, "head")
    
    # Inspect schema
    engine = sa.create_engine(db_url)
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()
    
    expected_tables = {
        "tenants", "users", "students", "import_jobs", "records",
        "prediction_history", "audit_events", "import_previews",
        "revoked_tokens", "rate_limits", "alembic_version"
    }
    assert expected_tables.issubset(set(tables))
    
    # Check columns on hardened tables
    user_cols = {c["name"] for c in inspector.get_columns("users")}
    assert "password_changed_at" in user_cols
    
    pred_cols = {c["name"] for c in inspector.get_columns("prediction_history")}
    assert "is_tentative" in pred_cols
    assert "provenance" in pred_cols
    
    engine.dispose()

def test_at_06_existing_database_migration_preserves_data(tmp_path):
    """AT-06: Existing database records and tenant ownership survive upgrade."""
    backup_file = BASE_DIR / "classpulse.db.v3_backup"
    assert backup_file.exists(), "classpulse.db.v3_backup required for existing DB verification"
    
    db_file = tmp_path / "existing_test.db"
    shutil.copyfile(backup_file, db_file)
    db_url = f"sqlite:///{db_file.as_posix()}"
    
    cfg = run_alembic_command(["upgrade", "head"], db_url)
    command.upgrade(cfg, "head")
    
    # Verify data integrity
    engine = sa.create_engine(db_url)
    with Session(engine) as s:
        # Tenants exist
        tenant_count = s.scalar(sa.text("SELECT count(*) FROM tenants"))
        assert tenant_count >= 5
        
        # Users exist
        user_count = s.scalar(sa.text("SELECT count(*) FROM users"))
        assert user_count >= 5
        
        # Records exist
        record_count = s.scalar(sa.text("SELECT count(*) FROM records"))
        assert record_count >= 400
        
        # Tenant isolation preserved: check records belonging to tenant 1
        t1_records = s.scalar(sa.text("SELECT count(*) FROM records WHERE tenant_id = 1"))
        assert t1_records > 0
    engine.dispose()

def test_at_07_downgrade_and_reversibility(tmp_path):
    """AT-07: Downgrade reverses safely from head to 001_initial_schema and re-upgrades without data loss."""
    backup_file = BASE_DIR / "classpulse.db.v3_backup"
    db_file = tmp_path / "reversibility_test.db"
    shutil.copyfile(backup_file, db_file)
    db_url = f"sqlite:///{db_file.as_posix()}"
    
    cfg = run_alembic_command(["upgrade", "head"], db_url)
    command.upgrade(cfg, "head")
    
    # 1. Downgrade to 001_initial_schema
    command.downgrade(cfg, "001_initial_schema")
    
    engine = sa.create_engine(db_url)
    inspector = sa.inspect(engine)
    tables = inspector.get_table_names()
    
    # Added tables should be gone
    assert "rate_limits" not in tables
    assert "revoked_tokens" not in tables
    assert "import_previews" not in tables
    
    # Base tables and data still exist!
    with Session(engine) as s:
        tenant_count = s.scalar(sa.text("SELECT count(*) FROM tenants"))
        assert tenant_count >= 5
        user_count = s.scalar(sa.text("SELECT count(*) FROM users"))
        assert user_count >= 5
    engine.dispose()
    
    # 2. Re-upgrade cleanly to head
    command.upgrade(cfg, "head")
    
    engine2 = sa.create_engine(db_url)
    inspector2 = sa.inspect(engine2)
    tables2 = inspector2.get_table_names()
    assert "rate_limits" in tables2
    assert "revoked_tokens" in tables2
    assert "import_previews" in tables2
    engine2.dispose()
