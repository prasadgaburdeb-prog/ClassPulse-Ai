"""
Acceptance Tests for Shared Rate Limiting (AT-01 to AT-03, FR-RL-01 to FR-RL-06).
"""
import uuid
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, text

from app.database import engine
from app.models import RateLimitRecord
import app.main as app_main
from app.main import check_rate_limit, login_attempts

@pytest.fixture
def db():
    with Session(engine) as session:
        yield session

def test_at_01_production_rate_limit_store_unavailable():
    """
    AT-01: When the shared persistent store fails in production,
    protected requests shall fail closed with a controlled 503 error (no silent memory fallback).
    """
    orig_env = app_main.APP_ENV
    try:
        app_main.APP_ENV = "production"
        broken_db = MagicMock(spec=Session)
        broken_db.execute.side_effect = RuntimeError("Database connection lost")
        
        test_key = f"prod_test_{uuid.uuid4().hex}"
        
        # Protected request must fail closed with 503
        with pytest.raises(HTTPException) as exc_info:
            check_rate_limit(test_key, max_attempts=5, window_seconds=60, db=broken_db)
        
        assert exc_info.value.status_code == 503
        assert "Rate limiting service temporarily unavailable" in exc_info.value.detail
        
        # Verify no silent fallback was recorded in process-local login_attempts
        assert test_key not in login_attempts
    finally:
        app_main.APP_ENV = orig_env

def test_at_02_development_store_unavailable():
    """
    AT-02: When the shared store is unavailable in development mode,
    fallback to process-local memory tracker is permitted with explicit warning.
    """
    orig_env = app_main.APP_ENV
    try:
        app_main.APP_ENV = "development"
        test_key = f"dev_fallback_{uuid.uuid4().hex}"
        
        # Execute attempts with no database session provided
        for _ in range(3):
            check_rate_limit(test_key, max_attempts=3, window_seconds=60, db=None)
            
        # 4th attempt should be blocked by memory tracker
        with pytest.raises(HTTPException) as exc_info:
            check_rate_limit(test_key, max_attempts=3, window_seconds=60, db=None)
            
        assert exc_info.value.status_code == 429
        assert "Too many failed attempts" in exc_info.value.detail
        assert test_key in login_attempts
    finally:
        app_main.APP_ENV = orig_env

def test_at_03_multi_worker_shared_rate_limit(db):
    """
    AT-03: Multi-worker rate limiting — requests across independent workers (sessions)
    share the effective limit in the persistent rate_limits table.
    """
    orig_env = app_main.APP_ENV
    try:
        app_main.APP_ENV = "development"
        shared_key = f"shared_worker_key_{uuid.uuid4().hex[:8]}"
        
        # Simulate Worker 1 (Session 1) handling 3 attempts
        with Session(engine) as worker1_db:
            for _ in range(3):
                check_rate_limit(shared_key, max_attempts=5, window_seconds=60, db=worker1_db)
        
        # Simulate Worker 2 (Session 2) handling 2 attempts (total 5)
        with Session(engine) as worker2_db:
            for _ in range(2):
                check_rate_limit(shared_key, max_attempts=5, window_seconds=60, db=worker2_db)
        
        # Simulate Worker 3 (Session 3) handling the 6th attempt -> must be blocked
        with Session(engine) as worker3_db:
            with pytest.raises(HTTPException) as exc_info:
                check_rate_limit(shared_key, max_attempts=5, window_seconds=60, db=worker3_db)
            assert exc_info.value.status_code == 429
            assert "Too many requests" in exc_info.value.detail

        # Clean up test rows
        db.execute(text("DELETE FROM rate_limits WHERE rate_key = :k"), {"k": shared_key})
        db.commit()
    finally:
        app_main.APP_ENV = orig_env

def test_fr_rl_04_privacy_conscious_keys(db):
    """
    FR-RL-04: Excessively long keys or keys with arbitrary payloads are hashed to protect privacy.
    """
    long_key = "a" * 200
    check_rate_limit(long_key, max_attempts=5, window_seconds=60, db=db)
    
    # Assert long_key itself was not stored as raw string in rate_limits
    raw_row = db.scalar(select(RateLimitRecord).where(RateLimitRecord.rate_key == long_key))
    assert raw_row is None
    
    # Clean up
    db.execute(text("DELETE FROM rate_limits WHERE rate_key != '' AND attempt_timestamp < 1"))
    db.commit()
