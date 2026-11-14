# ClassPulse AI — System Architecture & Data Model (v2.0 Hardened)

## 1. System Overview

ClassPulse AI is an enterprise coaching-centre intelligence and machine learning predictive platform designed to track student performance, forecast exam success probabilities, and provide actionable pedagogical recommendations.

```
                      +---------------------------------------+
                      |       Client Browser (Vanilla SPA)     |
                      | HTML5 / Modern CSS / Vanilla JavaScript|
                      +-------------------+-------------------+
                                          | HTTP / REST API (JWT Auth + CSRF)
                                          v
                      +---------------------------------------+
                      |          FastAPI Application          |
                      |   - Auth & Session Engine (bcrypt)    |
                      |   - Cryptographic JWT Signer (HS256)  |
                      |   - Double-Submit CSRF Protection     |
                      |   - Shared Sliding-Window Rate Limiter|
                      |   - Multi-Tenant Boundary Enforcement |
                      |   - Dynamic Role-Based Access Control |
                      +----+-------------+---------------+----+
                           |             |               |
             +-------------+             |               +-------------+
             v                           v                             v
+-------------------------+ +-------------------------+ +-------------------------+
|     Analytics Engine    | |    Scikit-learn Engine  | |   ReportLab PDF Engine  |
| - KPI Aggregation       | | - Random Forest Clf     | | - Student 360° Report   |
| - Matplotlib Visuals    | | - Pure Academic Model   | | - Cohort Executive      |
| - Universal Sheet Ingest| | - Independent Finances  | |   Summary Report        |
| - Persisted Previews    | | - Benchmark Provenance  | | - Model Provenance Note |
+-------------------------+ +-------------------------+ +-------------------------+
             |                           |                             |
             +---------------------------+-----------------------------+
                                         | SQLAlchemy ORM / Alembic Migrations
                                         v
                      +---------------------------------------+
                      |        Relational Database Layer      |
                      |     SQLite (Local) / MySQL (Cloud)    |
                      +---------------------------------------+
```

---

## 2. Multi-Tenancy & Security Isolation

- **Tenant Boundary (SEC-012, SEC-TEN-01):** Every database query strictly filters by `tenant_id` extracted from authenticated and cryptographically verified JWT tokens. Cross-tenant leakage is strictly prevented across all data endpoints, student search, exports, backups, and ML predictions.
- **Password Security (SEC-001):** Passwords hashed via standard `bcrypt` with automatic salting (12 rounds). Legacy PBKDF2 hashes are verified and seamlessly upgraded upon login.
- **JWT Signing-Key Remediation (SEC-JWT-01 to SEC-JWT-06):**
  - All hardcoded signing keys and insecure fallbacks have been eliminated.
  - In production (`APP_ENV=production`), the application fails closed on startup if `JWT_SECRET_KEY` is missing, shorter than 32 characters, or matches any known compromised key.
  - The previously exposed key (`classpulse-super-secure-production-jwt-key-2026-deb-prasad`) is actively blocklisted. Any token presented with this signature is rejected with HTTP 401.
  - Algorithms are strictly enforced to `HS256`. Unsigned tokens (`alg: none`) and algorithm confusion attacks (e.g., asymmetric confusion or unauthorized symmetric algorithms) are rejected.
  - Every token carries standard claims: `sub`, `uid`, `tid`, `email`, `role`, `iat`, `exp`, `iss`, `aud`, and `jti`.
- **Token Revocation & Session Management (FR-AUTH-04, FR-AUTH-05, SEC-TOK-05):**
  - Explicit logout adds the token's unique `jti` to the `revoked_tokens` table until token expiration.
  - Password changes update `password_changed_at` on the `User` record, invalidating all older sessions issued before that timestamp.
  - Account deactivation (`is_active = False`) terminates all session access immediately.
- **CSRF Protection (SEC-CSRF-01, SEC-CSRF-02):**
  - Cookie-authenticated state-changing requests (POST, PUT, PATCH, DELETE) require a matching `X-CSRF-Token` header corresponding to the `classpulse_csrf` cookie.
  - Direct API clients using `Authorization: Bearer <token>` bypass ambient cookie CSRF checks.
- **Rate Limiting (SEC-008, SEC-RATE-01):**
  - Database-backed sliding-window rate limiting in `rate_limits` table ensures rate limiting functions reliably across multiple workers or server restarts.

---

## 3. Relational Database Schema & Migrations

Database schema versioning is managed via **Alembic**.

### Schema Tables:

1. `tenants`: Primary institutional tenant record (`id`, `name`, `created_at`).
2. `users`: System users with RBAC roles (`owner`, `admin`, `teacher`, `viewer`), password hash, active status, and audit timestamps.
3. `students`: First-class normalized student records per tenant.
4. `records`: Historical and event-level JSON data logs (enquiries, attendance, exam marks, fees).
5. `import_jobs`: Audit records of completed spreadsheet upload jobs.
6. `import_previews`: Persisted staging area for spreadsheet imports, enabling multi-worker preview inspections and idempotent confirmations.
7. `prediction_history`: Longitudinal audit trail of ML predictions per student with risk category, model version, and data provenance.
8. `audit_events`: Security and operational audit log tracking user creations, password updates, backups, and imports.
9. `revoked_tokens`: Stores revoked token `jti` identifiers with expiration timestamps.
10. `rate_limits`: Timestamped rate-limit attempt tracking per IP/key.
