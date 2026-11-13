"""
Unit & Integration Tests for ClassPulse AI Machine Learning Pipeline
Requirements: ML-001 to ML-030, TEST-011 to TEST-019
"""
import pytest
from app.ml_model import StudentExamPredictor, UniversalSheetAdapter

def test_model_initialization_and_metadata():
    """ML-007, ML-008, ML-011: Model training, held-out metrics, and metadata provenance."""
    predictor = StudentExamPredictor()
    predictor.train_base_model()
    
    assert predictor.is_trained is True
    assert predictor.model_version.startswith("v2.1.0")
    assert predictor.dataset_provenance == "synthetic_benchmark"
    assert predictor.is_synthetic is True
    
    # Held-out metrics verification
    assert predictor.model_accuracy > 60.0
    assert predictor.model_f1 > 60.0
    assert predictor.model_roc_auc > 60.0
    assert 0.0 <= predictor.model_brier_score <= 1.0
    assert predictor.cv_mean_accuracy > 60.0
    assert predictor.train_samples > 0
    assert predictor.test_samples > 0

def test_academic_and_financial_risk_separation():
    """ML-027, ML-028, ML-029: Complete separation of academic and financial risks."""
    predictor = StudentExamPredictor()
    predictor.train_base_model()
    
    profile_cleared = {
        "student_id": "STU-001",
        "attendance_rate": 85.0,
        "present_count": 34,
        "total_sessions": 40,
        "avg_mock_score": 78.0,
        "has_mock_records": True,
        "attendance_trend": 0.05,
        "course_id": "JEE",
        "fee_clearance_ratio": 1.0,
        "outstanding_fees": 0.0,
        "total_obligations": 50000.0
    }
    
    profile_defaulter = {
        "student_id": "STU-002",
        "attendance_rate": 85.0,
        "present_count": 34,
        "total_sessions": 40,
        "avg_mock_score": 78.0,
        "has_mock_records": True,
        "attendance_trend": 0.05,
        "course_id": "JEE",
        "fee_clearance_ratio": 0.0,
        "outstanding_fees": 50000.0,
        "total_obligations": 50000.0
    }
    
    pred_cleared = predictor.predict_student(profile_cleared)
    pred_defaulter = predictor.predict_student(profile_defaulter)
    
    # Academic pass probability and risk level must be identical!
    assert pred_cleared["pass_probability"] == pred_defaulter["pass_probability"]
    assert pred_cleared["risk_level"] == pred_defaulter["risk_level"]
    
    # Independent financial risk assessment
    fin_cleared = StudentExamPredictor.assess_financial_risk(profile_cleared)
    assert fin_cleared["financial_risk_level"] == "Clear"
    assert fin_cleared["badge_color"] == "success"
    
    fin_defaulter = StudentExamPredictor.assess_financial_risk(profile_defaulter)
    assert fin_defaulter["financial_risk_level"] == "High Financial Due"
    assert fin_defaulter["badge_color"] == "danger"

def test_missing_data_transparency_no_fabrication():
    """ML-021, ML-022, DATA-018: Missing mock exam scores flagged transparently without silent fabrication."""
    predictor = StudentExamPredictor()
    predictor.train_base_model()
    
    profile_no_exam = {
        "student_id": "STU-NO-EXAM",
        "attendance_rate": 80.0,
        "present_count": 32,
        "total_sessions": 40,
        "avg_mock_score": None,  # No exam
        "has_mock_records": False,
        "course_id": "NEET"
    }
    
    pred = predictor.predict_student(profile_no_exam)
    assert pred["data_status"] == "incomplete_missing_mock_scores"
    assert "Mock Exam Scores" in pred["missing_inputs"]
    assert any("Missing mock examination scores" in factor for factor in pred["key_factors"])

def test_feature_importances_ranking():
    """ML-009, ML-010: Feature importances calculated and ranked."""
    predictor = StudentExamPredictor()
    predictor.train_base_model()
    
    fi = predictor.get_feature_importances()
    assert len(fi) == 5
    features = [f["feature"] for f in fi]
    assert "Mock Exam Score" in features
    assert "Attendance Rate (%)" in features
    total_pct = sum(f["importance_pct"] for f in fi)
    assert round(total_pct) == 100

def test_retraining_validation_gates_and_rollback():
    """ML-015 to ML-020: Minimum sample size gate, class balance gate, and fallback."""
    predictor = StudentExamPredictor()
    predictor.train_base_model()
    
    original_version = predictor.model_version
    
    # Gate 1: Insufficient samples (< 30)
    small_dataset = [{
        "student_id": f"S{i}",
        "attendance_rate": 80.0,
        "present_count": 16,
        "avg_mock_score": 75.0,
        "has_mock_records": True,
        "actual_outcome": 1
    } for i in range(10)]
    res = predictor.retrain_from_historical_data(small_dataset)
    assert res["success"] is False
    assert "Minimum 30 records required" in res["error"]
    assert predictor.model_version == original_version
    
    # Gate 2: Imbalanced classes (all passed, 0 failed)
    imbalanced_dataset = [{
        "student_id": f"S{i}",
        "attendance_rate": 85.0,
        "present_count": 17,
        "avg_mock_score": 80.0,
        "has_mock_records": True,
        "actual_outcome": 1
    } for i in range(35)]
    res = predictor.retrain_from_historical_data(imbalanced_dataset)
    assert res["success"] is False
    assert "Both classes must have at least 5 records" in res["error"]
    assert predictor.model_version == original_version
