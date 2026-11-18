import os
import json
import uuid
import secrets
import base64
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
import pytest
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

client = TestClient(app)

@pytest.fixture
def db():
    with Session(engine) as session:
        yield session

def create_jwt_test_user(db: Session, email: str, role: str = "faculty", tenant_id: int = 1) -> User:
    existing = db.scalars(select(User).where(User.email == email)).first()
    if existing:
        return existing
    user = User(
        tenant_id=tenant_id,
        email=email,
        password_hash=password_hash("ValidPass123!"),
        role=role,
        is_active=True,
        created_at=datetime.now(timezone.utc)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

# ==============================================================================
# AT-08: Missing/Placeholder JWT Secret Validation (FR-JWT-01, FR-JWT-02)
# ==============================================================================

def test_at_08_missing_and_placeholder_secrets_fail_safely():
    """AT-08: Production startup fails safely on missing/placeholder secret; secret never exposed."""
    # 1. Missing / None / Empty
    with pytest.raises(RuntimeError) as exc_info:
        validate_jwt_secret("", environment="production")
    assert "empty or missing" in str(exc_info.value)
    assert "" == exc_info.value.args[0].split(":")[-1].strip() or "empty" in str(exc_info.value)

    with pytest.raises(RuntimeError) as exc_info:
        validate_jwt_secret(None, environment="production")
    assert "empty or missing" in str(exc_info.value)

    # 2. Known placeholders and compromised values
    placeholders = [
        "replace-this-before-hosting",
        "replace-with-a-secure-random-64-character-secret-in-production",
        "your-secret-key-goes-here-32chars",
        "my-placeholder-secret-key-production",
        "changeme-please-update-this-key-now",
        "classpulse-super-secure-production-jwt-key-2026-deb-prasad",
    ]
    for ph in placeholders:
        with pytest.raises(RuntimeError) as exc_info:
            validate_jwt_secret(ph, environment="production")
        # Ensure secret value itself is NEVER echoed in the error message
        assert ph not in str(exc_info.value)
        assert "compromised" in str(exc_info.value) or "placeholder" in str(exc_info.value)

    # 3. Insufficient length (< 32 chars)
    short_secret = "short_secret_123"
    with pytest.raises(RuntimeError) as exc_info:
        validate_jwt_secret(short_secret, environment="production")
    assert short_secret not in str(exc_info.value)
    assert "at least 32 characters" in str(exc_info.value)

    # 4. Low entropy / repeated character pattern
    low_entropy = "A" * 64
    with pytest.raises(RuntimeError) as exc_info:
        validate_jwt_secret(low_entropy, environment="production")
    assert low_entropy not in str(exc_info.value)
    assert "entropy" in str(exc_info.value)

    # 5. Valid high-entropy secret succeeds
    valid_key = secrets.token_urlsafe(48)
    assert validate_jwt_secret(valid_key, environment="production") == valid_key

# ==============================================================================
# AT-09: JWT Secret Rotation Lifecycle (FR-JWT-05)
# ==============================================================================

def test_at_09_jwt_secret_rotation(db):
    """AT-09: Old tokens rejected after key rotation; new tokens work after re-authentication."""
    user = create_jwt_test_user(db, "rotation_user@classpulse.edu")

    # Step 1: Issue token with original key
    original_secret = SECRET.decode("utf-8") if isinstance(SECRET, bytes) else str(SECRET)
    now = datetime.now(timezone.utc)
    original_payload = {
        "sub": str(user.id),
        "uid": user.id,
        "tid": user.tenant_id,
        "email": user.email,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "jti": secrets.token_urlsafe(16),
    }
    old_token = jwt.encode(original_payload, original_secret, algorithm="HS256")

    # Step 2: Verify old token works before rotation
    decoded_before = decode_token(old_token, db=db)
    assert decoded_before["uid"] == user.id

    # Step 3: Simulate key rotation by changing active SECRET in app.main
    new_secret = secrets.token_urlsafe(48)
    import app.main
    original_app_secret = app.main.SECRET
    try:
        app.main.SECRET = new_secret.encode("utf-8")

        # Step 4: Old token MUST now be rejected (Invalid session credentials)
        with pytest.raises(Exception) as exc_info:
            app.main.decode_token(old_token, db=db)
        assert exc_info.value.status_code == 401

        # Step 5: User re-authenticates and receives new token signed with new key
        new_token = app.main.token_for(user)
        decoded_after = app.main.decode_token(new_token, db=db)
        assert decoded_after["uid"] == user.id
        assert decoded_after["sub"] == str(user.id)
    finally:
        # Restore active secret
        app.main.SECRET = original_app_secret

# ==============================================================================
# AT-10: Strict JWT Claims, Algorithms & Legacy Sunset (FR-JWT-06, FR-JWT-07)
# ==============================================================================

def test_at_10_jwt_verification_strictness(db):
    """AT-10: Wrong algorithm, missing claims, expired/revoked token rejected."""
    user = create_jwt_test_user(db, "claims_strict@classpulse.edu")
    secret_key = SECRET.decode("utf-8") if isinstance(SECRET, bytes) else str(SECRET)
    now = datetime.now(timezone.utc)

    # 1. Wrong algorithm: 'none' or 'HS512'
    base_payload = {
        "sub": str(user.id),
        "uid": user.id,
        "tid": user.tenant_id,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "jti": secrets.token_urlsafe(16),
    }
    none_token = jwt.encode(base_payload, key="", algorithm="none")
    with pytest.raises(Exception) as exc:
        decode_token(none_token, db=db)
    assert exc.value.status_code == 401

    hs512_token = jwt.encode(base_payload, key=secret_key, algorithm="HS512")
    with pytest.raises(Exception) as exc:
        decode_token(hs512_token, db=db)
    assert exc.value.status_code == 401

    # 2. Missing required claims: exp, iat, sub, uid, tid
    for req_claim in ["exp", "iat", "sub", "uid", "tid"]:
        incomplete_payload = dict(base_payload)
        del incomplete_payload[req_claim]
        inc_token = jwt.encode(incomplete_payload, secret_key, algorithm="HS256")
        with pytest.raises(Exception) as exc:
            decode_token(inc_token, db=db)
        assert exc.value.status_code == 401

    # 3. Expired token
    expired_payload = dict(base_payload)
    expired_payload["exp"] = int((now - timedelta(seconds=10)).timestamp())
    expired_payload["iat"] = int((now - timedelta(minutes=30)).timestamp())
    exp_token = jwt.encode(expired_payload, secret_key, algorithm="HS256")
    with pytest.raises(Exception) as exc:
        decode_token(exp_token, db=db)
    assert exc.value.status_code == 401
    assert "expired" in str(exc.value.detail).lower()

    # 4. Revoked token (by jti)
    revoked_jti = secrets.token_urlsafe(16)
    revoked_payload = dict(base_payload)
    revoked_payload["jti"] = revoked_jti
    db.add(RevokedToken(jti=revoked_jti, revoked_at=now, expires_at=now + timedelta(hours=1)))
    db.commit()
    rev_token = jwt.encode(revoked_payload, secret_key, algorithm="HS256")
    with pytest.raises(Exception) as exc:
        decode_token(rev_token, db=db)
    assert exc.value.status_code == 401
    assert "revoked" in str(exc.value.detail).lower()

    # 5. Token invalidated after password change
    user.password_changed_at = now + timedelta(minutes=5)
    db.commit()
    issued_earlier_token = jwt.encode(base_payload, secret_key, algorithm="HS256")
    with pytest.raises(Exception) as exc:
        decode_token(issued_earlier_token, db=db)
    assert exc.value.status_code == 401
    assert "password was changed" in str(exc.value.detail).lower()

    # Reset password_changed_at for user
    user.password_changed_at = None
    db.commit()

    # 6. Deactivated user
    user.is_active = False
    db.commit()
    active_token = jwt.encode(base_payload, secret_key, algorithm="HS256")
    with pytest.raises(Exception) as exc:
        decode_token(active_token, db=db)
    assert exc.value.status_code == 403
    assert "deactivated" in str(exc.value.detail).lower()

    # Restore active status
    user.is_active = True
    db.commit()

    # 7. Cross-tenant token (tid != user.tenant_id)
    cross_payload = dict(base_payload)
    cross_payload["tid"] = user.tenant_id + 999
    cross_token = jwt.encode(cross_payload, secret_key, algorithm="HS256")
    with pytest.raises(Exception) as exc:
        decode_token(cross_token, db=db)
    assert exc.value.status_code == 401

def test_at_10_legacy_token_sunset_and_claim_enforcement(db):
    """FR-JWT-07: Legacy tokens enforce expiration, identity claims, revocation and sunset policy."""
    user = create_jwt_test_user(db, "legacy_test_user@classpulse.edu")
    now = datetime.now(timezone.utc)
    import app.main

    # Build a valid legacy HMAC token
    legacy_payload = {
        "sub": str(user.id),
        "uid": user.id,
        "tid": user.tenant_id,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=20)).timestamp()),
    }
    raw_body = base64.urlsafe_b64encode(json.dumps(legacy_payload).encode()).decode()
    sig = hmac.new(app.main.SECRET, raw_body.encode(), hashlib.sha256).hexdigest()
    valid_legacy_token = f"{raw_body}.{sig}"

    # Verify it decodes before sunset
    decoded = app.main.decode_token(valid_legacy_token, db=db)
    assert decoded["uid"] == user.id

    # Verify expired legacy token is rejected
    exp_legacy = dict(legacy_payload)
    exp_legacy["exp"] = int((now - timedelta(minutes=5)).timestamp())
    exp_body = base64.urlsafe_b64encode(json.dumps(exp_legacy).encode()).decode()
    exp_sig = hmac.new(app.main.SECRET, exp_body.encode(), hashlib.sha256).hexdigest()
    with pytest.raises(Exception) as exc:
        app.main.decode_token(f"{exp_body}.{exp_sig}", db=db)
    assert exc.value.status_code == 401

    # Verify missing uid or tid in legacy token is rejected
    missing_id_payload = {"sub": str(user.id), "exp": int((now + timedelta(minutes=20)).timestamp())}
    mid_body = base64.urlsafe_b64encode(json.dumps(missing_id_payload).encode()).decode()
    mid_sig = hmac.new(app.main.SECRET, mid_body.encode(), hashlib.sha256).hexdigest()
    with pytest.raises(Exception) as exc:
        app.main.decode_token(f"{mid_body}.{mid_sig}", db=db)
    assert exc.value.status_code == 401

    # Verify past sunset date rejects all legacy tokens
    original_sunset = app.main.LEGACY_TOKEN_SUNSET_DATE
    try:
        app.main.LEGACY_TOKEN_SUNSET_DATE = "2020-01-01T00:00:00Z"
        with pytest.raises(Exception) as exc:
            app.main.decode_token(valid_legacy_token, db=db)
        assert exc.value.status_code == 401
        assert "sunset" in str(exc.value.detail).lower()
    finally:
        app.main.LEGACY_TOKEN_SUNSET_DATE = original_sunset

def test_sec_004_documentation_samples_rejected():
    """SEC-004: Production secret validator rejects every literal sample value shown in documentation."""
    import re
    doc_paths = ["README.md", ".env.example", "docs/deployment.md", "docs/architecture.md"]
    samples_found = set()
    
    for path in doc_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            for m in re.finditer(r'(?:JWT_SECRET_KEY|SECRET_KEY)\s*=\s*([^\r\n#\s]+)', content):
                val = m.group(1).strip().strip('"').strip("'")
                if val and val != "None":
                    samples_found.add(val)
    
    assert len(samples_found) > 0, "Expected to find documented sample keys for SEC-004 verification"
    
    for sample in samples_found:
        with pytest.raises(RuntimeError) as exc_info:
            validate_jwt_secret(sample, environment="production")
        # Ensure the secret value itself is never leaked in the exception message (SEC-002, SEC-009)
        assert sample not in str(exc_info.value)
        assert "empty" in str(exc_info.value).lower() or "placeholder" in str(exc_info.value).lower() or "compromised" in str(exc_info.value).lower() or "at least 32" in str(exc_info.value).lower()

def test_sec_010_token_revocation_replay_rejected(db):
    """SEC-010: Logout, password change, and token revocation behaviour rejects replay attempts."""
    user = create_jwt_test_user(db, "replay_user@classpulse.edu")
    token = token_for(user)

    # 1. Valid request before revocation succeeds
    res_valid = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert res_valid.status_code == 200
    assert res_valid.json()["email"] == user.email

    # 2. Extract jti and revoke the token
    payload = decode_token(token, db=db)
    jti = payload["jti"]
    db.add(RevokedToken(jti=jti, revoked_at=datetime.now(timezone.utc), expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    db.commit()

    # 3. Replay attempt using revoked token MUST be rejected with 401
    res_replay = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert res_replay.status_code == 401
    assert "revoked" in res_replay.json()["detail"].lower()

    # 4. Replay against other protected routes also rejected
    res_replay_students = client.get("/api/v1/students", headers={"Authorization": f"Bearer {token}"})
    assert res_replay_students.status_code == 401

