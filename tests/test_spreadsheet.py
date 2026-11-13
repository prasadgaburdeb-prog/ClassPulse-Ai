"""
Unit & Integration Tests for Spreadsheet Ingestion, Schema Detection & Validation
Requirements: DATA-001 to DATA-028, TEST-010
"""
import pytest
from app.ml_model import UniversalSheetAdapter, detect_column_mappings
from app.main import parse_sheet_data

def test_universal_sheet_header_detection():
    """DATA-020 to DATA-024: Robust detection of standard and generic column headers."""
    custom_headers = ["Roll No", "Student Name", "Attendance %", "Pre-Board Marks", "Total Fees", "Paid Fees"]
    
    mapping, unmapped = detect_column_mappings(custom_headers)
    assert mapping["student_id"] == "Roll No"
    assert mapping["student_name"] == "Student Name"
    assert mapping["attendance_rate"] == "Attendance %"
    assert mapping["exam_score"] == "Pre-Board Marks"
    assert mapping["fee_total"] == "Total Fees"
    assert mapping["fee_paid"] == "Paid Fees"

def test_generic_sheet_profile_extraction():
    """DATA-025: Extract normalized student profiles from generic spreadsheet rows."""
    generic_rows = [
        {"Roll No": "101", "Student Name": "Ananya", "Attendance %": "92", "Pre-Board Marks": "85", "Total Fees": "20000", "Paid Fees": "20000"},
        {"Roll No": "102", "Student Name": "Vikram", "Attendance %": "48", "Pre-Board Marks": "42", "Total Fees": "20000", "Paid Fees": "10000"}
    ]
    
    mapping, _ = detect_column_mappings(list(generic_rows[0].keys()))
    profiles, detected_cols, table_type, audit_info = UniversalSheetAdapter.convert_flat_rows_to_profiles(generic_rows, mapping)
    assert len(profiles) == 2
    
    p1 = profiles[0]
    assert "101" in p1["student_id"]
    assert p1["attendance_rate"] == 92.0
    assert p1["avg_mock_score"] == 85.0
    assert p1["fee_clearance_ratio"] == 1.0
    
    p2 = profiles[1]
    assert "102" in p2["student_id"]
    assert p2["attendance_rate"] == 48.0
    assert p2["avg_mock_score"] == 42.0
    assert p2["fee_clearance_ratio"] == 0.5

def test_duplicate_id_detection_in_sheet():
    """DATA-006: Duplicate student/record IDs in file must be flagged."""
    csv_data = (
        "record_type,id,date,student_id,course_id,batch_id,amount,status\n"
        "student,STU-1,2026-01-01,STU-1,JEE,Batch-A,0,admitted\n"
        "student,STU-1,2026-01-01,STU-1,JEE,Batch-A,0,admitted\n"
    ).encode("utf-8")
    
    valid, errors, summary = parse_sheet_data(csv_data, "students.csv")
    assert summary["duplicates"] >= 1
    assert any("duplicate" in err["issues"][0].lower() for err in errors)

def test_negative_fee_amount_validation():
    """DATA-007: Negative financial amounts rejected with validation error."""
    csv_data = (
        "record_type,id,date,student_id,course_id,batch_id,amount,status\n"
        "obligation,OB-1,2026-01-01,STU-1,JEE,Batch-A,-5000,due\n"
    ).encode("utf-8")
    
    valid, errors, summary = parse_sheet_data(csv_data, "fees.csv")
    assert len(errors) == 1
    assert "must not be negative" in errors[0]["issues"][0]
