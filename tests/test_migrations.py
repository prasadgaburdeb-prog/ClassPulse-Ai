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

def _prepare_baseline_v1_database(target_path: Path) -> str:
    """Prepare a baseline v1 schema database from disk backup or synthesize it on clean checkouts."""
    backup_file = BASE_DIR / "classpulse.db.v3_backup"
    if backup_file.exists() and backup_file.stat().st_size > 10000:
        shutil.copyfile(backup_file, target_path)
    else:
        # Create baseline v1 schema on clean systems where *.db is gitignored
        db_url = f"sqlite:///{target_path.as_posix()}"
        cfg = run_alembic_command(["upgrade", "001_initial_schema"], db_url)
        command.upgrade(cfg, "001_initial_schema")
        engine = sa.create_engine(db_url)
        with Session(engine) as s:
            for t_id in range(1, 6):
                s.execute(sa.text("INSERT INTO tenants (id, name, created_at) VALUES (:id, :name, '2026-01-01 00:00:00')"),
                          {"id": t_id, "name": f"Tenant {t_id}"})
                s.execute(sa.text("INSERT INTO users (id, tenant_id, email, password_hash, role, created_at) VALUES (:id, :tid, :email, :pwd, :role, '2026-01-01 00:00:00')"),
                          {"id": t_id, "tid": t_id, "email": f"user{t_id}@classpulse.edu", "pwd": "hash", "role": "admin"})
            s.execute(sa.text("INSERT INTO import_jobs (id, tenant_id, filename, status, created_at) VALUES (1, 1, 'test.csv', 'completed', '2026-01-01 00:00:00')"))
            for r_id in range(1, 405):
                s.execute(sa.text("INSERT INTO records (tenant_id, import_id, record_type, data_json) VALUES (1, 1, 'attendance', '{\"status\": \"present\"}')"))
            s.commit()
        engine.dispose()
    return f"sqlite:///{target_path.as_posix()}"

def test_at_06_existing_database_migration_preserves_data(tmp_path):
    """AT-06: Existing database records and tenant ownership survive upgrade."""
    db_file = tmp_path / "existing_test.db"
    db_url = _prepare_baseline_v1_database(db_file)
    
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
    db_file = tmp_path / "reversibility_test.db"
    db_url = _prepare_baseline_v1_database(db_file)
    
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

def test_db_005_migration_documentation_consistency():
    """DB-005: Each migration documents purpose, expected data impact, locking considerations and rollback limitations."""
    versions_dir = BASE_DIR / "alembic" / "versions"
    migration_files = list(versions_dir.glob("*.py"))
    assert len(migration_files) >= 2, "Expected migration version files"

    required_sections = [
        "Purpose:",
        "Expected Data Impact:",
        "Locking Considerations:",
        "Rollback Limitations:"
    ]

    for mig_file in migration_files:
        content = mig_file.read_text(encoding="utf-8")
        for sec in required_sections:
            assert sec in content, f"Migration {mig_file.name} missing required documentation section: '{sec}' (DB-005)"

def test_db_010_backup_and_restore_drill(tmp_path):
    """DB-010: Backup and restore drill demonstrates database can be restored and core records remain readable."""
    sandbox_db = tmp_path / "sandbox_live.db"
    db_url = f"sqlite:///{sandbox_db.as_posix()}"
    cfg = run_alembic_command(["upgrade", "head"], db_url)
    command.upgrade(cfg, "head")

    engine_setup = sa.create_engine(db_url)
    with Session(engine_setup) as s:
        s.execute(sa.text("INSERT INTO tenants (id, name, created_at) VALUES (1, 'Drill Centre', '2026-01-01 00:00:00')"))
        s.execute(sa.text("INSERT INTO users (id, tenant_id, email, password_hash, role, is_active, created_at) VALUES (1, 1, 'admin@drill.edu', 'hash', 'admin', 1, '2026-01-01 00:00:00')"))
        s.execute(sa.text("INSERT INTO students (id, tenant_id, student_id, name, course_id, batch_id, created_at, updated_at) VALUES (1, 1, 'STU-01', 'Drill Student', 'JEE', 'BatchA', '2026-01-01 00:00:00', '2026-01-01 00:00:00')"))
        s.execute(sa.text("INSERT INTO import_jobs (id, tenant_id, filename, status, created_at) VALUES (1, 1, 'drill.csv', 'completed', '2026-01-01 00:00:00')"))
        s.execute(sa.text("INSERT INTO records (id, tenant_id, import_id, record_type, data_json) VALUES (1, 1, 1, 'attendance', '{\"status\":\"present\"}')"))
        s.execute(sa.text("INSERT INTO prediction_history (id, tenant_id, student_id, pass_probability, risk_level, predicted_outcome, attendance_rate, model_version, is_tentative, provenance, created_at) VALUES (1, 1, 'STU-01', 85.0, 'Safe', 'Likely Pass', 90.0, 'v2.1.0', 0, 'benchmark', '2026-01-01 00:00:00')"))
        s.commit()
    engine_setup.dispose()

    # Step 2: Record baseline counts from sandbox database
    engine_orig = sa.create_engine(f"sqlite:///{sandbox_db.as_posix()}")
    baseline_counts = {}
    with Session(engine_orig) as session:
        for tbl in ["tenants", "users", "students", "records", "prediction_history"]:
            cnt = session.scalar(sa.text(f"SELECT count(*) FROM {tbl}"))
            baseline_counts[tbl] = cnt
    engine_orig.dispose()

    assert baseline_counts["tenants"] > 0
    assert baseline_counts["users"] > 0
    assert baseline_counts["records"] > 0

    # Step 3: Execute backup procedure (snapshot)
    backup_file = tmp_path / "drill_backup_snapshot.db"
    shutil.copyfile(sandbox_db, backup_file)
    assert backup_file.exists() and backup_file.stat().st_size > 0

    # Step 4: Simulate restoration into a completely separate restored environment
    restored_db = tmp_path / "restored_production.db"
    shutil.copyfile(backup_file, restored_db)

    # Step 5: Verify restored database health, foreign-key integrity, and application API readability
    engine_restored = sa.create_engine(f"sqlite:///{restored_db.as_posix()}")
    with Session(engine_restored) as session:
        # SQLite integrity check
        integrity = session.scalar(sa.text("PRAGMA integrity_check"))
        assert integrity == "ok"

        # Foreign key integrity check (AT-06)
        fk_violations = session.execute(sa.text("PRAGMA foreign_key_check")).fetchall()
        assert len(fk_violations) == 0, f"Foreign key check violations detected: {fk_violations}"

        # Verify all table record counts match pre-backup state
        for tbl, expected_count in baseline_counts.items():
            actual_count = session.scalar(sa.text(f"SELECT count(*) FROM {tbl}"))
            assert actual_count == expected_count, f"Record count mismatch in {tbl}: expected {expected_count}, got {actual_count}"

        # Verify readability of users and tenant relationship
        users = session.execute(sa.text("SELECT id, email, tenant_id, role, is_active FROM users LIMIT 5")).fetchall()
        assert len(users) > 0
        for u in users:
            assert u.email and u.tenant_id > 0

    # Step 6: Verify actual FastAPI application API read-back against restored database (AT-07, FR-06)
    from starlette.testclient import TestClient
    from app.main import app, db_session, token_for
    from app.models import User

    restored_session_maker = sa.orm.sessionmaker(bind=engine_restored, expire_on_commit=False)
    def override_restored_db():
        with restored_session_maker() as s:
            yield s

    app.dependency_overrides[db_session] = override_restored_db
    try:
        client = TestClient(app)
        with Session(engine_restored) as s:
            user_inst = s.get(User, 1)
            token = token_for(user_inst)

        me_resp = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == "admin@drill.edu"

        stu_resp = client.get("/api/v1/students", headers={"Authorization": f"Bearer {token}"})
        assert stu_resp.status_code == 200
    finally:
        app.dependency_overrides.clear()
        engine_restored.dispose()

