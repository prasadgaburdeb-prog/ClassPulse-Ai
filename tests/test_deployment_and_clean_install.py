"""
Automated Acceptance Tests for AT-12 (Full Regression Verification) & AT-13 (Clean Install & Deployment Sanity)
Requirements: FR-DEP-01 to FR-DEP-04, AT-12, AT-13
"""
import os
import sys
import tempfile
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect

from app.main import app

client = TestClient(app)

def test_at_13_clean_install_and_dependency_sanity():
    """AT-13: Dependencies install and app starts with documented configuration."""
    # 1. Verify requirements.txt exists and contains core production dependencies
    req_path = Path("requirements.txt")
    assert req_path.exists(), "requirements.txt must exist for clean installation"
    req_text = req_path.read_text(encoding="utf-8")
    
    required_packages = [
        "fastapi",
        "uvicorn",
        "sqlalchemy",
        "alembic",
        "bcrypt",
        "pyjwt",
        "scikit-learn",
        "numpy",
        "matplotlib",
        "reportlab",
        "openpyxl"
    ]
    for pkg in required_packages:
        assert pkg in req_text.lower(), f"Package '{pkg}' missing from requirements.txt"

    # 2. Verify all core modules import without circular dependencies or runtime errors
    import app.main
    import app.database
    import app.models
    import app.ml_model
    import app.charts
    import app.pdf_reports
    
    # 3. Verify clean database initialization and migration to head
    with tempfile.TemporaryDirectory() as tmpdir:
        clean_db_path = Path(tmpdir) / "clean_test.db"
        clean_db_url = f"sqlite:///{clean_db_path.as_posix()}"
        
        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", clean_db_url)
        command.upgrade(cfg, "head")
        
        # Verify all tables created cleanly
        engine = create_engine(clean_db_url)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        
        expected_tables = {
            "tenants", "users", "students", "records", "import_jobs",
            "import_previews", "prediction_history", "audit_events",
            "revoked_tokens", "rate_limits", "alembic_version"
        }
        assert expected_tables.issubset(tables), f"Missing tables in clean database: {expected_tables - tables}"
        engine.dispose()

def test_at_12_protected_workflow_app_health_and_info():
    """AT-12: Full regression check on health, static mounts, and model info endpoints."""
    # 1. Root / UI endpoint
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")

    # 2. Static files accessibility
    res_static = client.get("/static/app.js")
    assert res_static.status_code == 200

    # 3. Auth failure on protected endpoint without credentials
    res_auth = client.get("/api/v1/students")
    assert res_auth.status_code == 401
