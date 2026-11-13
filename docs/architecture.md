# ClassPulse AI — System Architecture & Data Model

## 1. System Overview

ClassPulse AI is an enterprise coaching-centre intelligence and machine learning predictive platform designed to track student performance, forecast exam success probabilities, and provide actionable pedagogical recommendations.

```
                      +---------------------------------------+
                      |       Client Browser (Vanilla SPA)     |
                      | HTML5 / Modern CSS / Vanilla JavaScript|
                      +-------------------+-------------------+
                                          | HTTP / REST API (JWT Auth)
                                          v
                      +---------------------------------------+
                      |          FastAPI Application          |
                      |   - Auth & Session Engine (bcrypt)    |
                      |   - Rate Limiter & Security Headers   |
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
+-------------------------+ +-------------------------+ +-------------------------+
             |                           |                             |
             +---------------------------+-----------------------------+
                                         | SQLAlchemy ORM
                                         v
                      +---------------------------------------+
                      |        Relational Database Layer      |
                      |     SQLite (Local) / MySQL (Cloud)    |
                      +---------------------------------------+
```

---

## 2. Multi-Tenancy & Security Isolation

- **Tenant Boundary (SEC-012):** Every database query filters by `tenant_id` extracted from authenticated and cryptographically verified JWT tokens. Cross-tenant leakage is strictly prevented.
- **Password Security (SEC-001):** Passwords hashed via standard `bcrypt` with automatic salting (12 rounds).
- **Session Tokens (SEC-003):** Signed `HS256` JSON Web Tokens carrying `sub`, `uid`, `tid`, and `role` claims, stored securely in HTTP-only cookies and supported via Bearer Authorization headers.
- **Rate Limiting (SEC-008):** In-memory sliding window rate limiter prevents credential-stuffing and brute-force attacks on login and registration endpoints.

---

## 3. Normalized Database Schema (DB-001 to DB-009)

The platform supports both historical flexible JSON ingestion (`records` table) and normalized first-class entities:

### `tenants`
- `id`: Integer Primary Key
- `name`: Centre Name
- `created_at`: Timestamp

### `users`
- `id`: Integer Primary Key
- `tenant_id`: Foreign Key (`tenants.id`)
- `email`: Unique String
- `password_hash`: Bcrypt string
- `full_name`: User name
- `role`: Role (`owner`, `admin`, `teacher`, `viewer`)
- `is_active`: Boolean
- `created_at`: Timestamp
- `last_login_at`: Timestamp

### `students`
- `id`: Integer Primary Key
- `tenant_id`: Foreign Key (`tenants.id`)
- `student_id`: Unique Student Identifier within centre
- `name`: Student Name
- `course_id`: Target Examination / Course (e.g., JEE, NEET)
- `batch_id`: Batch Identifier
- `created_at`: Timestamp
- `updated_at`: Timestamp

### `prediction_history`
- `id`: Integer Primary Key
- `tenant_id`: Foreign Key (`tenants.id`)
- `student_id`: Student Identifier
- `pass_probability`: Predicted probability percentage (0-100)
- `risk_level`: `High Risk`, `Borderline`, or `Safe`
- `predicted_outcome`: Binary classification (`Likely Pass` / `At Risk`)
- `avg_mock_score`: Logged mock score at time of prediction
- `attendance_rate`: Attendance percentage at time of prediction
- `financial_risk_level`: Independent financial standing
- `model_version`: Exact version of model used
- `factors_json`: Contributing factor breakdown
- `created_at`: Timestamp

### `import_jobs` & `records`
- Preserves raw spreadsheet data, row validation counts, and original unstructured historical logs.

### `audit_events`
- Immutable administrative action logging for compliance and auditing.
