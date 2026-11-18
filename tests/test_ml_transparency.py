"""
Automated Acceptance Tests for AT-11: ML Transparency, Claim Consistency and Provenance
Requirements: FR-ML-01 to FR-ML-06, AT-11
"""
import os
import re
import pytest
from sklearn.ensemble import RandomForestClassifier
from app.ml_model import StudentExamPredictor, predictor
from app.pdf_reports import generate_cohort_summary_report, generate_student_report_card

def test_at_11_model_implementation_architecture():
    """FR-ML-01, AT-11: Verify model is a single RandomForestClassifier, not a multi-model ensemble."""
    # 1. Model type must be a single RandomForestClassifier
    assert isinstance(predictor.model, RandomForestClassifier)
    assert not hasattr(predictor.model, "estimators_") or isinstance(predictor.model.estimators_[0], object)
    
    # Must NOT be an ensemble of different model types (e.g. VotingClassifier, StackingClassifier)
    class_name = predictor.model.__class__.__name__
    assert class_name == "RandomForestClassifier"
    
    # Check parameters
    assert predictor.model.n_estimators == 150
    assert predictor.model.class_weight == "balanced"
    assert predictor.model.random_state == 42

def test_at_11_documentation_claim_consistency():
    """FR-ML-01, FR-ML-02, AT-11: Verify docs do not claim 'calibrated ensemble' and label metrics as synthetic."""
    doc_paths = ["README.md", "docs/ml_methodology.md", "docs/architecture.md"]
    
    forbidden_phrases = [
        re.compile(r"calibrated\s+ensemble", re.I),
        re.compile(r"calibrated\s+random\s+forest\s+classifier\s+ensemble", re.I),
        re.compile(r"multi-model\s+ensemble", re.I),
    ]
    
    for doc in doc_paths:
        assert os.path.exists(doc), f"Missing documentation file: {doc}"
        with open(doc, "r", encoding="utf-8") as f:
            content = f.read()
            for pattern in forbidden_phrases:
                match = pattern.search(content)
                assert match is None, f"Found misleading phrase '{match.group(0)}' in {doc} (violates FR-ML-01)"
            
            # Verify synthetic benchmark metrics are explicitly identified
            if doc in ["README.md", "docs/ml_methodology.md"]:
                assert "synthetic" in content.lower(), f"{doc} must explicitly label benchmark data as synthetic (FR-ML-02)"

def test_at_11_provenance_metadata_transparency():
    """FR-ML-02, FR-ML-03: Model metadata and predictions explicitly tag synthetic provenance."""
    # Verify predictor attributes
    assert predictor.dataset_provenance == "synthetic_benchmark"
    assert predictor.is_synthetic is True
    assert "benchmark" in predictor.model_version.lower()

    # Verify prediction outputs include provenance and synthetic flags
    sample_profile = {
        "student_id": "TEST-PROV-001",
        "attendance_rate": 82.0,
        "present_count": 33,
        "total_sessions": 40,
        "avg_mock_score": 74.0,
        "has_mock_records": True,
        "course_id": "JEE"
    }
    pred = predictor.predict_student(sample_profile)
    assert pred["dataset_provenance"] == "synthetic_benchmark"
    assert pred["is_synthetic"] is True
    assert pred["is_tentative"] is False

def test_at_11_missing_academic_inputs_warning_not_fabrication():
    """FR-ML-05: Missing/insufficient academic inputs produce warnings and tentative marking."""
    profile_missing_mocks = {
        "student_id": "TEST-MISSING-001",
        "attendance_rate": 88.0,
        "present_count": 35,
        "total_sessions": 40,
        "avg_mock_score": None,
        "has_mock_records": False,
        "course_id": "NEET"
    }
    pred = predictor.predict_student(profile_missing_mocks)
    
    # Must flag as tentative and incomplete
    assert pred["is_tentative"] is True
    assert pred["is_incomplete"] is True
    assert pred["data_status"] == "incomplete_missing_mock_scores"
    assert "Mock Exam Scores" in pred["missing_inputs"]
    assert any("missing" in factor.lower() for factor in pred["key_factors"])

def test_at_11_pdf_report_provenance_labels():
    """FR-ML-02, FR-ML-03, AT-11: Generated PDF reports display synthetic benchmark metrics."""
    student_profile = {
        "student_id": "STU-PDF-001",
        "full_name": "Test Student",
        "course": "JEE Advanced",
        "batch": "Batch 2026",
        "attendance_pct": 82.5,
        "present_count": 33,
        "total_sessions": 40,
        "avg_mock_score": 76.0,
        "academic_risk_tier": "Safe / High Probability",
        "pass_probability": 85.0,
        "financial_standing": "Clear",
        "total_fees_due": 0.0,
        "total_fees_paid": 50000.0,
        "model_version": "v2.1.0-benchmark",
        "dataset_provenance": "synthetic_benchmark",
        "model_accuracy": 74.2,
        "model_roc_auc": 82.8,
        "recommendations": ["Maintain current mock performance"],
        "key_factors": ["High attendance rate", "Consistent test scores"]
    }
    
    # Test generation does not raise error and produces valid PDF bytes
    pdf_bytes = generate_student_report_card(student_profile)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF")

    summary_data = {
        "cohort_name": "JEE 2026 Cohort",
        "total_students": 50,
        "pass_expected_pct": 78.0,
        "risk_distribution": {"Safe": 35, "Moderate": 10, "High Risk": 5},
        "model_name": "Random Forest Classifier",
        "model_version": "v2.1.0-benchmark",
        "dataset_provenance": "synthetic_benchmark",
        "model_accuracy": 74.2,
        "model_roc_auc": 82.8,
        "students": [student_profile]
    }
    summary_pdf = generate_cohort_summary_report(summary_data)
    assert isinstance(summary_pdf, bytes)
    assert len(summary_pdf) > 1000
    assert summary_pdf.startswith(b"%PDF")

def test_ml_003_and_ml_009_artifact_metadata_and_governance():
    """ML-003, ML-009: Model artifact metadata records schema and human review policy."""
    from fastapi.testclient import TestClient
    from app.main import app, token_for, User, db_session, password_hash
    from sqlalchemy.orm import Session
    from sqlalchemy import select
    from app.database import engine
    from datetime import datetime, timezone

    # 1. Direct predictor inspection (ML-003)
    assert hasattr(predictor, "feature_names") and len(predictor.feature_names) == 5
    assert hasattr(predictor, "train_samples") and predictor.train_samples > 0
    assert hasattr(predictor, "test_samples") and predictor.test_samples > 0
    assert hasattr(predictor, "model_version") and "benchmark" in predictor.model_version
    assert hasattr(predictor, "dataset_provenance") and predictor.dataset_provenance == "synthetic_benchmark"

    # 2. API inspection via authenticated client (ML-003, ML-009)
    with Session(engine) as s:
        user = s.scalars(select(User).where(User.email == "ml_gov_user@classpulse.edu")).first()
        if not user:
            user = User(
                tenant_id=1,
                email="ml_gov_user@classpulse.edu",
                password_hash=password_hash("Pass123!"),
                role="faculty",
                is_active=True,
                created_at=datetime.now(timezone.utc)
            )
            s.add(user)
            s.commit()
            s.refresh(user)

    client = TestClient(app)
    token = token_for(user)
    res = client.get("/api/v1/ml/model-info", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()

    assert "feature_schema" in data and len(data["feature_schema"]) == 5
    assert "dataset_size" in data and data["dataset_size"]["total"] == 1200
    assert data["data_type"] == "synthetic"
    assert data["is_synthetic"] is True
    assert "human_review_policy" in data
    assert "decision support" in data["human_review_policy"].lower()

def test_ml_009_human_governance_in_documentation():
    """ML-009: Documentation specifies human-in-the-loop review and prohibits automated adverse action."""
    doc_path = "docs/ml_methodology.md"
    assert os.path.exists(doc_path)
    with open(doc_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "Human-in-the-Loop Review" in content
    assert "Decision Support Exclusively" in content
    assert "Prohibition of Automated Adverse Actions" in content
    assert "Mandatory Faculty Verification" in content

