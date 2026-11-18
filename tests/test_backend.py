"""
Unit & Integration Tests for ClassPulse AI Backend, Auth, RBAC & Multi-Tenancy
Requirements: SEC-001 to SEC-016, DB-001 to DB-009, FEAT-001 to FEAT-020, TEST-001 to TEST-010
"""
import pytest
import json
import uuid
from fastapi.testclient import TestClient
from app.main import (
    app,
    password_hash,
    verify_password,
    token_for,
    decode_token,
    User,
    Tenant,
    Student,
    Record,
    ImportJob,
    SessionLocal,
    sync_students_from_records
)
from app.pdf_reports import generate_student_report_card, generate_cohort_summary_report

def test_password_hashing_and_verification():
    """SEC-001: Passwords hashed with bcrypt and properly verified."""
    raw_pwd = "SecurePassword123!"
    hashed = password_hash(raw_pwd)
    
    assert hashed != raw_pwd
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
    assert verify_password(raw_pwd, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False

def test_jwt_token_generation_and_claims():
    """SEC-003, SEC-004: JWT contains required tenant, user, role claims and validates."""
    dummy_user = User(
        id=999,
        tenant_id=42,
        email="test_jwt@classpulse.ai",
        password_hash="dummy_hash",
        full_name="JWT Tester",
        role="Admin"
    )
    
    token = token_for(dummy_user)
    assert isinstance(token, str)
    assert len(token) > 20
    
    payload = decode_token(token)
    assert payload["uid"] == 999
    assert payload["tid"] == 42
    assert payload["email"] == "test_jwt@classpulse.ai"
    assert payload["role"] == "Admin"
    assert "exp" in payload

def test_pdf_report_card_generation():
    """FEAT-013 to FEAT-018: Official student PDF report card generates with correct size and content."""
    student_profile = {
        "student": {
            "student_id": "STU-9901",
            "name": "Arjun Sharma",
            "course_id": "JEE-Advanced",
            "batch_id": "Batch-A"
        },
        "attendance_summary": {
            "attendance_rate": 88.5,
            "present_count": 38,
            "total_sessions": 43
        },
        "mock_exams": [
            {"date": "2026-02-15", "score": 82.0}
        ],
        "financial_standing": {
            "total_obligations": 45000.0,
            "total_paid": 45000.0,
            "outstanding_fees": 0.0,
            "clearance_pct": 100.0,
            "fee_status": "Paid in Full",
            "financial_risk_level": "Clear"
        },
        "latest_prediction": {
            "pass_probability": 86.4,
            "risk_level": "Safe",
            "predicted_outcome": "Likely Pass",
            "factors": ["Strong mock exam performance (82.0/100)", "Consistent attendance regularity (88.5%)"]
        }
    }
    
    pdf_bytes = generate_student_report_card(
        student_profile=student_profile,
        centre_name="Apex IIT Academy"
    )
    
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 2000
    assert pdf_bytes.startswith(b"%PDF")

def test_cohort_summary_pdf_generation():
    """FEAT-020: Executive cohort PDF summary generates properly."""
    summary_data = {
        "metrics": {
            "admissions": 50,
            "attendance_rate": 81.2,
            "avg_mock_score": 72.4,
            "fee_collected": 1500000.0,
            "outstanding_fees": 120000.0
        },
        "summary": {
            "total_students": 50,
            "avg_pass_probability": 76.5,
            "likely_to_pass": 35,
            "borderline": 10,
            "high_risk": 5,
            "model_version": "v2.1.0-benchmark"
        },
        "predictions": [
            {"student_id": "STU-001", "course_id": "JEE", "batch_id": "A", "attendance_rate": 45.0, "avg_mock_score": 38.0, "pass_probability": 32.0, "risk_level": "High Risk"}
        ]
    }
    
    pdf_bytes = generate_cohort_summary_report(
        summary_data=summary_data,
        centre_name="Apex IIT Academy"
    )
    
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 2000
    assert pdf_bytes.startswith(b"%PDF")

def test_reg_003_student_lifecycle_crud():
    """REG-003: Student lifecycle operations — creation/sync, profile lookup, directory listing, and cleanup."""
    client = TestClient(app)
    db = SessionLocal()
    try:
        # Create an isolated temporary tenant
        unique_suffix = uuid.uuid4().hex[:8]
        tenant = Tenant(name=f"CRUD Test Institution {unique_suffix}")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        # Create admin user for this tenant
        user = User(
            tenant_id=tenant.id,
            email=f"crud_admin_{unique_suffix}@classpulse.ai",
            password_hash=password_hash("AdminPass123!"),
            full_name="CRUD Admin",
            role="admin",
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        auth_header = {"Authorization": f"Bearer {token_for(user)}"}

        # 1. Initially student directory is empty for this tenant
        res_empty = client.get("/api/v1/students", headers=auth_header)
        assert res_empty.status_code == 200
        assert res_empty.json()["total_students"] == 0

        # 2. Add an import job and student record
        job = ImportJob(tenant_id=tenant.id, filename="student_crud_test.csv", status="completed")
        db.add(job)
        db.commit()
        db.refresh(job)

        stu_id = f"STU-CRUD-{unique_suffix}"
        rec = Record(
            tenant_id=tenant.id,
            import_id=job.id,
            record_type="student",
            data_json=json.dumps({
                "student_id": stu_id,
                "name": "Priya Sharma",
                "course_id": "NEET-Prep",
                "batch_id": "Batch-2026",
                "attendance_rate": 92.5,
                "avg_mock_score": 88.0,
                "total_obligations": 30000.0,
                "total_paid": 30000.0
            })
        )
        db.add(rec)
        db.commit()

        # 3. Listing students reflects the synced record
        res_list = client.get("/api/v1/students", headers=auth_header)
        assert res_list.status_code == 200
        data = res_list.json()
        assert data["total_students"] == 1
        assert data["students"][0]["student_id"] == stu_id

        # 4. Search filter by query string
        res_search = client.get(f"/api/v1/students?q={stu_id}", headers=auth_header)
        assert res_search.status_code == 200
        assert len(res_search.json()["students"]) == 1

        res_miss = client.get("/api/v1/students?q=NON_EXISTENT_ID", headers=auth_header)
        assert res_miss.status_code == 200
        assert len(res_miss.json()["students"]) == 0

        # 5. Fetch full 360-degree profile
        res_profile = client.get(f"/api/v1/students/{stu_id}", headers=auth_header)
        assert res_profile.status_code == 200
        prof_data = res_profile.json()
        assert prof_data["student_id"] == stu_id
        assert prof_data["course_id"] == "NEET-Prep"
        assert prof_data["batch_id"] == "Batch-2026"
        assert "academic_metrics" in prof_data
        assert "current_prediction" in prof_data

        # 6. Delete centre data (CRUD cleanup / account data wipe)
        res_del = client.delete("/api/v1/account/data", headers=auth_header)
        assert res_del.status_code == 200

        # 7. Verify directory is empty again
        res_after = client.get("/api/v1/students", headers=auth_header)
        assert res_after.status_code == 200
        assert res_after.json()["total_students"] == 0

    finally:
        # Final safety cleanup of this test tenant
        db.query(Record).filter(Record.tenant_id == tenant.id).delete()
        db.query(Student).filter(Student.tenant_id == tenant.id).delete()
        db.query(ImportJob).filter(ImportJob.tenant_id == tenant.id).delete()
        db.query(User).filter(User.tenant_id == tenant.id).delete()
        db.query(Tenant).filter(Tenant.id == tenant.id).delete()
        db.commit()
        db.close()

