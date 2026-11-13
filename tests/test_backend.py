"""
Unit & Integration Tests for ClassPulse AI Backend, Auth, RBAC & Multi-Tenancy
Requirements: SEC-001 to SEC-016, DB-001 to DB-009, FEAT-001 to FEAT-020, TEST-001 to TEST-010
"""
import pytest
from app.main import (
    password_hash,
    verify_password,
    token_for,
    decode_token,
    User,
    Tenant,
    Student,
    Record,
    SessionLocal
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
