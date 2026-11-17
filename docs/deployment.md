# ClassPulse AI — Deployment Guide & Production Configuration (v3.0 Remediated)

This guide documents the procedures for local development and multi-worker production deployments of ClassPulse AI, including secret management, shared rate limiting, Alembic schema migrations, and deployment checklists per SRS v3.0 requirements.

---

## 1. System Requirements & Runtime Environment

- **Python Runtime:** Python 3.11+ (Verified on Python 3.14.4)
- **Supported Databases:**
  - **Local Development / Single-node Testing:** SQLite (`sqlite:///./classpulse.db`)
  - **Multi-Worker Production:** PostgreSQL (`postgresql+psycopg2://...`) or MySQL (`mysql+pymysql://...`)
- **Web Server:** Uvicorn / Gunicorn with ASGI workers
- **Operating Systems:** Ubuntu 22.04 LTS+, Debian 12+, Windows Server 2022+, macOS Sonoma+

---

## 2. Configuration Profiles (FR-DEP-01)

### A. Local Development Profile (`APP_ENV=development`)

In local development, the server permits automatic fallback to ephemeral keys and process-local memory rate limiting if external stores are not configured:

```ini
APP_ENV=development
DEBUG=true
DATABASE_URL=sqlite:///./classpulse.db

# Ephemeral key is automatically generated on startup if omitted in development:
JWT_SECRET_KEY=
JWT_ALGORITHM=HS256
JWT_ISSUER=classpulse-ai
JWT_AUDIENCE=classpulse-client
ACCESS_TOKEN_TTL_MINUTES=60

# HTTP cookies permitted locally on localhost:
COOKIE_SECURE=false
COOKIE_SAMESITE=lax

CORS_ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
MAX_UPLOAD_MB=15
```

### B. Production Multi-Worker Profile (`APP_ENV=production`) (FR-DEP-02, FR-DEP-04)

In production, security controls **fail closed**. Startup aborts immediately if required configuration is missing, weak, or placeholder:

```ini
APP_ENV=production
DEBUG=false

# Multi-worker shared database (enables shared rate_limits and persisted import previews):
DATABASE_URL=mysql+pymysql://classpulse_user:STRONG_DB_PASS@db-cluster.internal:3306/classpulse?charset=utf8mb4

# Cryptographically random signing secret (Mandatory, >= 32 characters high-entropy):
# Example placeholder text is strictly rejected; generate an independent secret per environment!
JWT_SECRET_KEY=<INDEPENDENT_RANDOMLY_GENERATED_64_CHAR_HEX_OR_BASE64_SECRET>

JWT_ALGORITHM=HS256
JWT_ISSUER=classpulse-ai
JWT_AUDIENCE=classpulse-client
ACCESS_TOKEN_TTL_MINUTES=30
LEGACY_TOKEN_SUNSET_DATE=2026-12-31T23:59:59Z

# Secure cookies strictly enforced (requires HTTPS):
COOKIE_SECURE=true
COOKIE_SAMESITE=lax

# Explicit allowed browser origins (no wildcards permitted):
CORS_ALLOWED_ORIGINS=https://classpulse.institution.edu,https://analytics.institution.edu

MAX_UPLOAD_MB=15
```

> [!CAUTION]
> **FR-DEP-04 / AT-08 Warning:** Example placeholders (such as `replace-with-a-secure-random...` or `your-secret-key-here`) are non-usable and actively detected by the production validator. Production startup will raise a fatal `RuntimeError` if any placeholder is used. Always generate an independent key.

---

## 3. Secret Generation & Rotation Runbook (FR-JWT-01 to FR-JWT-05)

### Generating a High-Entropy Secret
Generate a new 64-character URL-safe random key using Python's standard cryptographic library:
```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### Routine Secret Rotation
1. **Prepare New Secret:** Store the new secret in your cloud key management service (e.g. AWS Secrets Manager, HashiCorp Vault, Azure Key Vault).
2. **Scheduled Low-Traffic Window:** Update `JWT_SECRET_KEY` on all worker instances.
3. **Graceful User Re-Authentication:** Active sessions expire within `ACCESS_TOKEN_TTL_MINUTES` (30 minutes). Upon key rotation, older tokens will be rejected, and users seamlessly sign in again.

### Emergency Key Invalidation (Compromised Key Protocol)
If a signing secret is suspected of exposure:
1. Immediately generate and deploy a fresh random secret.
2. Ensure the compromised string is registered in `COMPROMISED_KEYS` in `app/main.py`.
3. The server immediately rejects any token signed with the compromised key with HTTP 401.

---

## 4. Database Migrations with Alembic (FR-MIG-01 to FR-MIG-05)

Alembic is the authoritative schema migration engine. Migrations run independently of application web workers:

```bash
# 1. Verify current database revision
alembic current

# 2. Apply all pending migrations before web process deployment
alembic upgrade head

# 3. If rollback is necessary:
# alembic downgrade 001_initial_schema
```

> [!IMPORTANT]
> Always run `alembic upgrade head` **before** rolling out new application worker processes.

---

## 5. Deployment Checklists (FR-DEP-03)

### Pre-Deployment Checklist
- [ ] Database backup executed and verified (e.g. `pg_dump` / `mysqldump` / SQLite copy).
- [ ] Fresh independent `JWT_SECRET_KEY` generated via `secrets.token_urlsafe(64)` and populated into secret store.
- [ ] Verified `JWT_SECRET_KEY` is not a placeholder, weak string, or previously exposed key.
- [ ] `APP_ENV=production` set in environment.
- [ ] `COOKIE_SECURE=true` set for HTTPS enforcement.
- [ ] `CORS_ALLOWED_ORIGINS` configured with explicit institutional domain(s) without wildcards (`*`).
- [ ] Shared database URL verified for multi-worker connection pooling.
- [ ] Automated regression test suite executed and 100% passing (`pytest -v`).

### Deployment Checklist
- [ ] Put application into maintenance mode or drain traffic from staging instance.
- [ ] Run authoritative schema migrations: `alembic upgrade head`.
- [ ] Verify migration version via `alembic current`.
- [ ] Deploy updated backend code and static assets.
- [ ] Start Uvicorn ASGI workers with multi-worker configuration:
  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --proxy-headers --forwarded-allow-ips='*'
  ```
- [ ] Check application startup logs: confirm successful boot without secret leakage or migration warnings.

### Post-Deployment Checklist
- [ ] Verify health and model info endpoint: `GET /api/v1/ml/model-info`.
- [ ] Perform smoke test: log in with supported administrative and faculty roles.
- [ ] Verify CSRF protection: confirm mutating POST requests require valid `X-CSRF-Token`.
- [ ] Verify rate limiting: confirm rate limits are enforced across workers.
- [ ] Verify spreadsheet upload: staging preview, column mapping, and import idempotency.
- [ ] Verify prediction generation and PDF report card downloads.

### Rollback Checklist (In Case of Deployment Failure)
- [ ] Revert application code / container image to previous release commit.
- [ ] If schema downgrade is necessary, inspect `alembic/versions/` and execute target downgrade:
  ```bash
  alembic downgrade <PREVIOUS_REVISION_ID>
  ```
- [ ] If database downgrade leaves mixed state, restore from pre-deployment backup:
  ```bash
  # Restore backup copy taken in pre-deployment step
  ```
- [ ] Restart application workers under previous release.
- [ ] Verify login and core services are fully functional.

---

## 6. Clean-Install Verification (AT-13)

To verify a clean installation in an isolated Python environment:

```bash
# 1. Create fresh virtual environment
python -m venv .venv_clean
source .venv_clean/bin/activate  # On Windows: .venv_clean\Scripts\activate

# 2. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 3. Run migrations on a clean database
export DATABASE_URL="sqlite:///./clean_install.db"
alembic upgrade head

# 4. Execute test suite
pytest -v

# 5. Start development server
uvicorn app.main:app --port 8000
```
