# ClassPulse AI — Deployment Guide & Production Configuration (v2.0 Hardened)

## 1. System Requirements

- **Python Version:** 3.11+ (Verified on Python 3.14)
- **Supported Databases:**
  - SQLite (Local single-node development & testing: `sqlite:///./classpulse.db`)
  - PostgreSQL / MySQL (Production multi-worker deployments: `mysql+pymysql://...` or `postgresql+psycopg2://...`)
- **Supported OS:** Windows 10/11, Ubuntu 22.04 LTS+, Debian 12+, macOS

---

## 2. Environment Variables Configuration

Create a `.env` file in the project root based on `.env.example`:

```ini
# Application Environment
APP_ENV=production
DEBUG=false

# Database Configuration
DATABASE_URL=sqlite:///./classpulse.db

# Cryptographic JWT Signing Key (Mandatory in production, >= 32 characters)
# Generate via: python -c "import secrets; print(secrets.token_urlsafe(64))"
JWT_SECRET_KEY=replace-with-a-secure-random-64-character-secret-in-production

# JWT Claims Configuration
JWT_ALGORITHM=HS256
JWT_ISSUER=classpulse-ai
JWT_AUDIENCE=classpulse-client
ACCESS_TOKEN_TTL_MINUTES=30

# Cookie & CSRF Security
COOKIE_SECURE=true
COOKIE_SAMESITE=lax

# Allowed CORS Origins (comma-separated, wildcards rejected in production)
CORS_ALLOWED_ORIGINS=https://classpulse.yourdomain.edu,https://app.yourdomain.edu

# File Upload Limit (MB)
MAX_UPLOAD_MB=15
```

> [!WARNING]
> Never use the compromised key `classpulse-super-secure-production-jwt-key-2026-deb-prasad`. The application will immediately abort startup if this key is detected in production.

---

## 3. Database Migrations (Alembic)

ClassPulse AI uses Alembic for controlled, versioned database schema migrations:

```bash
# Check current migration revision
alembic current

# Run all pending migrations
alembic upgrade head

# Rollback to baseline schema if needed
# alembic downgrade 001_initial_schema
```

---

## 4. Zero-Downtime Key Rotation Runbook (SEC-JWT-04)

When rotating the JWT signing key:

1. **Generate New Key:**
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(64))"
   ```
2. **Scheduled Rotation Window:**
   - In low-traffic hours, update `JWT_SECRET_KEY` in your environment management system (or secret manager).
   - Because active access tokens expire within `ACCESS_TOKEN_TTL_MINUTES` (default: 30 minutes), users will smoothly re-authenticate.
3. **Emergency Invalidation of Compromised Keys:**
   - If a key exposure is suspected, add the compromised key to `COMPROMISED_KEYS` in `app/main.py`.
   - The application automatically rejects all tokens signed with that key, forcing immediate re-authentication.

---

## 5. Startup and Execution

```bash
# Install dependencies
pip install -r requirements.txt

# Execute automated test suite
pytest tests -v

# Run production server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```
