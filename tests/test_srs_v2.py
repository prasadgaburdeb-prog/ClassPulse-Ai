import os
import json
import uuid
import secrets
import pytest
from datetime import datetime, timezone, timedelta
import jwt
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.main import (
    app,
    db_session,
    engine,
    User,
    Tenant,
    Record,
    Student,
    ImportJob,
    ImportPreviewRecord,
    RevokedToken,
    validate_jwt_secret,
    token_for,
    decode_token,
    SECRET,
    JWT_ALGORITHM,
    JWT_ISSUER,
    JWT_AUDIENCE,
    COMPROMISED_KEYS,
    password_hash,
)
from app.ml_model import UniversalSheetAdapter, StudentExamPredictor

client = TestClient(app)

@pytest.fixture
def db():
    with Session(engine) as session:
        yield session

def create_test_user(db: Session, email: str, role: str = "faculty", tenant_id: int = 1) -> User:
    existing = db.scalars(select(User).where(User.email == email)).first()
    if existing:
        return existing
    user = User(
        tenant_id=tenant_id,
        email=email,
        password_hash=password_hash("TestPassword123!"),
        role=role,
        is_active=True,
        created_at=datetime.now(timezone.utc)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

# ----------------- AT-JWT-01: Secret Validation on Startup -----------------

def test_at_jwt_01_production_startup_validation():
    # Missing / empty secret
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY is empty or missing"):
        validate_jwt_secret("", environment="production")

    # Exposed compromised secret
    for comp in COMPROMISED_KEYS:
        with pytest.raises(RuntimeError, match="known compromised key"):
            validate_jwt_secret(comp, environment="production")

    # Insecure short secret in production
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        validate_jwt_secret("short-secret-key", environment="production")

    # Valid secret in production
    valid_key = "a_very_secure_and_cryptographically_strong_random_key_1234567890"
    assert validate_jwt_secret(valid_key, environment="production") == valid_key

# ----------------- AT-JWT-02: Source Code Scanning for Hardcoded Secrets -----------------

def test_at_jwt_02_no_hardcoded_secrets_in_source():
    compromised_needle = "classpulse-super-secure-production-jwt-key-2026-deb-prasad"
    checked_files = []
    for root, dirs, files in os.walk("app"):
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                checked_files.append(path)
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    # In main.py, it should ONLY appear in COMPROMISED_KEYS blocklist, never as the live secret
                    if "RAW_SECRET = " in content:
                        assert compromised_needle not in content.split("RAW_SECRET = ")[1].split("\n")[0]
    assert len(checked_files) > 0

# ----------------- AT-JWT-03: Token Claims and Structure -----------------

def test_at_jwt_03_token_generation_claims(db):
    user = create_test_user(db, "claims_test@classpulse.edu", role="faculty", tenant_id=1)
    token = token_for(user)
    
    secret_key = SECRET.decode("utf-8") if isinstance(SECRET, bytes) else str(SECRET)
    decoded = jwt.decode(
        token,
        secret_key,
        algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER,
        audience=JWT_AUDIENCE
    )
    
    assert decoded["sub"] == str(user.id)
    assert decoded["uid"] == user.id
    assert decoded["tid"] == user.tenant_id
    assert decoded["role"] == user.role
    assert "jti" in decoded
    assert "exp" in decoded
    assert "iat" in decoded
    assert decoded["iss"] == JWT_ISSUER
    assert decoded["aud"] == JWT_AUDIENCE

# ----------------- AT-JWT-04: Malformed, Expired, Tampered Tokens -----------------

def test_at_jwt_04_tampered_and_expired_tokens(db):
    user = create_test_user(db, "tamper_test@classpulse.edu", role="faculty", tenant_id=1)
    
    # 1. Tampered payload
    valid_token = token_for(user)
    parts = valid_token.split(".")
    tampered_token = parts[0] + "." + parts[1] + "tampered." + parts[2]
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {tampered_token}"})
    assert response.status_code == 401

    # 2. Expired token
    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": str(user.id),
        "uid": user.id,
        "tid": user.tenant_id,
        "role": user.role,
        "jti": str(uuid.uuid4()),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": int((now - timedelta(hours=2)).timestamp()),
        "exp": int((now - timedelta(hours=1)).timestamp())
    }
    secret_key = SECRET.decode("utf-8") if isinstance(SECRET, bytes) else str(SECRET)
    expired_token = jwt.encode(expired_payload, secret_key, algorithm=JWT_ALGORITHM)
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert response.status_code == 401

    # 3. Malformed token string
    response = client.get("/api/v1/me", headers={"Authorization": "Bearer not-a-valid-jwt"})
    assert response.status_code == 401

# ----------------- AT-JWT-05: Algorithm Confusion Rejected -----------------

def test_at_jwt_05_algorithm_confusion_rejected(db):
    user = create_test_user(db, "alg_test@classpulse.edu", role="faculty", tenant_id=1)
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "uid": user.id,
        "tid": user.tenant_id,
        "role": user.role,
        "jti": str(uuid.uuid4()),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp())
    }
    
    # Algorithm "none"
    none_token = jwt.encode(payload, key="", algorithm="none")
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {none_token}"})
    assert response.status_code == 401

    # Algorithm HS512 (when server strictly specifies HS256)
    secret_key = SECRET.decode("utf-8") if isinstance(SECRET, bytes) else str(SECRET)
    hs512_token = jwt.encode(payload, key=secret_key, algorithm="HS512")
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {hs512_token}"})
    assert response.status_code == 401

# ----------------- AT-JWT-06: Compromised Key Rejected -----------------

def test_at_jwt_06_compromised_key_rejected(db):
    user = create_test_user(db, "compromised_test@classpulse.edu", role="faculty", tenant_id=1)
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "uid": user.id,
        "tid": user.tenant_id,
        "role": user.role,
        "jti": str(uuid.uuid4()),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp())
    }
    
    compromised_key = "classpulse-super-secure-production-jwt-key-2026-deb-prasad"
    token = jwt.encode(payload, key=compromised_key, algorithm="HS256")
    
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401

# ----------------- AT-JWT-07: Logout, Revocation & Session Invalidation -----------------

def test_at_jwt_07_token_revocation_and_invalidation(db):
    user = create_test_user(db, "revocation_test@classpulse.edu", role="faculty", tenant_id=1)
    token = token_for(user)
    
    # Verify token works initially
    resp = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    
    # 1. Logout revokes token jti
    logout_resp = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_resp.status_code == 200
    
    # 2. Subsequent call with same token fails
    after_logout_resp = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert after_logout_resp.status_code == 401
    
    # 3. New token works, but password change invalidates all existing sessions
    new_token = token_for(user)
    resp2 = client.get("/api/v1/me", headers={"Authorization": f"Bearer {new_token}"})
    assert resp2.status_code == 200
    
    # Simulate password change timestamp
    user.password_changed_at = datetime.now(timezone.utc) + timedelta(seconds=2)
    db.add(user)
    db.commit()
    
    # Old token fails due to iat < password_changed_at
    resp3 = client.get("/api/v1/me", headers={"Authorization": f"Bearer {new_token}"})
    assert resp3.status_code == 401

    # 4. Deactivation of user account
    latest_token = token_for(user)
    user.is_active = False
    db.add(user)
    db.commit()
    
    resp4 = client.get("/api/v1/me", headers={"Authorization": f"Bearer {latest_token}"})
    assert resp4.status_code == 403
    
    # Restore user
    user.is_active = True
    user.password_changed_at = None
    db.add(user)
    db.commit()

# ----------------- CSRF Protection on Mutating Requests -----------------

def test_csrf_protection_on_cookie_auth(db):
    user = create_test_user(db, "csrf_test@classpulse.edu", role="admin", tenant_id=1)
    token = token_for(user)
    
    # 1. Cookie authentication WITHOUT CSRF header on mutating request (POST) -> 403 Forbidden
    client.cookies.set("classpulse_session", token)
    client.cookies.set("classpulse_csrf", "valid-csrf-token-abc")
    
    resp = client.post("/api/v1/auth/change-password", json={"old_password": "Wrong", "new_password": "NewPassword123!"})
    assert resp.status_code == 403
    assert "CSRF" in resp.json().get("detail", "")
    
    # 2. Cookie authentication with MISMATCHED CSRF token -> 403 Forbidden
    resp = client.post(
        "/api/v1/auth/change-password",
        headers={"X-CSRF-Token": "wrong-token"},
        json={"old_password": "Wrong", "new_password": "NewPassword123!"}
    )
    assert resp.status_code == 403
    
    # 3. Cookie authentication with MATCHING CSRF token -> reaches endpoint logic (not 403)
    resp = client.post(
        "/api/v1/auth/change-password",
        headers={"X-CSRF-Token": "valid-csrf-token-abc"},
        json={"old_password": "WrongPassword", "new_password": "NewPassword123!"}
    )
    assert resp.status_code == 400
    assert "Current password is incorrect" in resp.json().get("detail", "")
    
    # Clean up cookies
    client.cookies.clear()
    
    # 4. Bearer authorization header bypasses CSRF check (API client)
    token2 = token_for(user)
    resp = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {token2}"},
        json={"old_password": "WrongPassword", "new_password": "NewPassword123!"}
    )
    assert resp.status_code == 400  # Reached application logic without 403

# ----------------- RBAC Enforcement -----------------

def test_rbac_enforcement(db):
    viewer = create_test_user(db, "viewer_rbac@classpulse.edu", role="viewer", tenant_id=1)
    faculty = create_test_user(db, "faculty_rbac@classpulse.edu", role="faculty", tenant_id=1)
    admin = create_test_user(db, "admin_rbac@classpulse.edu", role="admin", tenant_id=1)
    
    viewer_token = token_for(viewer)
    faculty_token = token_for(faculty)
    admin_token = token_for(admin)
    
    # 1. Viewer cannot retrain ML model (requires owner, admin) -> 403
    resp = client.post("/api/v1/ml/retrain", headers={"Authorization": f"Bearer {viewer_token}"})
    assert resp.status_code == 403
    
    # 2. Faculty cannot retrain ML model -> 403
    resp = client.post("/api/v1/ml/retrain", headers={"Authorization": f"Bearer {faculty_token}"})
    assert resp.status_code == 403
    
    # 3. Viewer cannot access user management (/api/v1/auth/users requires admin, owner) -> 403
    resp = client.get("/api/v1/auth/users", headers={"Authorization": f"Bearer {viewer_token}"})
    assert resp.status_code == 403

    # 4. Admin can access user management -> 200
    resp = client.get("/api/v1/auth/users", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200

# ----------------- Tenant Data Isolation -----------------

def test_tenant_data_isolation(db):
    # Ensure Tenant 1 and Tenant 2 exist
    t1 = db.get(Tenant, 1) or Tenant(id=1, name="Tenant 1")
    t2 = db.get(Tenant, 2) or Tenant(id=2, name="Tenant 2")
    db.add(t1)
    db.add(t2)
    db.commit()
    
    u1 = create_test_user(db, "user_t1@classpulse.edu", role="admin", tenant_id=1)
    u2 = create_test_user(db, "user_t2@classpulse.edu", role="admin", tenant_id=2)
    
    # Add a unique student record to Tenant 2
    unique_t2_id = f"T2_STU_{uuid.uuid4().hex[:6]}"
    # Ensure an import job exists for FK
    job2 = db.scalars(select(ImportJob).where(ImportJob.tenant_id == 2)).first()
    if not job2:
        job2 = ImportJob(tenant_id=2, filename="initial_t2.csv", status="completed")
        db.add(job2)
        db.commit()
        db.refresh(job2)
        
    s2 = Student(
        tenant_id=2,
        student_id=unique_t2_id,
        name="Tenant 2 Student",
        course_id="CS101",
        batch_id="2026"
    )
    db.add(s2)
    r2 = Record(
        tenant_id=2,
        import_id=job2.id,
        record_type="student",
        data_json=json.dumps({
            "record_type": "student",
            "student_id": unique_t2_id,
            "student_name": "Tenant 2 Student",
            "course_id": "CS101",
            "batch_id": "2026",
            "id": f"REC_{unique_t2_id}",
            "date": "2026-01-01"
        })
    )
    db.add(r2)
    db.commit()
    
    t1_token = token_for(u1)
    t2_token = token_for(u2)
    
    # Tenant 1 queries students list
    resp1 = client.get("/api/v1/students", headers={"Authorization": f"Bearer {t1_token}"})
    assert resp1.status_code == 200
    t1_student_ids = [s["student_id"] for s in resp1.json().get("students", [])]
    assert unique_t2_id not in t1_student_ids
    
    # Tenant 1 attempts to access Tenant 2 student directly
    resp_direct = client.get(f"/api/v1/students/{unique_t2_id}", headers={"Authorization": f"Bearer {t1_token}"})
    assert resp_direct.status_code == 404
    
    # Tenant 2 can access the student
    resp_t2 = client.get(f"/api/v1/students/{unique_t2_id}", headers={"Authorization": f"Bearer {t2_token}"})
    assert resp_t2.status_code == 200

# ----------------- Import Persistence & Idempotency -----------------

def test_import_preview_persistence_and_idempotency(db):
    admin = create_test_user(db, "import_test@classpulse.edu", role="admin", tenant_id=1)
    admin_token = token_for(admin)
    
    # Upload sample spreadsheet data for preview
    csv_content = "student_id,name,attendance_pct,gpa\nTEST_IMP_01,Alice Smith,92.5,3.8\nTEST_IMP_02,Bob Jones,75.0,2.9\n"
    files = {"file": ("test_students.csv", csv_content.encode("utf-8"), "text/csv")}
    
    preview_resp = client.post("/api/v1/imports/preview", headers={"Authorization": f"Bearer {admin_token}"}, files=files)
    assert preview_resp.status_code == 200
    preview_data = preview_resp.json()
    preview_id = preview_data["preview_id"]
    
    # 1. Verify preview was persisted to import_previews table
    stored_preview = db.scalars(select(ImportPreviewRecord).where(ImportPreviewRecord.preview_id == preview_id)).first()
    assert stored_preview is not None
    assert stored_preview.status == "pending"
    payload = json.loads(stored_preview.payload_json)
    assert len(payload.get("valid", [])) > 0
    assert payload.get("summary", {}).get("total_rows") == 2
    
    # 2. Confirm the import
    confirm_resp = client.post(
        f"/api/v1/imports/{preview_id}/confirm",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert confirm_resp.status_code == 200
    assert "completed" in confirm_resp.json().get("message", "").lower()
    
    # 3. Second confirmation must be idempotent
    confirm_resp_2 = client.post(
        f"/api/v1/imports/{preview_id}/confirm",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert confirm_resp_2.status_code == 200
    assert confirm_resp_2.json().get("status") == "already_processed"

# ----------------- Data Integrity: No Fabrication -----------------

def test_no_data_fabrication_in_adapter():
    # Provide flat rows without fee or attendance details
    flat_rows = [
        {"student_id": "NOFAB_01", "name": "Test Student 1", "course": "Physics"}
    ]
    records = UniversalSheetAdapter.convert_flat_to_classpulse_records(flat_rows)
    
    # Must NOT fabricate fees or attendance logs
    fee_records = [r for r in records if r.get("record_type") == "fees"]
    attendance_records = [r for r in records if r.get("record_type") == "attendance"]
    
    assert len(fee_records) == 0, "UniversalSheetAdapter fabricated fee obligations!"
    assert len(attendance_records) == 0, "UniversalSheetAdapter fabricated attendance records!"

def test_ml_provenance_and_tentative_marking():
    predictor = StudentExamPredictor()
    predictor.train_base_model()
    profile = {
        "student_id": "TENT_01",
        "name": "Tentative Profile",
        "attendance_rate": 80.0,
        "present_count": 32,
        "total_sessions": 40,
        "avg_mock_score": None,
        "has_mock_records": False,
        "course_id": "NEET"
    }
    pred = predictor.predict_student(profile)
    assert pred.get("is_tentative") is True
    assert pred.get("provenance") is not None
    assert pred.get("data_status") == "incomplete_missing_mock_scores"
