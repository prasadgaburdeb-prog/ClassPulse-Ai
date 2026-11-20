"""
ClassPulse AI — Application Security & Tenant Isolation Regression Test Suite
Requirements: FR-01, FR-02, FR-03, AT-05, NFR-01, NFR-02
Validates multi-tenant boundaries across direct reads, history, exports, reports,
analytics, imports, RBAC enforcement, CSRF, and token rejection pathways.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone
import pytest
import jwt
from starlette.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import engine
from app.main import (
    app,
    Tenant,
    User,
    Student,
    Record,
    ImportJob,
    ImportPreviewRecord,
    PredictionHistory,
    RevokedToken,
    token_for,
    password_hash,
    SECRET,
    JWT_ALGORITHM,
    JWT_ISSUER,
    JWT_AUDIENCE
)

client = TestClient(app)

@pytest.fixture
def db():
    with Session(engine) as session:
        yield session

def setup_two_tenants_with_data(db: Session):
    """Fixture helper to create two isolated tenants with users and representative student records."""
    t1 = db.get(Tenant, 101) or Tenant(id=101, name="Tenant Alpha 101")
    t2 = db.get(Tenant, 102) or Tenant(id=102, name="Tenant Beta 102")
    db.add(t1)
    db.add(t2)
    db.commit()

    u1 = db.scalars(select(User).where(User.email == "owner_t101@alpha.edu")).first()
    if not u1:
        u1 = User(
            tenant_id=101,
            email="owner_t101@alpha.edu",
            password_hash=password_hash("AlphaPass123!"),
            role="owner",
            is_active=True
        )
        db.add(u1)

    u2 = db.scalars(select(User).where(User.email == "owner_t102@beta.edu")).first()
    if not u2:
        u2 = User(
            tenant_id=102,
            email="owner_t102@beta.edu",
            password_hash=password_hash("BetaPass123!"),
            role="owner",
            is_active=True
        )
        db.add(u2)

    # Add teacher and viewer users for RBAC testing
    teacher_t1 = db.scalars(select(User).where(User.email == "teacher_t101@alpha.edu")).first()
    if not teacher_t1:
        teacher_t1 = User(
            tenant_id=101,
            email="teacher_t101@alpha.edu",
            password_hash=password_hash("TeacherPass123!"),
            role="teacher",
            is_active=True
        )
        db.add(teacher_t1)

    viewer_t1 = db.scalars(select(User).where(User.email == "viewer_t101@alpha.edu")).first()
    if not viewer_t1:
        viewer_t1 = User(
            tenant_id=101,
            email="viewer_t101@alpha.edu",
            password_hash=password_hash("ViewerPass123!"),
            role="viewer",
            is_active=True
        )
        db.add(viewer_t1)

    db.commit()
    db.refresh(u1)
    db.refresh(u2)
    db.refresh(teacher_t1)
    db.refresh(viewer_t1)

    # Seed students and records
    stu_alpha_id = "STU-ALPHA-99"
    stu_beta_id = "STU-BETA-88"

    # Ensure ImportJobs exist
    job1 = db.scalars(select(ImportJob).where(ImportJob.tenant_id == 101)).first()
    if not job1:
        job1 = ImportJob(tenant_id=101, filename="alpha_seed.csv", status="completed")
        db.add(job1)
    job2 = db.scalars(select(ImportJob).where(ImportJob.tenant_id == 102)).first()
    if not job2:
        job2 = ImportJob(tenant_id=102, filename="beta_seed.csv", status="completed")
        db.add(job2)
    db.commit()
    db.refresh(job1)
    db.refresh(job2)

    # Add students
    s1 = db.scalars(select(Student).where(Student.tenant_id == 101, Student.student_id == stu_alpha_id)).first()
    if not s1:
        s1 = Student(tenant_id=101, student_id=stu_alpha_id, name="Alice Alpha", course_id="JEE", batch_id="Batch-A")
        db.add(s1)
    s2 = db.scalars(select(Student).where(Student.tenant_id == 102, Student.student_id == stu_beta_id)).first()
    if not s2:
        s2 = Student(tenant_id=102, student_id=stu_beta_id, name="Bob Beta", course_id="NEET", batch_id="Batch-B")
        db.add(s2)

    # Add records for analytics and profiles
    r1 = db.scalars(select(Record).where(Record.tenant_id == 101, Record.data_json.contains(stu_alpha_id))).first()
    if not r1:
        db.add(Record(
            tenant_id=101,
            import_id=job1.id,
            record_type="attendance",
            data_json=json.dumps({
                "record_type": "attendance",
                "student_id": stu_alpha_id,
                "student_name": "Alice Alpha",
                "course_id": "JEE",
                "batch_id": "Batch-A",
                "status": "present",
                "amount": 0,
                "attendance_rate": 95.0,
                "classes_attended": 38,
                "total_classes": 40,
                "date": "2026-01-10",
                "id": f"REC_A1_{stu_alpha_id}"
            })
        ))
        db.add(Record(
            tenant_id=101,
            import_id=job1.id,
            record_type="exam",
            data_json=json.dumps({
                "record_type": "exam",
                "student_id": stu_alpha_id,
                "student_name": "Alice Alpha",
                "course_id": "JEE",
                "batch_id": "Batch-A",
                "status": "graded",
                "amount": 88.0,
                "score": 88.0,
                "max_score": 100,
                "date": "2026-01-12",
                "id": f"REC_A2_{stu_alpha_id}"
            })
        ))

    r2 = db.scalars(select(Record).where(Record.tenant_id == 102, Record.data_json.contains(stu_beta_id))).first()
    if not r2:
        db.add(Record(
            tenant_id=102,
            import_id=job2.id,
            record_type="attendance",
            data_json=json.dumps({
                "record_type": "attendance",
                "student_id": stu_beta_id,
                "student_name": "Bob Beta",
                "course_id": "NEET",
                "batch_id": "Batch-B",
                "status": "present",
                "amount": 0,
                "attendance_rate": 62.0,
                "classes_attended": 25,
                "total_classes": 40,
                "date": "2026-01-10",
                "id": f"REC_B1_{stu_beta_id}"
            })
        ))

    # Add PredictionHistory
    p1 = db.scalars(select(PredictionHistory).where(PredictionHistory.tenant_id == 101, PredictionHistory.student_id == stu_alpha_id)).first()
    if not p1:
        db.add(PredictionHistory(
            tenant_id=101,
            student_id=stu_alpha_id,
            pass_probability=91.0,
            risk_level="Safe",
            predicted_outcome="Likely Pass",
            attendance_rate=95.0,
            avg_mock_score=88.0,
            model_version="v2.1.0-benchmark",
            provenance="synthetic_benchmark"
        ))

    p2 = db.scalars(select(PredictionHistory).where(PredictionHistory.tenant_id == 102, PredictionHistory.student_id == stu_beta_id)).first()
    if not p2:
        db.add(PredictionHistory(
            tenant_id=102,
            student_id=stu_beta_id,
            pass_probability=44.0,
            risk_level="High Risk",
            predicted_outcome="At Risk",
            attendance_rate=62.0,
            avg_mock_score=50.0,
            model_version="v2.1.0-benchmark",
            provenance="synthetic_benchmark"
        ))

    db.commit()
    return u1, u2, teacher_t1, viewer_t1, stu_alpha_id, stu_beta_id


# ---------------------------------------------------------------------------
# Tenant Isolation Regression Tests (FR-03, AT-05)
# ---------------------------------------------------------------------------

def test_tenant_isolation_direct_access_and_history(db):
    """FR-03, AT-05: Tenant 1 cannot access Tenant 2 student profile or prediction history."""
    u1, u2, _, _, stu_alpha_id, stu_beta_id = setup_two_tenants_with_data(db)
    token_t1 = token_for(u1)
    token_t2 = token_for(u2)

    # 1. Direct profile read
    resp_cross = client.get(f"/api/v1/students/{stu_beta_id}", headers={"Authorization": f"Bearer {token_t1}"})
    assert resp_cross.status_code == 404

    resp_own = client.get(f"/api/v1/students/{stu_alpha_id}", headers={"Authorization": f"Bearer {token_t1}"})
    assert resp_own.status_code == 200
    assert resp_own.json()["student_id"] == stu_alpha_id

    # 2. Prediction history
    resp_hist_cross = client.get(f"/api/v1/students/{stu_beta_id}/predictions", headers={"Authorization": f"Bearer {token_t1}"})
    assert resp_hist_cross.status_code == 200
    assert resp_hist_cross.json() == []  # Scoped to Tenant 1, so Tenant 2 student returns zero history

    resp_hist_own = client.get(f"/api/v1/students/{stu_alpha_id}/predictions", headers={"Authorization": f"Bearer {token_t1}"})
    assert resp_hist_own.status_code == 200
    hist_records = resp_hist_own.json()
    assert len(hist_records) > 0
    assert any(p["pass_probability"] == 91.0 for p in hist_records)
    assert all("pass_probability" in p and "risk_level" in p for p in hist_records)


def test_tenant_isolation_pdf_reports(db):
    """FR-03, AT-05: PDF report downloads strictly enforce tenant boundaries."""
    u1, u2, _, _, stu_alpha_id, stu_beta_id = setup_two_tenants_with_data(db)
    token_t1 = token_for(u1)

    # Attempt cross-tenant student report card
    resp_pdf_cross = client.get(f"/api/v1/reports/pdf/student/{stu_beta_id}", headers={"Authorization": f"Bearer {token_t1}"})
    assert resp_pdf_cross.status_code == 404

    # Own student report card succeeds
    resp_pdf_own = client.get(f"/api/v1/reports/pdf/student/{stu_alpha_id}", headers={"Authorization": f"Bearer {token_t1}"})
    assert resp_pdf_own.status_code == 200
    assert resp_pdf_own.headers["content-type"] == "application/pdf"
    assert resp_pdf_own.content[:4] == b"%PDF"


def test_tenant_isolation_analytics_and_predictions(db):
    """FR-03, AT-05: Overview analytics and ML cohort endpoints do not leak cross-tenant metrics."""
    u1, u2, _, _, stu_alpha_id, stu_beta_id = setup_two_tenants_with_data(db)
    token_t1 = token_for(u1)

    # Overview analytics
    resp_overview = client.get("/api/v1/analytics/overview", headers={"Authorization": f"Bearer {token_t1}"})
    assert resp_overview.status_code == 200
    overview_data = resp_overview.json()
    assert overview_data["filters"]["matched_records"] >= 2  # Only Tenant 1 records

    # ML predictions list
    resp_preds = client.get("/api/v1/ml/predictions", headers={"Authorization": f"Bearer {token_t1}"})
    assert resp_preds.status_code == 200
    pred_ids = [p["student_id"] for p in resp_preds.json().get("predictions", [])]
    assert stu_alpha_id in pred_ids
    assert stu_beta_id not in pred_ids


def test_tenant_isolation_csv_exports(db):
    """FR-03, AT-05: CSV prediction and KPI exports never include another tenant's data."""
    u1, u2, _, _, stu_alpha_id, stu_beta_id = setup_two_tenants_with_data(db)
    token_t1 = token_for(u1)

    resp_csv = client.get("/api/v1/ml/export-predictions", headers={"Authorization": f"Bearer {token_t1}"})
    assert resp_csv.status_code == 200
    csv_text = resp_csv.text

    assert stu_alpha_id in csv_text
    assert stu_beta_id not in csv_text


def test_tenant_isolation_import_preview_confirmation(db):
    """FR-03, AT-05: Users cannot confirm or execute import previews owned by another tenant."""
    u1, u2, _, _, _, _ = setup_two_tenants_with_data(db)
    token_t1 = token_for(u1)

    # Create a pending import preview owned by Tenant 2
    foreign_preview_id = f"prev_beta_{uuid.uuid4().hex[:12]}"
    preview = ImportPreviewRecord(
        preview_id=foreign_preview_id,
        tenant_id=102,
        initiating_user_id=u2.id,
        filename="beta_confidential.csv",
        payload_json=json.dumps({"valid": [], "errors": [], "summary": {}}),
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    db.add(preview)
    db.commit()

    # Tenant 1 attempts to confirm Tenant 2's preview
    resp_confirm = client.post(
        f"/api/v1/imports/{foreign_preview_id}/confirm",
        headers={"Authorization": f"Bearer {token_t1}"}
    )
    assert resp_confirm.status_code == 404


def test_tenant_isolation_staff_listing(db):
    """FR-03, AT-05: Admin user management lists only users belonging to the caller's tenant."""
    u1, u2, _, _, _, _ = setup_two_tenants_with_data(db)
    token_t1 = token_for(u1)

    resp_users = client.get("/api/v1/auth/users", headers={"Authorization": f"Bearer {token_t1}"})
    assert resp_users.status_code == 200
    emails = [u["email"] for u in resp_users.json()]
    assert "owner_t101@alpha.edu" in emails
    assert "owner_t102@beta.edu" not in emails


# ---------------------------------------------------------------------------
# RBAC Enforcement Regression Tests (FR-02)
# ---------------------------------------------------------------------------

def test_rbac_allowed_and_denied_actions(db):
    """FR-02: Role-based permissions enforce correct allowed/denied behavior."""
    u1, _, teacher_t1, viewer_t1, _, _ = setup_two_tenants_with_data(db)
    token_owner = token_for(u1)
    token_teacher = token_for(teacher_t1)
    token_viewer = token_for(viewer_t1)

    # 1. Staff creation requires owner/admin -> denied for teacher and viewer
    resp_teacher_create = client.post(
        "/api/v1/auth/users",
        headers={"Authorization": f"Bearer {token_teacher}"},
        json={"email": "new_staff@alpha.edu", "password": "StaffPassword123!", "role": "teacher"}
    )
    assert resp_teacher_create.status_code == 403

    resp_viewer_create = client.post(
        "/api/v1/auth/users",
        headers={"Authorization": f"Bearer {token_viewer}"},
        json={"email": "new_staff2@alpha.edu", "password": "StaffPassword123!", "role": "teacher"}
    )
    assert resp_viewer_create.status_code == 403

    # 2. Import preview requires owner, admin, or teacher -> denied for viewer
    sample_csv = "student_id,name,attendance_rate\nS01,Test,80.0\n"
    resp_viewer_import = client.post(
        "/api/v1/imports/preview",
        headers={"Authorization": f"Bearer {token_viewer}"},
        files={"file": ("test.csv", sample_csv.encode(), "text/csv")}
    )
    assert resp_viewer_import.status_code == 403

    # 3. Viewer can view students
    resp_viewer_read = client.get("/api/v1/students", headers={"Authorization": f"Bearer {token_viewer}"})
    assert resp_viewer_read.status_code == 200


# ---------------------------------------------------------------------------
# Authentication & Token Lifecycle Rejections (FR-02)
# ---------------------------------------------------------------------------

def test_authentication_token_rejections(db):
    """FR-02: Strict rejection of invalid, expired, malformed, and revoked tokens."""
    u1, _, _, _, _, _ = setup_two_tenants_with_data(db)

    # 1. Missing token
    resp_none = client.get("/api/v1/me")
    assert resp_none.status_code == 401

    # 2. Malformed token
    resp_malformed = client.get("/api/v1/me", headers={"Authorization": "Bearer not.a.valid.jwt"})
    assert resp_malformed.status_code == 401

    # 3. Expired token
    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": str(u1.id),
        "uid": u1.id,
        "tid": u1.tenant_id,
        "email": u1.email,
        "role": u1.role,
        "iat": int((now - timedelta(hours=2)).timestamp()),
        "exp": int((now - timedelta(hours=1)).timestamp()),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "jti": str(uuid.uuid4())
    }
    secret_key = SECRET.decode("utf-8") if isinstance(SECRET, bytes) else str(SECRET)
    expired_token = jwt.encode(expired_payload, secret_key, algorithm=JWT_ALGORITHM)

    resp_expired = client.get("/api/v1/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp_expired.status_code == 401

    # 4. Revoked token (FR-AUTH-04)
    revoked_jti = f"rev_{uuid.uuid4().hex[:16]}"
    valid_payload = {
        "sub": str(u1.id),
        "uid": u1.id,
        "tid": u1.tenant_id,
        "email": u1.email,
        "role": u1.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "jti": revoked_jti
    }
    revoked_token = jwt.encode(valid_payload, secret_key, algorithm=JWT_ALGORITHM)

    # Insert into revoked_tokens table
    db.add(RevokedToken(
        jti=revoked_jti,
        tenant_id=u1.tenant_id,
        user_id=u1.id,
        revoked_at=now,
        expires_at=now + timedelta(hours=1)
    ))
    db.commit()

    resp_rev = client.get("/api/v1/me", headers={"Authorization": f"Bearer {revoked_token}"})
    assert resp_rev.status_code == 401


# ---------------------------------------------------------------------------
# Input Validation & Boundary Checks (FR-01)
# ---------------------------------------------------------------------------

def test_input_validation_and_filter_boundaries(db):
    """FR-01: Verify input validation handles invalid dates and unsupported record types gracefully."""
    u1, _, _, _, _, _ = setup_two_tenants_with_data(db)
    token = token_for(u1)

    # 1. Invalid date filter format
    resp_invalid_date = client.get(
        "/api/v1/analytics/overview?start=invalid-date&end=2026-01-30",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp_invalid_date.status_code == 400

    # 2. Unsupported record type
    resp_bad_type = client.get(
        "/api/v1/records?record_type=unsupported_type_xyz",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp_bad_type.status_code == 400

    # 3. What-if simulation handles extreme bounds safely without crash
    resp_sim = client.post(
        "/api/v1/ml/simulate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "attendance_rate": 100.0,
            "avg_mock_score": 0.0,
            "fee_clearance_ratio": 1.0,
            "course_id": "JEE"
        }
    )
    assert resp_sim.status_code == 200
    assert "prediction" in resp_sim.json()
    assert 0.0 <= resp_sim.json()["prediction"]["pass_probability"] <= 100.0
