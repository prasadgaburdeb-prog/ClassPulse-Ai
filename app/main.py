import base64
import csv
import hashlib
import hmac
import io
import json
import logging
import math
import os
import secrets
import shutil
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional

import bcrypt
import jwt
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import openpyxl
from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint, create_engine, select, func, inspect, text
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from app.ml_model import predictor, UniversalSheetAdapter
from app.charts import (
    generate_all_charts,
    generate_master_graph,
    generate_small_graph,
    SMALL_GRAPH_DISPATCHER
)
from app.pdf_reports import (
    generate_student_report_card,
    generate_cohort_summary_report
)

logger = logging.getLogger("classpulse")
BASE_DIR = Path(__file__).resolve().parent.parent

def load_local_env() -> None:
    """Load simple KEY=value pairs from the project .env without adding a runtime dependency."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists(): return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_local_env()

APP_ENV = os.getenv("APP_ENV", "development").lower()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./classpulse.db")
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "15")) * 1024 * 1024

COMPROMISED_KEYS = {
    "classpulse-super-secure-production-jwt-key-2026-deb-prasad",
    "replace-this-before-hosting",
    "replace-with-a-secure-random-64-character-secret-in-production",
    "secret",
    "changeme",
    "test",
    "password"
}

RAW_SECRET = os.getenv("JWT_SECRET_KEY") or os.getenv("SECRET_KEY")

def validate_jwt_secret(secret_val: Optional[str], environment: str = "production") -> str:
    """Validate JWT secret meets minimum security requirements (SEC-JWT-01, SEC-JWT-03, AT-JWT-01)."""
    val = (secret_val or "").strip()
    if environment == "production":
        if not val:
            raise RuntimeError("FATAL (SEC-JWT-03): JWT_SECRET_KEY is empty or missing.")
        if val in COMPROMISED_KEYS:
            raise RuntimeError("FATAL (SEC-JWT-03): JWT_SECRET_KEY is a known compromised key.")
        if len(val) < 32:
            raise RuntimeError("FATAL (SEC-JWT-03): JWT_SECRET_KEY must be at least 32 characters.")
    return val

if APP_ENV == "production":
    validated = validate_jwt_secret(RAW_SECRET, environment="production")
    SECRET = validated.encode("utf-8")
else:
    if not RAW_SECRET or RAW_SECRET.strip() in COMPROMISED_KEYS:
        ephemeral_key = secrets.token_urlsafe(64)
        SECRET = ephemeral_key.encode("utf-8")
        logger.warning("SEC-JWT-02: No secure JWT_SECRET_KEY configured; generated ephemeral runtime key.")
    else:
        SECRET = RAW_SECRET.strip().encode("utf-8")

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ISSUER = os.getenv("JWT_ISSUER", "classpulse-ai")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "classpulse-client")
ACCESS_TOKEN_TTL_MINUTES = int(os.getenv("ACCESS_TOKEN_TTL_MINUTES", "30"))

COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax").lower()

raw_origins = os.getenv("CORS_ALLOWED_ORIGINS") or os.getenv("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [origin.strip() for origin in raw_origins.split(",") if origin.strip() and origin.strip() != "*"]

engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs = {"connect_args": {"check_same_thread": False}}
else:
    engine_kwargs = {
        "pool_pre_ping": True,
        "pool_recycle": 3600,
        "pool_size": 10,
        "max_overflow": 20
    }

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


# ----------------- Database Schema Entities (DB-001 to DB-007) -----------------

class Base(DeclarativeBase): pass

class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(191), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(30), default="owner")  # owner, admin, teacher, viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class Student(Base):
    """Normalized student record entity within tenant scope (DB-001, DB-002, DATA-04)."""
    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint("tenant_id", "student_id", name="uq_tenant_student_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    student_id: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(150), default="")
    course_id: Mapped[str] = mapped_column(String(80), default="General")
    batch_id: Mapped[str] = mapped_column(String(80), default="Standard")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class ImportJob(Base):
    __tablename__ = "import_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    initiating_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(30))
    accepted_rows: Mapped[int] = mapped_column(Integer, default=0)
    rejected_rows: Mapped[int] = mapped_column(Integer, default=0)
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class ImportPreviewRecord(Base):
    """Persisted import preview state across workers and restarts (IMP-05, IMP-06)."""
    __tablename__ = "import_previews"
    id: Mapped[int] = mapped_column(primary_key=True)
    preview_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    initiating_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String(255))
    payload_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending, completed, expired
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime)

class RevokedToken(Base):
    """Token revocation tracking for logout and credential invalidation (FR-AUTH-04, SEC-TOK-05)."""
    __tablename__ = "revoked_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    revoked_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime)

class RateLimitRecord(Base):
    """Persistent shared rate limiting across multi-worker deployments (FR-AUTH-06, SEC-RATE-01)."""
    __tablename__ = "rate_limits"
    id: Mapped[int] = mapped_column(primary_key=True)
    rate_key: Mapped[str] = mapped_column(String(120), index=True)
    attempt_timestamp: Mapped[float] = mapped_column(Float, index=True)

class Record(Base):
    __tablename__ = "records"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("import_jobs.id"), index=True)
    record_type: Mapped[str] = mapped_column(String(30), index=True)
    data_json: Mapped[str] = mapped_column(Text)

class PredictionHistory(Base):
    """Maintains snapshot of prediction results over time (DB-006, FEAT-007 to FEAT-012, FR-STU-03)."""
    __tablename__ = "prediction_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    student_id: Mapped[str] = mapped_column(String(120), index=True)
    pass_probability: Mapped[float] = mapped_column(Float)
    risk_level: Mapped[str] = mapped_column(String(50))
    predicted_outcome: Mapped[str] = mapped_column(String(50))
    avg_mock_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    attendance_rate: Mapped[float] = mapped_column(Float)
    financial_risk_level: Mapped[str] = mapped_column(String(50), default="Clear")
    model_version: Mapped[str] = mapped_column(String(50), default="v2.1.0-benchmark")
    factors_json: Mapped[str] = mapped_column(Text, default="[]")
    is_tentative: Mapped[bool] = mapped_column(Boolean, default=False)
    provenance: Mapped[str] = mapped_column(String(100), default="benchmark")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    event: Mapped[str] = mapped_column(String(80))
    target: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="success")
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

# Create schema tables if not exist (DB-008, DB-009)
Base.metadata.create_all(engine)

def ensure_database_migrations():
    """Lightweight automatic schema migration for SQLite / MySQL existing tables."""
    try:
        inspector = inspect(engine)
        tbls = inspector.get_table_names()
        with engine.connect() as conn:
            if "users" in tbls:
                user_cols = {c["name"] for c in inspector.get_columns("users")}
                for col_name, col_def in [
                    ("full_name", "VARCHAR(255) DEFAULT ''"),
                    ("is_active", "BOOLEAN DEFAULT 1"),
                    ("created_at", "DATETIME DEFAULT '2026-01-01 00:00:00'"),
                    ("last_login_at", "DATETIME DEFAULT NULL"),
                    ("password_changed_at", "DATETIME DEFAULT NULL")
                ]:
                    if col_name not in user_cols:
                        conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}"))
            if "tenants" in tbls:
                tenant_cols = {c["name"] for c in inspector.get_columns("tenants")}
                if "created_at" not in tenant_cols:
                    conn.execute(text("ALTER TABLE tenants ADD COLUMN created_at DATETIME DEFAULT '2026-01-01 00:00:00'"))
            if "import_jobs" in tbls:
                job_cols = {c["name"] for c in inspector.get_columns("import_jobs")}
                if "initiating_user_id" not in job_cols:
                    conn.execute(text("ALTER TABLE import_jobs ADD COLUMN initiating_user_id INTEGER DEFAULT NULL"))
                if "file_hash" not in job_cols:
                    conn.execute(text("ALTER TABLE import_jobs ADD COLUMN file_hash VARCHAR(64) DEFAULT NULL"))
            if "prediction_history" in tbls:
                pred_cols = {c["name"] for c in inspector.get_columns("prediction_history")}
                if "is_tentative" not in pred_cols:
                    conn.execute(text("ALTER TABLE prediction_history ADD COLUMN is_tentative BOOLEAN DEFAULT 0"))
                if "provenance" not in pred_cols:
                    conn.execute(text("ALTER TABLE prediction_history ADD COLUMN provenance VARCHAR(100) DEFAULT 'benchmark'"))
            if "audit_events" in tbls:
                ae_cols = {c["name"] for c in inspector.get_columns("audit_events")}
                if "actor_id" not in ae_cols:
                    conn.execute(text("ALTER TABLE audit_events ADD COLUMN actor_id INTEGER DEFAULT NULL"))
                if "target" not in ae_cols:
                    conn.execute(text("ALTER TABLE audit_events ADD COLUMN target VARCHAR(120) DEFAULT NULL"))
                if "status" not in ae_cols:
                    conn.execute(text("ALTER TABLE audit_events ADD COLUMN status VARCHAR(30) DEFAULT 'success'"))
                if "details" not in ae_cols:
                    conn.execute(text("ALTER TABLE audit_events ADD COLUMN details TEXT DEFAULT NULL"))
            if "students" in tbls:
                try:
                    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_student_id ON students (tenant_id, student_id)"))
                except Exception:
                    pass
            conn.commit()
    except Exception as e:
        logger.warning(f"Auto-migration notice: {e}")

ensure_database_migrations()

app = FastAPI(
    title="ClassPulse Analytics & Universal AI Exam Predictor",
    version="2.1.0",
    description="Coaching-centre intelligence platform with Scikit-learn AI pass prediction & Matplotlib reporting."
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.method} {request.url.path}: {exc}")
    if APP_ENV == "production":
        return JSONResponse(status_code=500, content={"detail": "An internal server error occurred."})
    return JSONResponse(status_code=500, content={"detail": f"Internal server error: {str(exc)}"})

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "PUT", "PATCH"],
        allow_headers=["Content-Type", "Authorization", "X-Requested-With", "X-CSRF-Token"]
    )

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Enforces no-cache for static UI updates and strict security response headers (SEC-HEAD-01)."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none';"
    )
    return response

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Shared sliding window rate limiter (SEC-008, SEC-RATE-01, FR-AUTH-06)
login_attempts: dict[str, list[float]] = {}

def check_rate_limit(key: str, max_attempts: int = 15, window_seconds: int = 600, db: Optional[Session] = None):
    now = datetime.now(timezone.utc).timestamp()
    cutoff = now - window_seconds
    if db is not None:
        try:
            db.execute(text("DELETE FROM rate_limits WHERE rate_key = :k AND attempt_timestamp < :c"), {"k": key, "c": cutoff})
            count = db.scalar(text("SELECT count(*) FROM rate_limits WHERE rate_key = :k"), {"k": key}) or 0
            if count >= max_attempts:
                wait_min = max(1, int(window_seconds // 60))
                raise HTTPException(429, f"Too many requests. Please try again after {wait_min} minutes (SEC-RATE-01).")
            db.add(RateLimitRecord(rate_key=key, attempt_timestamp=now))
            db.commit()
            return
        except HTTPException:
            raise
        except Exception:
            pass

    attempts = login_attempts.get(key, [])
    attempts = [t for t in attempts if now - t < window_seconds]
    login_attempts[key] = attempts
    if len(attempts) >= max_attempts:
        raise HTTPException(429, f"Too many failed attempts. Please try again after {int((window_seconds - (now - attempts[0])) // 60) + 1} minutes (SEC-008).")
    attempts.append(now)

def db_session():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# ----------------- Security, Password & JWT Engine (SEC-001 to SEC-016) -----------------

def password_hash(value: str) -> str:
    """Hash password using industry-standard bcrypt with automatic salt (SEC-001)."""
    return bcrypt.hashpw(value.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

def verify_password(value: str, stored: str) -> bool:
    """Verify password using bcrypt, with backwards-compatibility for legacy PBKDF2 (SEC-001)."""
    if not stored:
        return False
    try:
        if stored.startswith("$2b$") or stored.startswith("$2a$"):
            return bcrypt.checkpw(value.encode("utf-8"), stored.encode("utf-8"))
        raw = base64.b64decode(stored)
        return hmac.compare_digest(raw[16:], hashlib.pbkdf2_hmac("sha256", value.encode("utf-8"), raw[:16], 300_000))
    except Exception:
        return False

def token_for(user: User) -> str:
    """Generate standard signed JSON Web Token (JWT) with user, role, tenant claims & jti (SEC-003, FR-AUTH-03)."""
    now = datetime.now(timezone.utc)
    jti = secrets.token_urlsafe(16)
    payload = {
        "sub": str(user.id),
        "uid": user.id,
        "tid": user.tenant_id,
        "email": user.email,
        "role": user.role,
        "name": getattr(user, "full_name", "") or "",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES)).timestamp()),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "jti": jti
    }
    secret_key = SECRET.decode("utf-8") if isinstance(SECRET, bytes) else str(SECRET)
    return jwt.encode(payload, secret_key, algorithm=JWT_ALGORITHM)

def decode_token(token: str, db: Optional[Session] = None) -> dict:
    """
    Decode and strictly validate standard JWT token signature, algorithm, claims, expiration, and revocation.
    Rejects tokens signed with known compromised keys (SEC-JWT-01, SEC-JWT-06, FR-AUTH-02, FR-AUTH-03).
    """
    # 1. Reject tokens signed with known compromised secrets
    for comp_key in COMPROMISED_KEYS:
        try:
            jwt.decode(token, comp_key, algorithms=["HS256", "HS384", "HS512"], options={"verify_signature": True})
            raise HTTPException(401, "Token was signed with a compromised signing key. Re-authentication required (SEC-JWT-01).")
        except HTTPException:
            raise
        except (jwt.InvalidSignatureError, jwt.DecodeError, Exception):
            pass

    secret_key = SECRET.decode("utf-8") if isinstance(SECRET, bytes) else str(SECRET)
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            options={"require": ["exp", "iat", "sub", "uid", "tid"]}
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired. Please sign in again (SEC-003).")
    except jwt.InvalidAlgorithmError:
        raise HTTPException(401, "Disallowed signing algorithm (SEC-JWT-06).")
    except jwt.InvalidTokenError:
        # Check legacy HMAC format fallback for old tests if active key matches
        if "." in token:
            try:
                body, sig = token.rsplit(".", 1)
                expected_sig = hmac.new(SECRET, body.encode(), hashlib.sha256).hexdigest()
                if hmac.compare_digest(sig, expected_sig):
                    p = json.loads(base64.urlsafe_b64decode(body))
                    if p.get("exp", 0) > datetime.now(timezone.utc).timestamp():
                        return p
            except Exception:
                pass
        raise HTTPException(401, "Invalid session credentials. Please sign in again.")

    # 2. Check revocation and user state if db session provided
    if db is not None:
        jti = payload.get("jti")
        if jti:
            revoked = db.scalar(select(RevokedToken).where(RevokedToken.jti == jti))
            if revoked:
                raise HTTPException(401, "Session has been revoked. Please sign in again (FR-AUTH-04).")
        
        user = db.get(User, payload.get("uid"))
        if not user or user.tenant_id != payload.get("tid"):
            raise HTTPException(401, "Session unavailable or user not found.")
        if not getattr(user, "is_active", True):
            raise HTTPException(403, "This account has been deactivated. Please contact your administrator.")
        if getattr(user, "password_changed_at", None):
            pwd_ts = int(user.password_changed_at.replace(tzinfo=timezone.utc).timestamp()) if user.password_changed_at.tzinfo is None else int(user.password_changed_at.timestamp())
            if payload.get("iat", 0) < pwd_ts:
                raise HTTPException(401, "Password was changed since session was issued. Please sign in again (FR-AUTH-05).")

    return payload

def extract_token_from_request(request: Request) -> str:
    """Extract token from Authorization: Bearer header or classpulse_session cookie."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    token = request.cookies.get("classpulse_session")
    if token:
        return token
    raise HTTPException(401, "Please sign in to continue.")

def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)

def verify_csrf(request: Request):
    """CSRF protection for cookie-authenticated mutating requests (SEC-CSRF-01, SEC-CSRF-02)."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return  # Bearer token via custom Authorization header is not ambient cookie authentication
    
    # Cookie-authenticated requests require CSRF token
    cookie_token = request.cookies.get("classpulse_session")
    if cookie_token:
        hdr_token = request.headers.get("X-CSRF-Token")
        cookie_csrf = request.cookies.get("classpulse_csrf")
        if not hdr_token or not cookie_csrf or not hmac.compare_digest(hdr_token, cookie_csrf):
            raise HTTPException(403, "CSRF verification failed: missing or invalid CSRF token (SEC-CSRF-01, SEC-CSRF-02).")

def current_user(request: Request, db: Session = Depends(db_session)) -> User:
    """FastAPI dependency to retrieve the authenticated user and enforce tenant boundary (SEC-012)."""
    verify_csrf(request)
    token = extract_token_from_request(request)
    payload = decode_token(token, db=db)
    user = db.get(User, payload.get("uid"))
    if not user or user.tenant_id != payload.get("tid"):
        raise HTTPException(401, "Session unavailable or user not found.")
    if not getattr(user, "is_active", True):
        raise HTTPException(403, "This account has been deactivated. Please contact your administrator.")
    return user

def require_role(allowed_roles: list[str]):
    """FastAPI dependency to enforce Role-Based Access Control (RBAC) (SEC-009, SEC-010, SEC-011)."""
    def role_checker(user: User = Depends(current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(403, f"Access restricted. Requires one of roles: {', '.join(allowed_roles)}. Your role is: {user.role}")
        return user
    return role_checker

def audit(
    db: Session,
    tenant_id: int,
    event: str,
    actor_id: Optional[int] = None,
    target: Optional[str] = None,
    status: str = "success",
    details: Optional[str] = None
):
    """Logs action to audit table without exposing secrets or bearer tokens (SEC-AUD-01)."""
    db.add(AuditEvent(
        tenant_id=tenant_id,
        actor_id=actor_id,
        event=event,
        target=target,
        status=status,
        details=details
    ))

def set_session_cookie(response: Response, user: User, csrf_token: Optional[str] = None) -> Response:
    token = token_for(user)
    csrf = csrf_token or generate_csrf_token()
    response.set_cookie(
        "classpulse_session",
        token,
        httponly=True,
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
        max_age=ACCESS_TOKEN_TTL_MINUTES * 60,
        path="/"
    )
    response.set_cookie(
        "classpulse_csrf",
        csrf,
        httponly=False,
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
        max_age=ACCESS_TOKEN_TTL_MINUTES * 60,
        path="/"
    )
    return response

# ----------------- Database Normalization Migration Helper (DB-008, DB-009, 3.3.3) -----------------

def sync_students_from_records(db: Session, tenant_id: int):
    """
    Populates normalized Student table from existing JSON Record rows without losing any data.
    Ensures DB-001, DB-002, and section 3.3.3 backward compatibility.
    """
    existing_students = {s.student_id: s for s in db.scalars(select(Student).where(Student.tenant_id == tenant_id)).all()}
    records = db.scalars(select(Record).where(Record.tenant_id == tenant_id)).all()
    
    seen_ids = set()
    for rec in records:
        try:
            data = json.loads(rec.data_json)
            sid = (data.get("student_id") or "").strip()
            if not sid or sid in seen_ids:
                continue
            seen_ids.add(sid)
            
            cid = data.get("course_id") or "General"
            bid = data.get("batch_id") or "Standard"
            name = data.get("student_name") or sid
            
            if sid not in existing_students:
                new_s = Student(tenant_id=tenant_id, student_id=sid, name=name, course_id=cid, batch_id=bid)
                db.add(new_s)
                existing_students[sid] = new_s
        except Exception:
            continue
    db.commit()

# ----------------- Spreadsheet Ingestion & Validation (DATA-001 to DATA-028) -----------------

REQUIRED_COLUMNS = {"record_type", "id", "date", "course_id", "batch_id", "student_id", "amount", "status"}
VALID_TYPES = {"enquiry", "student", "obligation", "payment", "attendance", "exam", "test"}

def extract_rows_from_bytes(data: bytes, filename: str) -> tuple[list[dict], list[str]]:
    fname = filename.lower()
    if fname.endswith(".xlsx"):
        try:
            wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
        except Exception as e:
            raise HTTPException(400, f"Failed to read Excel file: {str(e)} (DATA-004)")
        
        ws = None
        for candidate in ["Import CSV", "import_csv", "Students", "Data", "Sheet1"]:
            if candidate in wb.sheetnames:
                ws = wb[candidate]
                break
        if ws is None:
            ws = wb.active

        all_rows = list(ws.iter_rows(values_only=True))
        header_idx = -1
        headers: list[str] = []
        
        for idx, row in enumerate(all_rows):
            named_cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
            if len(named_cells) >= 2:
                header_idx = idx
                headers = [str(cell).strip() if cell is not None else f"col_{c_i}" for c_i, cell in enumerate(row)]
                break
        
        if header_idx == -1:
            raise HTTPException(400, "Could not find a valid table with headers in this Excel spreadsheet (DATA-005).")
        
        dict_rows = []
        for r in all_rows[header_idx + 1:]:
            if not any(r): continue
            row_dict = {}
            for col_name, val in zip(headers, r):
                if not col_name: continue
                if isinstance(val, (datetime, date)):
                    row_dict[col_name] = val.strftime("%Y-%m-%d")
                elif val is not None:
                    row_dict[col_name] = str(val).strip()
                else:
                    row_dict[col_name] = ""
            dict_rows.append(row_dict)
        return dict_rows, headers
    else:
        try:
            text = data.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            fieldnames = [f.strip() for f in (reader.fieldnames or [])]
            return list(reader), fieldnames
        except UnicodeDecodeError:
            raise HTTPException(400, "Use a UTF-8 encoded CSV file or an .xlsx spreadsheet (DATA-001).")

def parse_sheet_data(data: bytes, filename: str, user_mapping: Optional[Dict[str, str]] = None) -> tuple[list[dict], list[dict], dict]:
    """
    Validates and processes spreadsheet files according to DATA-001 to DATA-028.
    Detects duplicates, validates numerical fields, identifies invalid attendance/marks, and supports manual mapping.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File exceeds maximum upload size of {MAX_UPLOAD_BYTES // 1024 // 1024} MB (DATA-002).")
    
    rows, fieldnames = extract_rows_from_bytes(data, filename)
    if not rows:
        raise HTTPException(400, "Uploaded spreadsheet contains no data rows (DATA-003).")

    # Case 1: Standard ClassPulse log schema
    if UniversalSheetAdapter.is_standard_classpulse(fieldnames) and not user_mapping:
        valid, errors, seen = [], [], set()
        duplicates_count = 0
        for line, raw_row in enumerate(rows, start=2):
            row = {k.strip().lower(): (str(v or "").strip()) for k, v in raw_row.items()}
            problems = []
            kind = row.get("record_type", "").lower()
            row["record_type"] = kind
            row["status"] = row.get("status", "").lower()

            if kind not in VALID_TYPES:
                problems.append("record_type must be enquiry, student, obligation, payment, attendance, or exam")
            if not row.get("id"):
                problems.append("id is required")
            if (kind, row.get("id")) in seen:
                problems.append("duplicate ID in this file (DATA-006)")
                duplicates_count += 1
            seen.add((kind, row.get("id")))

            try:
                date.fromisoformat(row.get("date", ""))
            except ValueError:
                problems.append("date must use YYYY-MM-DD")

            if kind in {"student", "obligation", "payment", "attendance", "exam", "test"} and not row.get("student_id"):
                problems.append("student_id is required")

            if kind in {"obligation", "payment", "exam", "test"}:
                try:
                    amt = Decimal(row.get("amount") or "0")
                    if amt < 0: problems.append("amount must not be negative (DATA-007)")
                except (InvalidOperation, ValueError):
                    problems.append("amount must be a valid number (DATA-007)")

            if kind == "attendance" and row.get("status") not in {"present", "absent", "excused"}:
                problems.append("attendance status must be present, absent, or excused")

            if kind == "payment" and row.get("status") not in {"successful", "refunded"}:
                problems.append("payment status must be successful or refunded")

            if problems:
                errors.append({"line": line, "issues": problems})
            else:
                valid.append(row)

        summary = {
            "total_rows": len(valid) + len(errors),
            "accepted_rows": len(valid),
            "rejected_rows": len(errors),
            "duplicates": duplicates_count,
            "format_detected": "ClassPulse Standard Template",
            "detected_columns": {f: f for f in fieldnames}
        }
        return valid, errors, summary

    # Case 2: Universal Flat Spreadsheet (Marksheets, attendance sheets, rosters)
    profiles, detected_map, sheet_type, val_report = UniversalSheetAdapter.convert_flat_rows_to_profiles(rows, user_mapping)
    normalized_records = UniversalSheetAdapter.convert_flat_to_classpulse_records(rows)
    
    formatted_errors = [{"line": idx + 2, "issues": [err]} for idx, err in enumerate(val_report.get("errors", []))]
    
    summary = {
        "total_rows": len(rows),
        "accepted_rows": len(normalized_records),
        "rejected_rows": len(formatted_errors),
        "duplicates": len(val_report.get("duplicates", [])),
        "format_detected": f"Universal Sheet Ingestion ({sheet_type})",
        "detected_columns": detected_map,
        "warnings": val_report.get("warnings", [])[:10],
        "missing_exam_count": val_report.get("missing_exam_count", 0),
        "missing_attendance_count": val_report.get("missing_attendance_count", 0)
    }
    return normalized_records, formatted_errors, summary

def filtered(records: list[Record], start: str|None, end: str|None, course: str|None, batch: str|None):
    selected_course = course.strip().casefold() if course else None
    selected_batch = batch.strip().casefold() if batch else None
    out = []
    for record in records:
        data = json.loads(record.data_json)
        if start and data.get("date", "") < start: continue
        if end and data.get("date", "") > end: continue
        if selected_course and (data.get("course_id") or "").strip().casefold() != selected_course: continue
        if selected_batch and (data.get("batch_id") or "").strip().casefold() != selected_batch: continue
        out.append(data)
    return out

def validate_filters(start: str|None, end: str|None):
    if start:
        try: date.fromisoformat(start)
        except ValueError: raise HTTPException(400, "Start date must use YYYY-MM-DD")
    if end:
        try: date.fromisoformat(end)
        except ValueError: raise HTTPException(400, "End date must use YYYY-MM-DD")
    if start and end and start > end:
        raise HTTPException(400, "Start date must be before or equal to end date.")

def metrics(rows: list[dict]):
    enquiries = [r for r in rows if r["record_type"] == "enquiry"]
    admissions = [r for r in rows if r["record_type"] == "student"]
    obligations = sum((Decimal(r["amount"]) for r in rows if r["record_type"] == "obligation"), Decimal())
    payments = sum((Decimal(r["amount"]) - Decimal(r.get("refund_amount") or 0) for r in rows if r["record_type"] == "payment" and r["status"].lower() == "successful"), Decimal())
    attendance = [r for r in rows if r["record_type"] == "attendance" and r["status"].lower() != "excused"]
    present = sum(r["status"].lower() == "present" for r in attendance)
    exams = [r for r in rows if r["record_type"] in ("exam", "test")]
    avg_mock_score = round(float(sum(Decimal(r["amount"]) for r in exams) / len(exams)), 1) if exams else None

    return {
        "enquiries": len(enquiries),
        "admissions": len(admissions),
        "conversion_rate": round(len(admissions) / len(enquiries) * 100, 1) if enquiries else 0.0,
        "fee_obligations": float(obligations),
        "fee_collected": float(payments),
        "outstanding_fees": float(max(Decimal(), obligations - payments)),
        "attendance_rate": round(present / len(attendance) * 100, 1) if attendance else 0.0,
        "mock_exams_count": len(exams),
        "avg_mock_score": avg_mock_score
    }

# ----------------- Core Routes -----------------

@app.get("/")
def home():
    return FileResponse(
        BASE_DIR / "static" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
    )

@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "2.1.0",
        "ml_model_loaded": predictor.is_trained,
        "ml_model_version": predictor.model_version,
        "ml_dataset_provenance": predictor.dataset_provenance,
        "universal_sheet_support": True
    }

# ----------------- Authentication Routes (SEC-001 to SEC-013) -----------------

@app.get("/api/v1/auth/csrf")
def get_csrf(request: Request):
    """Retrieve or initialize CSRF double-submit token (SEC-CSRF-01)."""
    token = request.cookies.get("classpulse_csrf") or generate_csrf_token()
    res = JSONResponse({"csrf_token": token})
    res.set_cookie(
        "classpulse_csrf",
        token,
        httponly=False,
        samesite=COOKIE_SAMESITE,
        secure=COOKIE_SECURE,
        max_age=ACCESS_TOKEN_TTL_MINUTES * 60,
        path="/"
    )
    return res

@app.post("/api/v1/auth/register")
async def register(request: Request, db: Session = Depends(db_session)):
    client_ip = request.client.host if request.client else "127.0.0.1"
    check_rate_limit(f"register_{client_ip}", max_attempts=10, window_seconds=600, db=db)
    
    body = await request.json()
    name = body.get("centre_name", "").strip()
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    full_name = body.get("full_name", "").strip()

    if len(name) < 2:
        raise HTTPException(400, "Centre name must be at least 2 characters.")
    if "@" not in email or "." not in email:
        raise HTTPException(400, "A valid email address is required.")
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters long.")
    if not any(c.isdigit() for c in password) or not any(c.isalpha() for c in password):
        raise HTTPException(400, "Password must contain both letters and at least one number.")

    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with that email already exists.")

    tenant = Tenant(name=name)
    db.add(tenant)
    db.flush()

    user = User(
        tenant_id=tenant.id,
        email=email,
        password_hash=password_hash(password),
        full_name=full_name or name,
        role="owner",
        is_active=True,
        last_login_at=datetime.now(timezone.utc)
    )
    db.add(user)
    audit(db, tenant.id, "account_created", target=email)
    db.commit()

    access_token = token_for(user)
    csrf_token = generate_csrf_token()
    return set_session_cookie(
        JSONResponse({
            "access_token": access_token,
            "token_type": "bearer",
            "csrf_token": csrf_token,
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "centre_name": tenant.name,
                "role": user.role
            }
        }),
        user,
        csrf_token=csrf_token
    )

@app.post("/api/v1/auth/login")
async def login(request: Request, db: Session = Depends(db_session)):
    client_ip = request.client.host if request.client else "127.0.0.1"
    check_rate_limit(f"login_{client_ip}", max_attempts=15, window_seconds=600, db=db)

    body = await request.json()
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    if not email or not password:
        raise HTTPException(400, "Email and password are required.")

    user = db.scalar(select(User).where(User.email == email))
    # FR-AUTH-07: Generic authentication failure message that does not leak username existence
    if not user or not verify_password(password, user.password_hash) or not getattr(user, "is_active", True):
        raise HTTPException(401, "Incorrect email or password.")

    user.last_login_at = datetime.now(timezone.utc)
    tenant = db.get(Tenant, user.tenant_id)
    audit(db, user.tenant_id, "signed_in", actor_id=user.id, target=user.email)
    db.commit()

    # Backward compatibility: automatically sync students from records on login
    sync_students_from_records(db, user.tenant_id)

    access_token = token_for(user)
    csrf_token = generate_csrf_token()
    return set_session_cookie(
        JSONResponse({
            "access_token": access_token,
            "token_type": "bearer",
            "csrf_token": csrf_token,
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "centre_name": tenant.name if tenant else "",
                "role": user.role
            }
        }),
        user,
        csrf_token=csrf_token
    )

@app.post("/api/v1/auth/logout")
def logout(request: Request, db: Session = Depends(db_session)):
    """Logs out user, invalidates JWT jti in RevokedToken store, and clears cookies (FR-AUTH-04, SEC-TOK-05)."""
    try:
        token = extract_token_from_request(request)
        payload = decode_token(token)
        jti = payload.get("jti")
        if jti:
            exp_ts = payload.get("exp", 0)
            exp_dt = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
            db.add(RevokedToken(
                jti=jti,
                tenant_id=payload.get("tid"),
                user_id=payload.get("uid"),
                revoked_at=datetime.now(timezone.utc),
                expires_at=exp_dt
            ))
            db.commit()
    except Exception:
        pass
    res = JSONResponse({"ok": True, "message": "Signed out successfully."})
    res.delete_cookie("classpulse_session", path="/")
    res.delete_cookie("classpulse_csrf", path="/")
    return res

@app.get("/api/v1/me")
def me(user: User = Depends(current_user), db: Session = Depends(db_session)):
    tenant = db.get(Tenant, user.tenant_id)
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "centre_name": tenant.name if tenant else "",
        "role": user.role,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None
    }

@app.post("/api/v1/auth/change-password")
async def change_password(request: Request, user: User = Depends(current_user), db: Session = Depends(db_session)):
    body = await request.json()
    old_password = body.get("old_password", "")
    new_password = body.get("new_password", "")

    if not verify_password(old_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect.")
    if len(new_password) < 8 or not any(c.isdigit() for c in new_password) or not any(c.isalpha() for c in new_password):
        raise HTTPException(400, "New password must be at least 8 characters and contain both letters and numbers.")

    user.password_hash = password_hash(new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    audit(db, user.tenant_id, "password_changed", actor_id=user.id, target=user.email)
    db.commit()
    return {"ok": True, "message": "Password changed successfully."}

@app.get("/api/v1/auth/users")
def list_centre_users(user: User = Depends(require_role(["owner", "admin"])), db: Session = Depends(db_session)):
    users = db.scalars(select(User).where(User.tenant_id == user.tenant_id).order_by(User.id)).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None
        }
        for u in users
    ]

@app.post("/api/v1/auth/users")
async def create_centre_user(request: Request, user: User = Depends(require_role(["owner", "admin"])), db: Session = Depends(db_session)):
    body = await request.json()
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")
    full_name = body.get("full_name", "").strip()
    role = body.get("role", "teacher").lower()

    if role not in ("admin", "teacher", "viewer"):
        raise HTTPException(400, "Role must be 'admin', 'teacher', or 'viewer'.")
    if "@" not in email or "." not in email:
        raise HTTPException(400, "A valid email address is required.")
    if len(password) < 8 or not any(c.isdigit() for c in password) or not any(c.isalpha() for c in password):
        raise HTTPException(400, "Password must be at least 8 characters and contain both letters and numbers.")

    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "A user with that email already exists.")

    new_user = User(
        tenant_id=user.tenant_id,
        email=email,
        password_hash=password_hash(password),
        full_name=full_name or email.split("@")[0],
        role=role,
        is_active=True
    )
    db.add(new_user)
    audit(db, user.tenant_id, f"staff_created:{role}", actor_id=user.id, target=email)
    db.commit()
    return {"ok": True, "message": f"User {email} created with role '{role}'.", "user_id": new_user.id}

# ----------------- Spreadsheet Ingestion Endpoints (DATA-001 to DATA-028, IMP-01 to IMP-07) -----------------

@app.post("/api/v1/imports/preview")
async def preview_import(
    file: UploadFile = File(...),
    user: User = Depends(require_role(["owner", "admin", "teacher"])),
    db: Session = Depends(db_session)
):
    ext = file.filename.lower().split(".")[-1]
    if ext not in ("csv", "xlsx"):
        raise HTTPException(400, "Only .csv and .xlsx spreadsheet files are accepted (DATA-001).")
    
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File exceeds maximum size of {MAX_UPLOAD_BYTES // 1024 // 1024} MB (DATA-002).")

    valid, errors, summary = parse_sheet_data(contents, file.filename)
    preview_key = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=2)

    db.add(ImportPreviewRecord(
        preview_id=preview_key,
        tenant_id=user.tenant_id,
        initiating_user_id=user.id,
        filename=file.filename,
        payload_json=json.dumps({"valid": valid, "errors": errors, "summary": summary}),
        status="pending",
        created_at=now,
        expires_at=expires
    ))
    audit(db, user.tenant_id, f"import_preview_created:{file.filename}", actor_id=user.id)
    db.commit()

    return {
        "preview_id": preview_key,
        "filename": file.filename,
        "summary": summary,
        "errors": errors[:25],
        "sample": valid[:5]
    }

@app.post("/api/v1/imports/{preview_id}/confirm")
def confirm_import(
    preview_id: str,
    user: User = Depends(require_role(["owner", "admin", "teacher"])),
    db: Session = Depends(db_session)
):
    check_rate_limit(f"import_confirm_{user.tenant_id}", max_attempts=30, window_seconds=60, db=db)
    
    preview = db.scalar(
        select(ImportPreviewRecord).where(
            ImportPreviewRecord.preview_id == preview_id,
            ImportPreviewRecord.tenant_id == user.tenant_id
        )
    )
    if not preview:
        raise HTTPException(404, "Import preview expired or not found. Upload the file again (DATA-028).")
    
    data = json.loads(preview.payload_json)

    if preview.status == "completed":
        # Idempotent confirmation (IMP-06)
        return {"id": 0, "message": "Import already completed.", "status": "already_processed", **data.get("summary", {})}
    
    if preview.status != "pending":
        raise HTTPException(400, f"Import preview is in status '{preview.status}'.")

    # Check expiration
    if preview.expires_at:
        exp_dt = preview.expires_at.replace(tzinfo=timezone.utc) if preview.expires_at.tzinfo is None else preview.expires_at
        if exp_dt < datetime.now(timezone.utc):
            preview.status = "expired"
            db.commit()
            raise HTTPException(404, "Import preview has expired. Upload the file again.")

    valid_rows = data.get("valid", [])
    error_rows = data.get("errors", [])
    summary = data.get("summary", {})

    preview.status = "completed"

    job = ImportJob(
        tenant_id=user.tenant_id,
        initiating_user_id=user.id,
        filename=preview.filename,
        status="completed",
        accepted_rows=len(valid_rows),
        rejected_rows=len(error_rows),
        summary_json=json.dumps(summary)
    )
    db.add(job)
    db.flush()

    for row in valid_rows:
        db.add(Record(
            tenant_id=user.tenant_id,
            import_id=job.id,
            record_type=row["record_type"],
            data_json=json.dumps(row)
        ))
    
    # Sync normalized Student records and log initial prediction history (DB-001, DB-006)
    sync_students_from_records(db, user.tenant_id)
    
    # Auto-log initial prediction snapshot for newly imported students
    try:
        all_recs = [json.loads(r.data_json) for r in db.scalars(select(Record).where(Record.tenant_id == user.tenant_id)).all()]
        pred_res = predictor.predict_cohort(all_recs)
        for p in pred_res.get("predictions", []):
            db.add(PredictionHistory(
                tenant_id=user.tenant_id,
                student_id=p["student_id"],
                pass_probability=p["pass_probability"],
                risk_level=p["risk_level"],
                predicted_outcome=p["predicted_outcome"],
                avg_mock_score=p.get("avg_mock_score"),
                attendance_rate=p["attendance_rate"],
                financial_risk_level=p.get("financial_risk", {}).get("financial_risk_level", "Clear"),
                model_version=p.get("model_version", predictor.model_version),
                factors_json=json.dumps(p.get("key_factors", [])),
                is_tentative=p.get("is_tentative", False),
                provenance=p.get("provenance", predictor.dataset_provenance)
            ))
    except Exception:
        pass

    audit(db, user.tenant_id, f"import_confirmed:{preview.filename}", actor_id=user.id)
    db.commit()
    return {"id": job.id, "message": "Import completed successfully.", **summary}

@app.get("/api/v1/imports")
def list_imports(user: User = Depends(current_user), db: Session = Depends(db_session)):
    jobs = db.scalars(select(ImportJob).where(ImportJob.tenant_id == user.tenant_id).order_by(ImportJob.created_at.desc())).all()
    return [
        {
            "id": j.id,
            "filename": j.filename,
            "status": j.status,
            "accepted_rows": j.accepted_rows,
            "rejected_rows": j.rejected_rows,
            "created_at": j.created_at.isoformat()
        }
        for j in jobs
    ]

# ----------------- Student Profiles & Prediction History (FEAT-001 to FEAT-012) -----------------

@app.get("/api/v1/students")
def list_students(
    q: Optional[str] = None,
    course: Optional[str] = None,
    batch: Optional[str] = None,
    risk_level: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(db_session)
):
    """
    Search and paginated listing of students with latest academic risk status (FEAT-001, UI-005, UI-006).
    """
    # Ensure students table is synced
    sync_students_from_records(db, user.tenant_id)
    
    tenant_records = db.scalars(select(Record).where(Record.tenant_id == user.tenant_id)).all()
    rows = [json.loads(r.data_json) for r in tenant_records]
    preds_data = predictor.predict_cohort(rows, course_filter=course, batch_filter=batch, risk_filter=risk_level)
    
    all_students = preds_data["predictions"]
    if q:
        query_str = q.strip().lower()
        all_students = [s for s in all_students if query_str in s["student_id"].lower() or query_str in s.get("course_id", "").lower()]

    total_count = len(all_students)
    start_idx = (page - 1) * limit
    paginated = all_students[start_idx:start_idx + limit]

    return {
        "total_students": total_count,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total_count / limit) if total_count > 0 else 1,
        "students": paginated
    }

@app.get("/api/v1/students/{student_id}")
def get_student_profile(student_id: str, user: User = Depends(current_user), db: Session = Depends(db_session)):
    """
    Returns comprehensive 360-degree student profile (FEAT-002, FEAT-003, FEAT-004, FEAT-005).
    """
    tenant_records = db.scalars(select(Record).where(Record.tenant_id == user.tenant_id)).all()
    rows = [json.loads(r.data_json) for r in tenant_records]
    student_rows = [r for r in rows if (r.get("student_id") or "").strip() == student_id.strip()]

    if not student_rows:
        raise HTTPException(404, f"Student '{student_id}' not found in active centre records.")

    features = predictor.extract_student_features(student_rows)
    profile = features.get(student_id.strip())
    if not profile:
        raise HTTPException(404, f"Profile for student '{student_id}' could not be computed.")

    current_pred = predictor.predict_student(profile)
    
    # Save snapshot to prediction history (FEAT-007 to FEAT-010)
    db.add(PredictionHistory(
        tenant_id=user.tenant_id,
        student_id=student_id,
        pass_probability=current_pred["pass_probability"],
        risk_level=current_pred["risk_level"],
        predicted_outcome=current_pred["predicted_outcome"],
        avg_mock_score=current_pred.get("avg_mock_score"),
        attendance_rate=current_pred["attendance_rate"],
        financial_risk_level=current_pred.get("financial_risk", {}).get("financial_risk_level", "Clear"),
        model_version=current_pred.get("model_version", predictor.model_version),
        factors_json=json.dumps(current_pred.get("key_factors", [])),
        is_tentative=current_pred.get("is_tentative", False),
        provenance=current_pred.get("provenance", predictor.dataset_provenance)
    ))
    db.commit()

    # Extract detailed attendance & exam log records
    attendance_logs = [r for r in student_rows if r.get("record_type") == "attendance"]
    attendance_logs.sort(key=lambda x: x.get("date", ""), reverse=True)

    exam_logs = [r for r in student_rows if r.get("record_type") in ("exam", "test")]
    exam_logs.sort(key=lambda x: x.get("date", ""), reverse=True)

    # Query historical predictions (FEAT-006, FEAT-011, FEAT-012)
    history_records = db.scalars(
        select(PredictionHistory)
        .where(PredictionHistory.tenant_id == user.tenant_id, PredictionHistory.student_id == student_id)
        .order_by(PredictionHistory.created_at.desc())
        .limit(10)
    ).all()

    prediction_history = [
        {
            "id": h.id,
            "pass_probability": h.pass_probability,
            "risk_level": h.risk_level,
            "predicted_outcome": h.predicted_outcome,
            "avg_mock_score": h.avg_mock_score,
            "attendance_rate": h.attendance_rate,
            "model_version": h.model_version,
            "created_at": h.created_at.isoformat()
        }
        for h in history_records
    ]

    return {
        "student_id": student_id,
        "course_id": profile["course_id"],
        "batch_id": profile["batch_id"],
        "academic_metrics": {
            "attendance_rate": profile["attendance_rate"],
            "classes_attended": profile["present_count"],
            "total_sessions": profile["total_sessions"],
            "avg_mock_score": profile["avg_mock_score"],
            "has_mock_records": profile["has_mock_records"],
            "attendance_trend": profile.get("attendance_trend", 0.0),
            "course_difficulty": profile.get("course_difficulty", 1.0)
        },
        "financial_standing": current_pred.get("financial_risk", {}),
        "current_prediction": current_pred,
        "attendance_logs": attendance_logs[:20],
        "exam_logs": exam_logs[:20],
        "prediction_history": prediction_history
    }

@app.get("/api/v1/students/{student_id}/predictions")
def get_student_prediction_history(student_id: str, user: User = Depends(current_user), db: Session = Depends(db_session)):
    """Returns timeline of historical predictions for reviewing changes over time (FEAT-006 to FEAT-012)."""
    history_records = db.scalars(
        select(PredictionHistory)
        .where(PredictionHistory.tenant_id == user.tenant_id, PredictionHistory.student_id == student_id)
        .order_by(PredictionHistory.created_at.desc())
    ).all()
    return [
        {
            "id": h.id,
            "pass_probability": h.pass_probability,
            "risk_level": h.risk_level,
            "predicted_outcome": h.predicted_outcome,
            "avg_mock_score": h.avg_mock_score,
            "attendance_rate": h.attendance_rate,
            "financial_risk_level": h.financial_risk_level,
            "model_version": h.model_version,
            "factors": json.loads(h.factors_json) if h.factors_json else [],
            "created_at": h.created_at.isoformat()
        }
        for h in history_records
    ]

# ----------------- PDF Analytical Reports (FEAT-013 to FEAT-016, REP-01 to REP-04) -----------------

@app.get("/api/v1/reports/pdf/student/{student_id}")
def download_student_report_card(student_id: str, user: User = Depends(current_user), db: Session = Depends(db_session)):
    """
    Generates and downloads official Student Performance & AI Risk Report Card (PDF) (REP-01, REP-02).
    """
    try:
        tenant = db.get(Tenant, user.tenant_id)
        centre_name = tenant.name if tenant else "ClassPulse Academy"

        tenant_records = db.scalars(select(Record).where(Record.tenant_id == user.tenant_id)).all()
        rows = [json.loads(r.data_json) for r in tenant_records]
        student_rows = [r for r in rows if (r.get("student_id") or "").strip() == student_id.strip()]

        if not student_rows:
            raise HTTPException(404, f"Student '{student_id}' not found.")

        features = predictor.extract_student_features(student_rows)
        profile = features.get(student_id.strip())
        if not profile:
            raise HTTPException(404, "Student profile could not be generated.")

        prediction = predictor.predict_student(profile)
        prediction["exam_scores_detail"] = [r for r in student_rows if r.get("record_type") in ("exam", "test")]

        pdf_bytes = generate_student_report_card(prediction, centre_name=centre_name)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=classpulse-report-{student_id}.pdf"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to generate student report card for {student_id}: {e}")
        raise HTTPException(500, "Unable to generate report card at this time. Please try again later (REP-04).")

@app.get("/api/v1/reports/pdf/cohort-summary")
def download_cohort_summary_pdf(
    start: Optional[str] = None,
    end: Optional[str] = None,
    course: Optional[str] = None,
    batch: Optional[str] = None,
    user: User = Depends(current_user),
    db: Session = Depends(db_session)
):
    """
    Generates and downloads Executive Cohort Analytics & Predictive Risk Report (PDF) (FEAT-013, FEAT-014, REP-01, REP-04).
    """
    validate_filters(start, end)
    try:
        tenant = db.get(Tenant, user.tenant_id)
        centre_name = tenant.name if tenant else "ClassPulse Academy"

        tenant_records = db.scalars(select(Record).where(Record.tenant_id == user.tenant_id)).all()
        current = filtered(tenant_records, start, end, course, batch)
        ml_analysis = predictor.predict_cohort(current, course_filter=course, batch_filter=batch)

        filters_applied = {"start": start, "end": end, "course": course, "batch": batch}
        pdf_bytes = generate_cohort_summary_report(ml_analysis["summary"], centre_name=centre_name, filters_applied=filters_applied)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "inline; filename=classpulse-cohort-executive-report.pdf"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to generate cohort summary report: {e}")
        raise HTTPException(500, "Unable to generate cohort summary report at this time. Please try again later (REP-04).")

# ----------------- Machine Learning Governance & Retraining (ML-001 to ML-020) -----------------

@app.get("/api/v1/ml/model-info")
def get_model_evaluation_info(user: User = Depends(current_user)):
    """
    Returns full machine learning model evaluation metrics, held-out validation results, and provenance (ML-001 to ML-014).
    """
    return {
        "model_name": "Random Forest Classifier (Benchmark Model)",
        "model_version": predictor.model_version,
        "dataset_provenance": predictor.dataset_provenance,
        "is_synthetic": predictor.is_synthetic,
        "training_date": predictor.training_date,
        "held_out_evaluation": {
            "test_accuracy_pct": predictor.model_accuracy,
            "precision_pct": predictor.model_precision,
            "recall_pct": predictor.model_recall,
            "f1_score_pct": predictor.model_f1,
            "roc_auc_pct": predictor.model_roc_auc,
            "brier_score_loss": predictor.model_brier_score,
            "confusion_matrix": predictor.confusion_matrix,
            "train_samples": predictor.train_samples,
            "test_samples": predictor.test_samples
        },
        "cross_validation": {
            "folds": 5,
            "mean_accuracy_pct": predictor.cv_mean_accuracy,
            "std_accuracy_pct": predictor.cv_std_accuracy
        },
        "class_distribution": predictor.class_distribution,
        "feature_importances": predictor.get_feature_importances(),
        "academic_financial_separation": "Academic features only. Fee status tracked independently without biasing predictive accuracy (ML-027).",
        "statutory_disclaimer": "Predictions are statistical estimates for pedagogical support on benchmark datasets and do not guarantee academic outcomes (ML-002, ML-025)."
    }

@app.post("/api/v1/ml/retrain")
def retrain_model(user: User = Depends(require_role(["owner", "admin"])), db: Session = Depends(db_session)):
    """
    Retrains the Random Forest model using verified historical student outcomes from the centre (ML-015 to ML-020).
    """
    tenant_records = db.scalars(select(Record).where(Record.tenant_id == user.tenant_id)).all()
    rows = [json.loads(r.data_json) for r in tenant_records]
    if not rows:
        raise HTTPException(400, "No records found in current centre to retrain model (ML-017).")

    profiles = list(predictor.extract_student_features(rows).values())
    result = predictor.retrain_from_historical_data(profiles)

    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Retraining validation failed. Previous model preserved (ML-020)."))

    audit(db, user.tenant_id, f"model_retrained:{result.get('model_version')}", actor_id=user.id)
    db.commit()
    return result

# ----------------- Database Backup & Restore (DEP-004, DEP-005, SEC-TEN-01) -----------------

@app.get("/api/v1/admin/backup")
def download_database_backup(user: User = Depends(require_role(["owner", "admin"])), db: Session = Depends(db_session)):
    """
    Exports a secure database backup archive strictly scoped to the authenticated tenant (DEP-004, SEC-TEN-01).
    """
    tenant_records = db.scalars(select(Record).where(Record.tenant_id == user.tenant_id)).all()
    tenant_students = db.scalars(select(Student).where(Student.tenant_id == user.tenant_id)).all()
    tenant_jobs = db.scalars(select(ImportJob).where(ImportJob.tenant_id == user.tenant_id)).all()

    audit(db, user.tenant_id, "backup_downloaded", actor_id=user.id)
    db.commit()

    backup_data = {
        "export_date": datetime.now(timezone.utc).isoformat(),
        "tenant_id": user.tenant_id,
        "students": [
            {
                "student_id": s.student_id,
                "name": s.name,
                "course_id": s.course_id,
                "batch_id": s.batch_id
            }
            for s in tenant_students
        ],
        "import_jobs": [
            {
                "filename": j.filename,
                "accepted_rows": j.accepted_rows,
                "rejected_rows": j.rejected_rows,
                "status": j.status
            }
            for j in tenant_jobs
        ],
        "records": [json.loads(r.data_json) for r in tenant_records]
    }
    return Response(
        content=json.dumps(backup_data, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=classpulse-backup.json"}
    )

@app.post("/api/v1/admin/restore")
async def restore_database_backup(
    file: UploadFile = File(...),
    user: User = Depends(require_role(["owner", "admin"])),
    db: Session = Depends(db_session)
):
    """
    Restores database records from an authorized backup file into the authenticated tenant (DEP-005, SEC-TEN-01).
    """
    contents = await file.read()
    try:
        data = json.loads(contents.decode("utf-8"))
        records = data.get("records", [])
        if not records:
            raise HTTPException(400, "Backup file contains no records to restore.")
        
        job = ImportJob(
            tenant_id=user.tenant_id,
            initiating_user_id=user.id,
            filename=f"Restore: {file.filename}",
            status="completed",
            accepted_rows=len(records),
            rejected_rows=0,
            summary_json=json.dumps({"restored": len(records)})
        )
        db.add(job)
        db.flush()

        for r in records:
            db.add(Record(
                tenant_id=user.tenant_id,
                import_id=job.id,
                record_type=r.get("record_type", "student"),
                data_json=json.dumps(r)
            ))
        
        sync_students_from_records(db, user.tenant_id)
        audit(db, user.tenant_id, f"backup_restored:{len(records)}_records", actor_id=user.id)
        db.commit()
        return {"ok": True, "message": f"Successfully restored {len(records)} records from backup."}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to restore backup: {e}")
        raise HTTPException(400, f"Failed to restore backup: {str(e)}")

# ----------------- Existing Analytical & Matplotlib Endpoints -----------------

@app.get("/api/v1/records")
def records(
    record_type: str|None = None,
    start: str|None = None,
    end: str|None = None,
    course: str|None = None,
    batch: str|None = None,
    user: User = Depends(current_user),
    db: Session = Depends(db_session)
):
    validate_filters(start, end)
    if record_type and record_type not in VALID_TYPES: raise HTTPException(400, "Unsupported record type.")
    tenant_records = db.scalars(select(Record).where(Record.tenant_id == user.tenant_id)).all()
    result = filtered(tenant_records, start, end, course, batch)
    if record_type: result = [row for row in result if row["record_type"] == record_type]
    result.sort(key=lambda row: (row["date"], row["id"]), reverse=True)
    return {"records": result[:500], "result_count": len(result), "limit": 500}

@app.get("/api/v1/analytics/overview")
def overview(
    start: str|None = None,
    end: str|None = None,
    course: str|None = None,
    batch: str|None = None,
    user: User = Depends(current_user),
    db: Session = Depends(db_session)
):
    validate_filters(start, end)
    recs = db.scalars(select(Record).where(Record.tenant_id == user.tenant_id)).all()
    current = filtered(recs, start, end, course, batch)
    prior = None
    if start and end:
        days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
        prior_end = (date.fromisoformat(start) - timedelta(days=1))
        prior_start = prior_end - timedelta(days=days-1)
        prior = metrics(filtered(recs, prior_start.isoformat(), prior_end.isoformat(), course, batch))
    
    ml_analysis = predictor.predict_cohort(current, course_filter=course, batch_filter=batch)

    return {
        "metrics": metrics(current),
        "comparison": prior,
        "filters": {"start": start, "end": end, "course": course, "batch": batch, "matched_records": len(current)},
        "ml_summary": ml_analysis["summary"],
        "definition": "Universal sheet ingestion enabled. Predictions adapt automatically to any spreadsheet format."
    }

@app.get("/api/v1/ml/predictions")
def get_predictions(
    course: str|None = None,
    batch: str|None = None,
    risk_level: str|None = None,
    user: User = Depends(current_user),
    db: Session = Depends(db_session)
):
    tenant_records = db.scalars(select(Record).where(Record.tenant_id == user.tenant_id)).all()
    rows = [json.loads(r.data_json) for r in tenant_records]
    return predictor.predict_cohort(rows, course_filter=course, batch_filter=batch, risk_filter=risk_level)

@app.post("/api/v1/ml/analyze-sheet")
async def analyze_arbitrary_sheet(file: UploadFile = File(...), user: User = Depends(current_user)):
    ext = file.filename.lower().split(".")[-1]
    if ext not in ("csv", "xlsx"):
        raise HTTPException(400, "Only .csv and .xlsx spreadsheet files are accepted.")
    
    data = await file.read()
    rows, fieldnames = extract_rows_from_bytes(data, file.filename)
    if not rows:
        raise HTTPException(400, "Uploaded spreadsheet contains no data rows.")
    
    result = predictor.predict_from_generic_sheet(rows, filename=file.filename)
    return {
        "filename": file.filename,
        **result
    }

@app.post("/api/v1/ml/simulate")
async def simulate_student(request: Request, user: User = Depends(current_user)):
    body = await request.json()
    att_rate = float(body.get("attendance_rate", 75.0))
    mock_score = float(body.get("avg_mock_score", 65.0))
    fee_ratio = float(body.get("fee_clearance_ratio", 1.0))
    course_id = body.get("course_id", "General")
    classes_attended = body.get("classes_attended")
    if classes_attended is not None:
        classes_attended = int(classes_attended)
    
    pred = predictor.simulate(att_rate, mock_score, fee_ratio, course_id, classes_attended)
    return {"prediction": pred}

@app.get("/api/v1/ml/export-predictions")
def export_predictions(
    course: str|None = None,
    batch: str|None = None,
    risk_level: str|None = None,
    user: User = Depends(current_user),
    db: Session = Depends(db_session)
):
    tenant_records = db.scalars(select(Record).where(Record.tenant_id == user.tenant_id)).all()
    rows = [json.loads(r.data_json) for r in tenant_records]
    results = predictor.predict_cohort(rows, course_filter=course, batch_filter=batch, risk_filter=risk_level)
    
    audit(db, user.tenant_id, "ml_predictions_exported")
    db.commit()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ClassPulse AI - Student Exam Pass Predictions Report"])
    writer.writerow(["Model Name", results["summary"].get("model_name", "Random Forest Classifier")])
    writer.writerow(["Model Version", results["summary"].get("model_version", "v2.1.0-benchmark")])
    writer.writerow(["Dataset Provenance", results["summary"].get("dataset_provenance", "synthetic_benchmark")])
    writer.writerow(["Model Held-out Accuracy", f"{results['summary'].get('model_accuracy', 0)}%"])
    writer.writerow(["Model ROC-AUC", f"{results['summary'].get('model_roc_auc', 0)}%"])
    writer.writerow([])
    writer.writerow([
        "Student ID", "Course", "Batch", "Attendance Rate (%)",
        "Classes Attended", "Total Classes", "Avg Mock Score", "Has Mock Records",
        "Pass Probability (%)", "Forecasted Outcome", "Risk Tier", "Key Factors", "Recommendations",
        "Fee Clearance (%)", "Outstanding Fees (INR)", "Financial Standing"
    ])

    for p in results["predictions"]:
        fin = p.get("financial_risk", {})
        writer.writerow([
            p["student_id"],
            p["course_id"],
            p["batch_id"],
            p["attendance_rate"],
            p["classes_attended"],
            p["total_classes"],
            p["avg_mock_score"] if p["avg_mock_score"] is not None else "N/A (Missing)",
            "Yes" if p["has_mock_records"] else "No",
            p["pass_probability"],
            p["predicted_outcome"],
            p["risk_level"],
            " | ".join(p.get("key_factors", [])),
            " | ".join(p.get("recommendations", [])),
            fin.get("fee_clearance_pct", 100.0),
            fin.get("outstanding_fees", 0.0),
            fin.get("financial_status", "Clear")
        ])

    output.seek(0)
    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=classpulse-exam-predictions.csv"})

@app.get("/api/v1/reports/export")
def export_kpi(
    start: str|None = None,
    end: str|None = None,
    course: str|None = None,
    batch: str|None = None,
    user: User = Depends(current_user),
    db: Session = Depends(db_session)
):
    validate_filters(start, end)
    recs = db.scalars(select(Record).where(Record.tenant_id == user.tenant_id)).all()
    current = filtered(recs, start, end, course, batch)
    m = metrics(current)
    
    audit(db, user.tenant_id, "kpi_report_exported")
    db.commit()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ClassPulse AI Coaching Analytics Report"])
    writer.writerow(["Generated At (UTC)", datetime.now(timezone.utc).isoformat()])
    writer.writerow(["Metric", "Value"])
    for k, v in m.items():
        writer.writerow([k, v])
    output.seek(0)
    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=classpulse-analytics-summary.csv"})

# ----------------- Matplotlib Visual Analytics Endpoints -----------------

@app.get("/api/v1/charts/all")
def get_all_charts(
    start: Optional[str] = None,
    end: Optional[str] = None,
    course: Optional[str] = None,
    batch: Optional[str] = None,
    user: User = Depends(current_user),
    db: Session = Depends(db_session)
):
    validate_filters(start, end)
    tenant = db.get(Tenant, user.tenant_id)
    centre_name = tenant.name if tenant else "ClassPulse Coaching Centre"

    tenant_records = db.scalars(select(Record).where(Record.tenant_id == user.tenant_id)).all()
    current_records = filtered(tenant_records, start, end, course, batch)
    ml_analysis = predictor.predict_cohort(current_records, course_filter=course, batch_filter=batch)

    charts_bundle = generate_all_charts(
        current_records,
        ml_predictions=ml_analysis,
        centre_name=centre_name,
        filters_applied={"start": start, "end": end, "course": course, "batch": batch}
    )
    return charts_bundle

@app.get("/api/v1/charts/master")
def get_master_graph_image(
    start: Optional[str] = None,
    end: Optional[str] = None,
    course: Optional[str] = None,
    batch: Optional[str] = None,
    user: User = Depends(current_user),
    db: Session = Depends(db_session)
):
    validate_filters(start, end)
    tenant = db.get(Tenant, user.tenant_id)
    centre_name = tenant.name if tenant else "ClassPulse Coaching Centre"

    tenant_records = db.scalars(select(Record).where(Record.tenant_id == user.tenant_id)).all()
    current_records = filtered(tenant_records, start, end, course, batch)
    ml_analysis = predictor.predict_cohort(current_records, course_filter=course, batch_filter=batch)

    raw_png = generate_master_graph(
        current_records,
        ml_predictions=ml_analysis,
        centre_name=centre_name,
        filters_applied={"start": start, "end": end, "course": course, "batch": batch},
        as_base64=False
    )
    return Response(content=raw_png, media_type="image/png", headers={"Content-Disposition": "inline; filename=classpulse-master-graph.png"})

@app.get("/api/v1/charts/small/{chart_type}")
def get_small_graph_image(
    chart_type: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    course: Optional[str] = None,
    batch: Optional[str] = None,
    user: User = Depends(current_user),
    db: Session = Depends(db_session)
):
    validate_filters(start, end)
    ctype = chart_type.lower().strip()
    if ctype not in SMALL_GRAPH_DISPATCHER:
        raise HTTPException(404, f"Chart type '{chart_type}' not found. Supported: {list(SMALL_GRAPH_DISPATCHER.keys())}")

    tenant_records = db.scalars(select(Record).where(Record.tenant_id == user.tenant_id)).all()
    current_records = filtered(tenant_records, start, end, course, batch)
    ml_analysis = predictor.predict_cohort(current_records, course_filter=course, batch_filter=batch)

    raw_png = generate_small_graph(
        ctype,
        current_records,
        ml_predictions=ml_analysis,
        as_base64=False
    )
    return Response(content=raw_png, media_type="image/png", headers={"Content-Disposition": f"inline; filename=classpulse-{ctype}-chart.png"})

@app.post("/api/v1/charts/generate-from-sheet")
async def generate_charts_from_sheet(file: UploadFile = File(...), user: User = Depends(current_user)):
    ext = file.filename.lower().split(".")[-1]
    if ext not in ("csv", "xlsx"):
        raise HTTPException(400, "Only .csv and .xlsx spreadsheet files are accepted.")

    data = await file.read()
    rows, fieldnames = extract_rows_from_bytes(data, file.filename)
    if not rows:
        raise HTTPException(400, "Uploaded file contains no rows.")

    ml_result = predictor.predict_from_generic_sheet(rows, filename=file.filename)
    charts_data = generate_all_charts(
        rows,
        ml_predictions=ml_result,
        centre_name=f"Sheet: {file.filename}"
    )
    charts_data["filename"] = file.filename
    charts_data["detected_columns"] = ml_result.get("detected_columns", {})
    return charts_data

# ----------------- Destructive Account Actions -----------------

@app.delete("/api/v1/account/data")
def delete_data(user: User = Depends(require_role(["owner", "admin"])), db: Session = Depends(db_session)):
    """Deletes all imported records and student profiles for this centre (SEC-011)."""
    db.query(Record).filter_by(tenant_id=user.tenant_id).delete()
    db.query(ImportJob).filter_by(tenant_id=user.tenant_id).delete()
    db.query(Student).filter_by(tenant_id=user.tenant_id).delete()
    db.query(PredictionHistory).filter_by(tenant_id=user.tenant_id).delete()
    audit(db, user.tenant_id, "tenant_data_deleted")
    db.commit()
    return {"message": "All imported analytics records and student profiles were deleted. Your account remains active."}

@app.delete("/api/v1/account")
async def delete_account(request: Request, user: User = Depends(require_role(["owner"])), db: Session = Depends(db_session)):
    """Permanently deletes the entire centre account and all associated entities (SEC-011)."""
    body = await request.json()
    if body.get("confirmation") != "DELETE":
        raise HTTPException(400, "Type DELETE to permanently remove this account and all of its data.")
    tenant_id = user.tenant_id
    db.query(Record).filter_by(tenant_id=tenant_id).delete()
    db.query(ImportJob).filter_by(tenant_id=tenant_id).delete()
    db.query(Student).filter_by(tenant_id=tenant_id).delete()
    db.query(PredictionHistory).filter_by(tenant_id=tenant_id).delete()
    db.query(AuditEvent).filter_by(tenant_id=tenant_id).delete()
    db.query(User).filter_by(tenant_id=tenant_id).delete()
    db.query(Tenant).filter_by(id=tenant_id).delete()
    db.commit()
    response = JSONResponse({"message": "Your centre account and all stored records were permanently deleted."})
    response.delete_cookie("classpulse_session")
    return response
