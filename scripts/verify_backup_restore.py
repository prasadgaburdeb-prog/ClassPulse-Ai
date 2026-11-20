"""
Database Backup & Restore Verification Drill Script
Requirements: FR-06, FR-DB-01 to FR-DB-06, AT-06, AT-07, D-03
Executes a repeatable, isolated backup and restore verification drill
against a disposable SQLite database, verifies schema, integrity, Alembic revision,
foreign keys, and executes actual FastAPI application HTTP API reads against restored data.
"""
import os
import sys
import time
import shutil
import sqlite3
import tempfile
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker
from alembic.config import Config
from alembic import command
from starlette.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.main import app, db_session, token_for
from app.models import Tenant, User, Student, ImportJob, Record, PredictionHistory, AuditEvent

def calculate_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def run_drill():
    print("=" * 70)
    print("ClassPulse AI — Database Backup & Restore Drill (FR-06 / AT-06 / AT-07)")
    print("=" * 70)

    start_time = datetime.now(timezone.utc).isoformat()
    sqlite_ver = sqlite3.sqlite_version
    print(f"Database Engine: SQLite {sqlite_ver} (Physical file snapshot)")
    
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        tmp_path = Path(tmpdir)
        source_db_path = tmp_path / "drill_source.db"
        backup_db_path = tmp_path / "drill_backup_snapshot.db"
        restored_db_path = tmp_path / "drill_restored_target.db"

        source_url = f"sqlite:///{source_db_path.as_posix()}"
        restored_url = f"sqlite:///{restored_db_path.as_posix()}"

        print(f"\n[1] Preparing isolated disposable database at: {source_db_path}")
        
        # Step 1: Migrate disposable database via Alembic
        alembic_cfg = Config(str(BASE_DIR / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
        alembic_cfg.set_main_option("sqlalchemy.url", source_url)
        command.upgrade(alembic_cfg, "head")

        # Step 2: Seed representative multi-tenant synthetic data
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
                      [{"id": 1, "tenant_id": 1, "filename": "drill_seed_t1.csv", "status": "completed", "created_at": "2026-01-01 00:00:00"},
                       {"id": 2, "tenant_id": 2, "filename": "drill_seed_t2.csv", "status": "completed", "created_at": "2026-01-01 00:00:00"}])
            s.execute(sa.text("INSERT INTO records (id, tenant_id, import_id, record_type, data_json) VALUES (:id, :tenant_id, :import_id, :record_type, :data_json)"),
                      [{"id": 1, "tenant_id": 1, "import_id": 1, "record_type": "attendance", "data_json": json.dumps({"record_type": "attendance", "student_id": "APEX-001", "student_name": "Synthetic Student 1", "course_id": "JEE", "batch_id": "Batch-A", "attendance_rate": 92.0, "classes_attended": 37, "total_classes": 40, "date": "2026-01-01"})},
                       {"id": 2, "tenant_id": 1, "import_id": 1, "record_type": "exam", "data_json": json.dumps({"record_type": "exam", "student_id": "APEX-001", "student_name": "Synthetic Student 1", "course_id": "JEE", "batch_id": "Batch-A", "score": 88.5, "max_score": 100, "date": "2026-01-02"})},
                       {"id": 3, "tenant_id": 1, "import_id": 1, "record_type": "attendance", "data_json": json.dumps({"record_type": "attendance", "student_id": "APEX-002", "student_name": "Synthetic Student 2", "course_id": "NEET", "batch_id": "Batch-B", "attendance_rate": 78.0, "classes_attended": 31, "total_classes": 40, "date": "2026-01-01"})},
                       {"id": 4, "tenant_id": 2, "import_id": 2, "record_type": "attendance", "data_json": json.dumps({"record_type": "attendance", "student_id": "HOR-001", "student_name": "Synthetic Student 3", "course_id": "Foundation", "batch_id": "Batch-C", "attendance_rate": 85.0, "classes_attended": 34, "total_classes": 40, "date": "2026-01-01"})}]
                      )
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

        # Step 4: Create backup artifact and measure duration
        print(f"\n[2] Executing backup snapshot to: {backup_db_path}")
        t_b_start = time.perf_counter()
        shutil.copyfile(source_db_path, backup_db_path)
        backup_duration_ms = round((time.perf_counter() - t_b_start) * 1000, 2)
        
        assert backup_db_path.exists() and backup_db_path.stat().st_size > 0
        backup_sha256 = calculate_sha256(backup_db_path)
        backup_size = backup_db_path.stat().st_size
        assert backup_sha256 == source_sha256, "Backup checksum mismatch!"
        print(f"   - Backup successfully created: {backup_size} bytes in {backup_duration_ms} ms")

        # Step 5: Restore into separate empty disposable target and measure duration
        print(f"\n[3] Executing restore procedure to: {restored_db_path}")
        t_r_start = time.perf_counter()
        shutil.copyfile(backup_db_path, restored_db_path)
        restore_duration_ms = round((time.perf_counter() - t_r_start) * 1000, 2)
        
        assert restored_db_path.exists() and restored_db_path.stat().st_size > 0
        restored_sha256 = calculate_sha256(restored_db_path)
        assert restored_sha256 == backup_sha256, "Restored database checksum mismatch!"
        print(f"   - Restore completed successfully into clean disposable target in {restore_duration_ms} ms.")

        # Step 6: Verify schema, revision, row counts, and foreign-key integrity
        print("\n[4] Running integrity, foreign-key and schema checks on restored database...")
        engine_restored = sa.create_engine(restored_url)
        with Session(engine_restored) as session:
            # Check 1: SQLite integrity check
            integrity = session.scalar(sa.text("PRAGMA integrity_check"))
            assert integrity == "ok", f"Integrity check failed: {integrity}"
            print("   - PRAGMA integrity_check: OK")

            # Check 2: Foreign key validation
            fk_violations = session.execute(sa.text("PRAGMA foreign_key_check")).fetchall()
            assert len(fk_violations) == 0, f"Foreign key check violations detected: {fk_violations}"
            print("   - PRAGMA foreign_key_check: OK (0 violations)")

            # Check 3: Alembic version table
            restored_rev = session.scalar(sa.text("SELECT version_num FROM alembic_version"))
            assert restored_rev == alembic_rev == "002_security_hardening", f"Alembic revision mismatch: {restored_rev}"
            print(f"   - Alembic Migration Revision: {restored_rev} (MATCH)")

            # Check 4: Row counts
            restored_counts = {}
            for tbl in tables:
                cnt = session.scalar(sa.text(f"SELECT count(*) FROM {tbl}"))
                restored_counts[tbl] = cnt
                assert cnt == baseline_counts[tbl], f"Count mismatch in {tbl}: expected {baseline_counts[tbl]}, got {cnt}"
            print(f"   - Table Row Counts: All {len(tables)} tables match baseline counts exactly.")

            # Check 5: Foreign-key relationships & multi-tenant separation
            tenant_1_students = session.scalars(sa.text("SELECT student_id FROM students WHERE tenant_id = 1")).all()
            tenant_2_students = session.scalars(sa.text("SELECT student_id FROM students WHERE tenant_id = 2")).all()
            assert len(tenant_1_students) == 2 and "APEX-001" in tenant_1_students
            assert len(tenant_2_students) == 1 and "HOR-001" in tenant_2_students
            print("   - Multi-tenant foreign-key integrity: VERIFIED (Tenant 1: 2 students, Tenant 2: 1 student)")

        # Step 7: Launch FastAPI application against restored database and execute real HTTP API reads
        print("\n[5] Launching application against restored database and verifying real HTTP API read requests...")
        restored_session_maker = sessionmaker(bind=engine_restored, expire_on_commit=False)
        
        def override_restored_db():
            db = restored_session_maker()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[db_session] = override_restored_db
        api_results = {}
        try:
            client = TestClient(app)
            with Session(engine_restored) as s:
                user_t1 = s.get(User, 1)
                user_t2 = s.get(User, 2)
                token_t1 = token_for(user_t1)
                token_t2 = token_for(user_t2)

            # API Call 1: Authenticated identity retrieval
            resp_me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token_t1}"})
            assert resp_me.status_code == 200, f"/api/v1/me failed: {resp_me.text}"
            me_data = resp_me.json()
            assert me_data["email"] == "admin@apex-drill.edu"
            assert me_data["role"] == "admin"
            api_results["/api/v1/me"] = {"status": 200, "user_email": me_data["email"], "role": me_data["role"]}
            print("   - HTTP GET /api/v1/me: 200 OK (Verified user context and tenant identity from restored DB)")

            # API Call 2: Tenant 1 student list (enforces tenant scoping)
            resp_stu = client.get("/api/v1/students", headers={"Authorization": f"Bearer {token_t1}"})
            assert resp_stu.status_code == 200, f"/api/v1/students failed: {resp_stu.text}"
            stu_data = resp_stu.json()
            retrieved_ids = [s["student_id"] for s in stu_data.get("students", [])]
            assert "APEX-001" in retrieved_ids and "APEX-002" in retrieved_ids
            assert "HOR-001" not in retrieved_ids
            api_results["/api/v1/students"] = {"status": 200, "tenant_1_students_returned": retrieved_ids}
            print(f"   - HTTP GET /api/v1/students: 200 OK (Retrieved {len(retrieved_ids)} students for Tenant 1; Tenant 2 excluded)")

            # API Call 3: Student 360 profile & prediction retrieval
            resp_profile = client.get("/api/v1/students/APEX-001", headers={"Authorization": f"Bearer {token_t1}"})
            assert resp_profile.status_code == 200, f"/api/v1/students/APEX-001 failed: {resp_profile.text}"
            profile_data = resp_profile.json()
            assert profile_data["student_id"] == "APEX-001"
            assert profile_data["course_id"] == "JEE"
            assert profile_data["current_prediction"]["pass_probability"] > 0
            api_results["/api/v1/students/APEX-001"] = {
                "status": 200,
                "student_id": profile_data["student_id"],
                "course_id": profile_data["course_id"],
                "pass_probability": profile_data["current_prediction"]["pass_probability"]
            }
            print(f"   - HTTP GET /api/v1/students/APEX-001: 200 OK (Verified 360 profile & pass prob: {profile_data['current_prediction']['pass_probability']}%)")

            # API Call 4: Cross-tenant isolation verification on restored data
            resp_cross = client.get("/api/v1/students/HOR-001", headers={"Authorization": f"Bearer {token_t1}"})
            assert resp_cross.status_code == 404, "Cross-tenant student read unexpectedly succeeded!"
            api_results["cross_tenant_read_attempt"] = {"status": 404, "isolated": True}
            print("   - HTTP GET /api/v1/students/HOR-001 (by Tenant 1 user): 404 Not Found (Cross-tenant access denied)")

        finally:
            app.dependency_overrides.clear()
            engine_restored.dispose()

        end_time = datetime.now(timezone.utc).isoformat()

        report = {
            "drill_id": "DRILL-DB-2026-11-20-01",
            "start_time": start_time,
            "end_time": end_time,
            "status": "PASSED_VERIFIED",
            "database_engine": f"SQLite {sqlite_ver} (Physical file snapshot)",
            "database_version": sqlite_ver,
            "scope_limitations": (
                "Verified physical file-level backup and restore for SQLite 3. "
                "This drill does NOT prove PostgreSQL or MySQL recovery; production RDBMS engines "
                "require engine-specific automated backup/restore verification via pg_dump/mysqldump."
            ),
            "alembic_revision": restored_rev,
            "source_db_size_bytes": source_size,
            "backup_checksum_sha256": backup_sha256,
            "restore_checksum_sha256": restored_sha256,
            "backup_duration_ms": backup_duration_ms,
            "restore_duration_ms": restore_duration_ms,
            "table_record_counts": restored_counts,
            "integrity_check": "ok",
            "foreign_key_check": "ok",
            "tenant_isolation_verified": True,
            "application_api_reads_verified": True,
            "api_endpoints_exercised": [
                "/api/v1/me",
                "/api/v1/students",
                "/api/v1/students/APEX-001"
            ],
            "api_verification_summary": api_results,
            "issues_discovered": None
        }

        report_file = BASE_DIR / "docs" / "backup_restore_drill_report.md"
        with open(report_file, "w", encoding="utf-8") as f:
            f.write("# ClassPulse AI — Database Backup & Restore Drill Report\n")
            f.write("**SRS v7.0 Requirements: FR-06, FR-DB-01 to FR-DB-06, AT-06, AT-07**\n\n")
            f.write("## 1. Drill Execution Summary\n\n")
            f.write("```json\n" + json.dumps(report, indent=2) + "\n```\n\n")
            f.write("## 2. Engine Limitations & Defensible Scope\n\n")
            f.write("- **Engine Tested:** SQLite 3 file snapshot.\n")
            f.write("- **Engine Limitations:** Recovery demonstrated on SQLite does not establish PostgreSQL or MySQL recovery readiness. Each production database engine requires an isolated drill using native export/restore tooling.\n")
            f.write("- **Application Read Verification:** Verified through FastAPI application routing, JWT authentication, and dependency-injected session to the restored database.\n")

        print(f"\n[6] Truthful Drill Report saved to: {report_file}")
        print("=" * 70)
        print("RESULT: BACKUP & RESTORE DRILL PASSED (VERIFIED ON SQLITE 3 VIA API READS)")
        print("=" * 70)

if __name__ == "__main__":
    run_drill()
