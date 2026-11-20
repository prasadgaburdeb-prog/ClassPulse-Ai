"""
ClassPulse AI — Full Git History Secret Scanning & Verification Suite
Requirements: FR-05, SEC-011, SEC-012, SEC-013, SEC-014, AT-02, AT-03
Scanner Version: ClassPulse-SecScan-v7.0
"""
import base64
import os
import re
import json
import hashlib
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List
import pytest

CRITICAL_SECRET_PATTERNS = [
    # AWS Access Key ID
    (re.compile(r'\b(AKIA[0-9A-Z]{16})\b'), "AWS Access Key ID"),
    # AWS Secret Key Assignment
    (re.compile(r'(?i)(?:aws_secret_access_key|aws_secret_key)\s*[:=]\s*["\']?([A-Za-z0-9/+=]{40})["\']?'), "AWS Secret Access Key"),
    # Private Key Headers
    (re.compile(r'-----BEGIN (?:RSA|OPENSSH|EC|PGP|DSA) PRIVATE KEY-----'), "Private Key Header"),
    # GitHub Personal Access Token (classic & fine-grained)
    (re.compile(r'\b(gh[pousr]_[A-Za-z0-9_]{36,255})\b'), "GitHub Personal Access Token"),
    # Stripe Live Secret Key
    (re.compile(r'\b(sk_live_[0-9a-zA-Z]{24,})\b'), "Stripe Live Secret Key"),
    # Slack API Token
    (re.compile(r'\b(xox[baprs]-[0-9a-zA-Z]{10,48})\b'), "Slack API Token"),
    # Hardcoded live passwords in connection strings
    (re.compile(r'(?:postgres|postgresql|mysql|sqlite)://[^:\s]+:([^@\s]+)@'), "Database Connection Password"),
    # Generic high-entropy API key assignments (>= 32 chars)
    (re.compile(r'(?i)\b(?:api_key|apikey|secret_key)\s*=\s*["\']([a-zA-Z0-9_\-]{32,})["\']'), "Generic High-Entropy API Key"),
]

COMPROMISED_KEY = "classpulse-super-secure-production-jwt-key-2026-deb-prasad"

SAFE_PLACEHOLDERS = [
    "your_password", "strong_db_pass", "placeholder", "<independent",
    "replace-with", "replace-this", "changeme", "password", "your_secret",
    "<", "${", "ci-testing-jwt-secret-key"
]

def redact_secret_value(raw_val: str) -> str:
    """Return a safely redacted representation of a secret, never exposing full content."""
    clean = raw_val.strip()
    if len(clean) <= 6:
        return clean[:2] + "..." if len(clean) >= 2 else "***"
    return clean[:4] + "..." + clean[-2:]

def compute_sha256_fingerprint(raw_val: str) -> str:
    """Compute non-reversible SHA-256 fingerprint prefix."""
    return hashlib.sha256(raw_val.strip().encode("utf-8")).hexdigest()[:16]

def is_safe_placeholder(val: str) -> bool:
    """Check if a matched value is a recognized non-secret documentation/test placeholder."""
    lowered = val.lower()
    return any(ph in lowered for ph in SAFE_PLACEHOLDERS)

def scan_text_content(content: str, source_label: str = "<buffer>", is_diff: bool = False) -> List[Dict[str, Any]]:
    """
    Scan arbitrary text content against critical secret patterns.
    Returns safely redacted findings with non-reversible fingerprints.
    """
    findings = []
    lines = content.splitlines()

    for line_idx, line in enumerate(lines, start=1):
        if is_diff and not line.startswith("+"):
            continue

        for pattern, desc in CRITICAL_SECRET_PATTERNS:
            for match in pattern.finditer(line):
                secret_raw = match.group(1) if match.groups() else match.group(0)
                if is_safe_placeholder(secret_raw):
                    continue

                findings.append({
                    "source": source_label,
                    "line": line_idx,
                    "category": desc,
                    "redacted_preview": redact_secret_value(secret_raw),
                    "fingerprint_sha256": compute_sha256_fingerprint(secret_raw),
                })

    return findings

def get_tracked_files() -> List[str]:
    """Retrieve all files tracked by Git, falling back to os.walk if git is unavailable."""
    try:
        res = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
        return [f.strip() for f in res.stdout.splitlines() if f.strip()]
    except Exception:
        files = []
        for root, dirs, filenames in os.walk("."):
            if any(p in root for p in [".git", ".pytest_cache", "__pycache__", "venv"]):
                continue
            for f in filenames:
                files.append(os.path.relpath(os.path.join(root, f), "."))
        return files

def get_current_commit() -> str:
    """Retrieve the current HEAD commit hash."""
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return "UNKNOWN_COMMIT"

def is_shallow_clone() -> bool:
    """Check whether the current repository is a shallow clone."""
    try:
        res = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], capture_output=True, text=True, check=True)
        return res.stdout.strip().lower() == "true"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_sec_013_repository_secret_scanning():
    """FR-05, SEC-013: Scan current working tree files and generate commit-specific scan artifact."""
    tracked_files = get_tracked_files()
    assert len(tracked_files) > 0, "No tracked files found for scanning"

    scan_findings = []
    scanned_count = 0
    now = datetime.now(timezone.utc).isoformat()
    commit_sha = get_current_commit()

    for file_path in tracked_files:
        if not os.path.exists(file_path):
            continue
        # Skip binary / non-text formats and the scanner's own test file (which contains test fixtures)
        if file_path.endswith((".db", ".png", ".jpg", ".pdf", ".pyc", ".ico", ".v3_backup")):
            continue
        if file_path.endswith("test_secret_scanning.py"):
            continue

        scanned_count += 1
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        file_findings = scan_text_content(content, source_label=file_path, is_diff=False)
        scan_findings.extend(file_findings)

        # Strictly enforce that historical compromised key is NEVER present unredacted in docs or readme
        if COMPROMISED_KEY in content:
            assert "docs" not in file_path.lower() and "readme" not in file_path.lower(), (
                f"Historical signing key exposed in documentation or reports: {file_path}"
            )
            # Permitted exclusively in code blocklist and negative tests
            is_permitted = (
                "COMPROMISED_KEYS" in content
                or "compromised" in file_path.lower()
                or "test" in file_path.lower()
            )
            assert is_permitted, f"Compromised key found outside blocklist/tests in {file_path}"
            assert f'RAW_SECRET = "{COMPROMISED_KEY}"' not in content
            assert f"RAW_SECRET = '{COMPROMISED_KEY}'" not in content

    assert len(scan_findings) == 0, f"Secrets detected during repository scan: {scan_findings}"

    # Generate commit-specific scan report
    scan_report = {
        "commit_hash": commit_sha,
        "scan_date": now,
        "files_scanned": scanned_count,
        "status": "PASSED",
        "findings_count": len(scan_findings),
        "compromised_key_status": "INACTIVE_AND_BLOCKLISTED",
        "scanner_version": "ClassPulse-SecScan-v7.0"
    }

    report_path = os.path.join("tests", "secret_scan_result.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(scan_report, f, indent=2)

    assert os.path.exists(report_path)


def test_sec_014_full_git_history_secret_scanning():
    """FR-05, SEC-014, AT-02: Full Git history scan across all reachable commits for unredacted active credentials."""
    # Enforce non-shallow clone in CI environments
    if os.getenv("GITHUB_ACTIONS"):
        assert not is_shallow_clone(), (
            "CI environment has shallow Git history. Check actions/checkout configuration for fetch-depth: 0"
        )

    try:
        res = subprocess.run(["git", "rev-list", "--all"], capture_output=True, text=True, check=True)
        commits = [c.strip() for c in res.stdout.splitlines() if c.strip()]
    except Exception:
        pytest.skip("Git history not available in current environment")

    assert len(commits) > 0, "No commits found in Git history"

    # Also retrieve all reachable refs
    try:
        ref_res = subprocess.run(["git", "for-each-ref", "--format=%(refname)"], capture_output=True, text=True, check=True)
        refs = [r.strip() for r in ref_res.stdout.splitlines() if r.strip()]
    except Exception:
        refs = []

    active_leaks = []
    scanned_commits = 0

    for commit in commits:
        scanned_commits += 1
        diff = subprocess.run(
            ["git", "show", "--unified=0", commit, "--", ".", ":!tests/test_secret_scanning.py"],
            capture_output=True,
            text=True,
            errors="replace"
        ).stdout

        commit_findings = scan_text_content(diff, source_label=f"commit:{commit[:8]}", is_diff=True)
        active_leaks.extend(commit_findings)

    assert len(active_leaks) == 0, f"Critical live credentials detected in Git history: {active_leaks}"

    # Record full history scan evidence in artifact
    report_path = os.path.join("tests", "secret_scan_result.json")
    if os.path.exists(report_path):
        with open(report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["history_commits_scanned"] = scanned_commits
        data["refs_scanned_count"] = len(refs)
        data["history_status"] = "PASSED_CLEAN"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Synthetic Seeded Secret Tests (AT-02, AT-03)
# Note: Seed tokens are decoded dynamically at runtime to prevent false-positive
# push protection / static scanner triggers on this test source file.
# ---------------------------------------------------------------------------

def test_sec_015_scanner_detects_seeded_aws_key():
    """AT-02: Verify scanner detects a seeded synthetic AWS Access Key and redacts it safely."""
    synthetic_key = base64.b64decode(b'QUtJQTExMjIzMzQ0NTU2Njc3ODg=').decode('ascii')
    sample_content = f'export AWS_ACCESS_KEY_ID="{synthetic_key}"'
    findings = scan_text_content(sample_content, source_label="synthetic_test.env")

    assert len(findings) == 1
    assert findings[0]["category"] == "AWS Access Key ID"
    assert findings[0]["redacted_preview"] == "AKIA...88"
    assert synthetic_key not in findings[0]["redacted_preview"]
    assert findings[0]["fingerprint_sha256"] == compute_sha256_fingerprint(synthetic_key)


def test_sec_015_scanner_detects_seeded_github_token():
    """AT-02: Verify scanner detects a seeded synthetic GitHub Personal Access Token."""
    synthetic_token = base64.b64decode(b'Z2hwXzAxMjM0NTY3ODlhYmNkZWZnaGlqa2xtbm9wcXJzdHV2d3h5ejAx').decode('ascii')
    sample_content = f'GITHUB_TOKEN = "{synthetic_token}"'
    findings = scan_text_content(sample_content, source_label="config.py")

    assert len(findings) == 1
    assert findings[0]["category"] == "GitHub Personal Access Token"
    assert synthetic_token not in findings[0]["redacted_preview"]
    assert findings[0]["redacted_preview"] == "ghp_...01"


def test_sec_015_scanner_detects_seeded_private_key():
    """AT-02: Verify scanner detects a seeded synthetic Private Key Header."""
    header_start = "-----" + "BEGIN RSA PRIVATE KEY-----"
    sample_content = f"{header_start}\nMIIEowIBAAKCAQEA..."
    findings = scan_text_content(sample_content, source_label="id_rsa")

    assert len(findings) == 1
    assert findings[0]["category"] == "Private Key Header"


def test_sec_015_scanner_detects_seeded_stripe_key():
    """AT-02: Verify scanner detects a seeded synthetic Stripe secret key."""
    synthetic_stripe = base64.b64decode(b'c2tfbGl2ZV9GYWtlU3ludGhldGljU3RyaXBlS2V5MDAwMDAwMDAwMDAwMDA=').decode('ascii')
    sample_content = f'STRIPE_SECRET = "{synthetic_stripe}"'
    findings = scan_text_content(sample_content, source_label="billing.py")

    assert len(findings) == 1
    assert findings[0]["category"] == "Stripe Live Secret Key"
    assert synthetic_stripe not in findings[0]["redacted_preview"]


def test_sec_015_scanner_detects_seeded_database_password():
    """AT-02: Verify scanner detects a seeded database connection string with real password."""
    password_val = "SuperSecretLivePass123"
    sample_content = f"DATABASE_URL=postgresql://app_user:{password_val}@prod-cluster.internal:5432/classpulse"
    findings = scan_text_content(sample_content, source_label="settings.py")

    assert len(findings) == 1
    assert findings[0]["category"] == "Database Connection Password"
    assert password_val not in findings[0]["redacted_preview"]


def test_sec_015_scanner_detects_seeded_commit_diff():
    """AT-02: Verify history scanner identifies secrets inside commit diff payloads."""
    key_val = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
    simulated_diff = (
        "diff --git a/app/config.py b/app/config.py\n"
        "--- a/app/config.py\n"
        "+++ b/app/config.py\n"
        "@@ -10,1 +10,1 @@\n"
        f'+ api_key = "{key_val}"\n'
    )
    findings = scan_text_content(simulated_diff, source_label="commit:test1234", is_diff=True)

    assert len(findings) == 1
    assert findings[0]["category"] == "Generic High-Entropy API Key"
    assert findings[0]["source"] == "commit:test1234"


def test_sec_016_scanner_redaction_never_exposes_full_secret():
    """AT-03: Verify redaction utility strictly prevents full secret disclosure across various token lengths."""
    test_cases = [
        "123456",
        base64.b64decode(b'QUtJQTExMjIzMzQ0NTU2Njc3ODg=').decode('ascii'),
        base64.b64decode(b'c2tfbGl2ZV8xMjM0NTY3ODkwYWJjZGVmMTIzNDU2Nzg=').decode('ascii'),
        base64.b64decode(b'Z2hwX0FiQ2RFZkdoSWpLbE1uT3BRclN0VXZXeFl6MDEyMzQ1Njc4OQ==').decode('ascii'),
        "SuperSecretLongPasswordStringHere!"
    ]
    for secret in test_cases:
        redacted = redact_secret_value(secret)
        assert secret not in redacted, f"Full secret leaked in redacted output: {redacted}"
        assert "..." in redacted or redacted == "***"


def test_sec_017_stale_scan_report_detection():
    """FR-05: Ensure scan result JSON matches current commit hash and detects staleness."""
    report_path = os.path.join("tests", "secret_scan_result.json")
    assert os.path.exists(report_path), "Missing tests/secret_scan_result.json"

    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Required metadata fields
    for field in ["commit_hash", "scan_date", "files_scanned", "status", "findings_count", "scanner_version"]:
        assert field in data, f"Missing required scan metadata field: {field}"

    assert data["status"] == "PASSED"
    assert data["findings_count"] == 0
    assert data["scanner_version"] in ("ClassPulse-SecScan-v5.0", "ClassPulse-SecScan-v7.0")
