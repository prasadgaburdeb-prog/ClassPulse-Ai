"""
Database Backup & Restore Verification Drill Script
Requirements: FR-DB-01 to FR-DB-06, D-03
Executes a non-destructive, repeatable backup and restore verification drill
against an isolated disposable database environment.
"""
import os
import sys
import shutil
import tempfile
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic.config import Config
from alembic import command

BASE_DIR = Path(__file__).resolve().parent.parent

def calculate_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def run_drill():
    print("=" * 60)
    print("ClassPulse AI — Database Backup & Restore Drill (FR-DB-01 to FR-DB-06)")
    print("=" * 60)

    start_time = datetime.now(timezone.utc).isoformat()
    
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        tmp_path = Path(tmpdir)
        source_db_path = tmp_path / "drill_source.db"
        backup_db_path = tmp_path / "drill_backup_snapshot.db"
        restored_db_path = tmp_path / "drill_restored_target.db"

        source_url = f"sqlite:///{source_db_path.as_posix()}"
        restored_url = f"sqlite:///{restored_db_path.as_posix()}"

        print(f"\n[1] Preparing disposable database at: {source_db_path}")
        
        # Step 1: Migrate disposable database via Alembic
        alembic_cfg = Config(str(BASE_DIR / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
        alembic_cfg.set_main_option("sqlalchemy.url", source_url)
        command.upgrade(alembic_cfg, "head")

        # Step 2: Seed representative synthetic data
        engine_source = sa.create_engine(source_url)
        with Session(engine_source) as s:
            s.execute(sa.text("INSERT INTO tenants (id, name, created_at) VALUES (:id, :name, :created_at)"),
                      [{"id": 1, "name": "Apex Academy Drill", "created_at": "2026-01-01 00:00:00"},
                       {"id": 2, "name": "Horizon Institute Drill", "created_at": "2026-01-01 00:00:00"}])
            s.execute(sa.text("INSERT INTO users (id, tenant_id, email, password_hash, role, is_active, created_at) VALUES (:id, :tenant_id, :email, :password_hash, :role, :is_active, :created_at)"),
                      [{"id": 1, "tenant_id": 1, "email": "admin@apex-drill.edu", "password_hash": "$2b$12$e80yq...", "role": "admin", "is_active": 1, "created_at": "2026-01-01 00:00:00"},
                       {"id": 2, "tenant_id": 2, "email": "faculty@horizon-drill.edu", "password_hash": "$2b$12$e80yq...", "role": "teacher", "is_active": 1, "created_at": "2026-01-01 00:00:00"}])
            s.execute(sa.text("INSERT INTO students (id, tenant_id, student_id, name, course_id, batch_id, created_at, updated_at) VALUES (:id, :tenant_id, :student_id, :name, :course_id, :batch_id, :created_at, :updated_at)"),
                      [{"id": 1, "tenant_id": 1, "student_id": "APEX-001", "name": "Synthetic Student 1", "course_id": "JEE", "batch_id": "Batch-A", "created_at": "2026-01-01 00:00:00", "updated_at": "2026-01-01 00:00:00"},
                       {"id": 2, "tenant_id": 1, "student_id": "APEX-002", "name": "Synthetic Student 2", "course_id": "NEET", "batch_id": "Batch-B", "created_at": "2026-01-01 00:00:00", "updated_at": "2026-01-01 00:00:00"},
                       {"id": 3, "tenant_id": 2, "student_id": "HOR-001", "name": "Synthetic Student 3", "course_id": "Foundation", "batch_id": "Batch-C", "created_at": "2026-01-01 00:00:00", "updated_at": "2026-01-01 00:00:00"}])
            s.execute(sa.text("INSERT INTO import_jobs (id, tenant_id, filename, status, created_at) VALUES (:id, :tenant_id, :filename, :status, :created_at)"),
                      [{"id": 1, "tenant_id": 1, "filename": "drill_seed.csv", "status": "completed", "created_at": "2026-01-01 00:00:00"}])
            s.execute(sa.text("INSERT INTO records (id, tenant_id, import_id, record_type, data_json) VALUES (:id, :tenant_id, :import_id, :record_type, :data_json)"),
                      [{"id": 1, "tenant_id": 1, "import_id": 1, "record_type": "attendance", "data_json": '{"status":"present"}'},
                       {"id": 2, "tenant_id": 1, "import_id": 1, "record_type": "exam", "data_json": '{"score":88.5}'}])
            s.execute(sa.text("INSERT INTO prediction_history (id, tenant_id, student_id, pass_probability, risk_level, predicted_outcome, attendance_rate, model_version, is_tentative, provenance, created_at) VALUES (:id, :tenant_id, :student_id, :pass_probability, :risk_level, :predicted_outcome, :attendance_rate, :model_version, :is_tentative, :provenance, :created_at)"),
                      [{"id": 1, "tenant_id": 1, "student_id": "APEX-001", "pass_probability": 84.5, "risk_level": "Safe", "predicted_outcome": "Likely Pass", "attendance_rate": 92.0, "model_version": "v2.1.0-benchmark", "is_tentative": 0, "provenance": "synthetic_benchmark", "created_at": "2026-01-01 00:00:00"}])
            s.execute(sa.text("INSERT INTO audit_events (id, tenant_id, event, details, created_at) VALUES (:id, :tenant_id, :event, :details, :created_at)"),
                      [{"id": 1, "tenant_id": 1, "event": "drill_initialized", "details": "Representative test seed created", "created_at": "2026-01-01 00:00:00"}])
            s.commit()
        engine_source.dispose()

        # Step 3: Record baseline counts
        engine_baseline = sa.create_engine(source_url)
        baseline_counts = {}
        tables = ["tenants", "users", "students", "import_jobs", "records", "prediction_history", "audit_events"]
        with Session(engine_baseline) as session:
            for tbl in tables:
                baseline_counts[tbl] = session.scalar(sa.text(f"SELECT count(*) FROM {tbl}"))
            alembic_rev = session.scalar(sa.text("SELECT version_num FROM alembic_version"))
        engine_baseline.dispose()

        source_sha256 = calculate_sha256(source_db_path)
        source_size = source_db_path.stat().st_size
        print(f"   - Baseline Alembic Revision: {alembic_rev}")
        print(f"   - Baseline Record Counts: {baseline_counts}")
        print(f"   - Source Database Size: {source_size} bytes (SHA256: {source_sha256[:16]}...)")

        # Step 4: Create backup artifact
        print(f"\n[2] Executing backup procedure to: {backup_db_path}")
        shutil.copyfile(source_db_path, backup_db_path)
        assert backup_db_path.exists() and backup_db_path.stat().st_size > 0
        backup_sha256 = calculate_sha256(backup_db_path)
        backup_size = backup_db_path.stat().st_size
        assert backup_sha256 == source_sha256, "Backup checksum mismatch!"
        print(f"   - Backup successfully created: {backup_size} bytes")

        # Step 5: Restore into separate empty disposable target
        print(f"\n[3] Executing restore procedure to: {restored_db_path}")
        shutil.copyfile(backup_db_path, restored_db_path)
        assert restored_db_path.exists() and restored_db_path.stat().st_size > 0
        restored_sha256 = calculate_sha256(restored_db_path)
        assert restored_sha256 == backup_sha256, "Restored database checksum mismatch!"
        print("   - Restore completed successfully into clean disposable target.")

        # Step 6: Verify schema, revision, row counts, relationships, and app read access
        print("\n[4] Running integrity and verification checks on restored database...")
        engine_restored = sa.create_engine(restored_url)
        with Session(engine_restored) as session:
            # Check 1: SQLite integrity check
            integrity = session.scalar(sa.text("PRAGMA integrity_check"))
            assert integrity == "ok", f"Integrity check failed: {integrity}"
            print("   - PRAGMA integrity_check: OK")

            # Check 2: Alembic version table
            restored_rev = session.scalar(sa.text("SELECT version_num FROM alembic_version"))
            assert restored_rev == alembic_rev == "002_security_hardening", f"Alembic revision mismatch: {restored_rev}"
            print(f"   - Alembic Migration Revision: {restored_rev} (MATCH)")

            # Check 3: Row counts
            restored_counts = {}
            for tbl in tables:
                cnt = session.scalar(sa.text(f"SELECT count(*) FROM {tbl}"))
                restored_counts[tbl] = cnt
                assert cnt == baseline_counts[tbl], f"Count mismatch in {tbl}: expected {baseline_counts[tbl]}, got {cnt}"
            print(f"   - Table Row Counts: All {len(tables)} tables match baseline counts exactly.")

            # Check 4: Foreign-key relationships & multi-tenant separation
            tenant_1_students = session.scalars(sa.text("SELECT student_id FROM students WHERE tenant_id = 1")).all()
            tenant_2_students = session.scalars(sa.text("SELECT student_id FROM students WHERE tenant_id = 2")).all()
            assert len(tenant_1_students) == 2 and "APEX-001" in tenant_1_students
            assert len(tenant_2_students) == 1 and "HOR-001" in tenant_2_students
            print("   - Multi-tenant foreign-key integrity: VERIFIED (Tenant 1: 2 students, Tenant 2: 1 student)")

            # Check 5: Application-level read access
            pred_row = session.execute(sa.text("SELECT pass_probability, risk_level, model_version, provenance FROM prediction_history WHERE student_id = 'APEX-001'")).fetchone()
            assert pred_row is not None and pred_row.pass_probability == 84.5
            assert pred_row.model_version == "v2.1.0-benchmark"
            assert pred_row.provenance == "synthetic_benchmark"
            print("   - Application read access to predictions and provenance: VERIFIED")

        engine_restored.dispose()

        end_time = datetime.now(timezone.utc).isoformat()

        report = {
            "drill_id": "DRILL-DB-2026-11-18-01",
            "start_time": start_time,
            "end_time": end_time,
            "status": "PASSED_VERIFIED",
            "database_engine": "SQLite 3 (File snapshot)",
            "alembic_revision": restored_rev,
            "source_db_size_bytes": source_size,
            "backup_checksum_sha256": backup_sha256,
            "table_record_counts": restored_counts,
            "integrity_check": "ok",
            "tenant_isolation_verified": True,
            "application_reads_verified": True,
            "issues_discovered": None
        }

        report_file = BASE_DIR / "docs" / "backup_restore_drill_report.md"
        with open(report_file, "w", encoding="utf-8") as f:
            f.write("# ClassPulse AI — Database Backup & Restore Drill Report\n")
            f.write("**SRS v5.0 Deliverable D-03 | Requirements: FR-DB-01 to FR-DB-06**\n\n")
            f.write("```json\n" + json.dumps(report, indent=2) + "\n```\n")

        print(f"\n[5] Drill Report saved to: {report_file}")
        print("=" * 60)
        print("RESULT: BACKUP & RESTORE DRILL PASSED WITH 100% INTEGRITY")
        print("=" * 60)

if __name__ == "__main__":
    run_drill()
