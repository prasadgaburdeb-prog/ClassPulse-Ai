# ClassPulse AI — Deployment Guide & Production Configuration

## 1. Environment Requirements

- **Python Version:** 3.11+ (Fully verified on Python 3.14)
- **Supported Databases:**
  - SQLite (Embedded file-based, default for single-node / development)
  - MySQL / MariaDB (Recommended for multi-worker production deployments)
- **Operating Systems:** Windows 10/11, Ubuntu 22.04 LTS+, Debian, macOS

---

## 2. Environment Variables Configuration

Create a `.env` file in the project root:

```ini
# Environment
ENV=production

# Database Configuration (DEP-002, DEP-003)
# For SQLite (default):
DATABASE_URL=sqlite:///./classpulse.db

# For MySQL (Production):
# DATABASE_URL=mysql+pymysql://username:password@127.0.0.1:3306/classpulse?charset=utf8mb4

# Security Secrets (SEC-002)
# Generate a strong 32-character key: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=c3f19a089e02c610996fbdeca6bc444857b22031c19b0d2d38eac4b2383c2e17

# Cookie & Domain Security (SEC-005, SEC-015)
COOKIE_SECURE=true
ALLOWED_ORIGINS=https://classpulse.yourdomain.edu,https://app.yourdomain.edu
```

---

## 3. Installation & Startup

```bash
# Clone the repository
git clone https://github.com/your-org/ClassPulse-Ai.git
cd ClassPulse-Ai

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run database schema migrations
python -c "from app.main import ensure_database_migrations; ensure_database_migrations()"

# Run automated test suite
python -m pytest tests -v

# Start production server with Uvicorn
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 4. Production Security Checklist

- [x] Passwords hashed with `bcrypt` (12 rounds)
- [x] JWT tokens with 24-hour expiration (`HS256`)
- [x] Sliding-window rate limiting on login/registration endpoints
- [x] Multi-tenant scoping enforced on every ORM query
- [x] Dynamic Role-Based Access Control (`owner`, `admin`, `teacher`, `viewer`)
- [x] CSRF protection for session cookies
- [x] No-cache headers on dynamic analytical data
- [x] Automated database backup endpoint (`/api/v1/admin/backup`)
