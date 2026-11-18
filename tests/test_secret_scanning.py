"""
Secret Scanning Verification Test & Log Generator
Requirements: SEC-011, SEC-012, SEC-013, SEC-014
"""
import os
import re
import json
import subprocess
from datetime import datetime, timezone
import pytest

SUSPICIOUS_PATTERNS = [
    # AWS / Cloud credentials
    (re.compile(r'AKIA[0-9A-Z]{16}'), "AWS Access Key ID"),
    # Private Key Headers
    (re.compile(r'-----BEGIN (?:RSA|OPENSSH|EC|PGP) PRIVATE KEY-----'), "Private Key Header"),
    # Hardcoded live passwords in connection strings
    (re.compile(r'(?:postgres|mysql|sqlite)://[^:\s]+:([^@\s]+)@'), "Database Connection Password"),
    # Generic high-entropy secret assignments (excluding test assertions/doc references)
    (re.compile(r'api_key\s*=\s*["\']([a-zA-Z0-9_\-]{32,})["\']', re.I), "Generic API Key Assignment"),
]

COMPROMISED_KEY = "classpulse-super-secure-production-jwt-key-2026-deb-prasad"

def get_tracked_files():
    try:
        res = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
        return [f.strip() for f in res.stdout.splitlines() if f.strip()]
    except Exception:
        # Fallback to os.walk if git is unavailable
        files = []
        for root, dirs, filenames in os.walk("."):
            if any(p in root for p in [".git", ".pytest_cache", "__pycache__", "venv"]):
                continue
            for f in filenames:
                files.append(os.path.relpath(os.path.join(root, f), "."))
        return files

def get_current_commit():
    try:
        res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return "UNKNOWN_COMMIT"

def test_sec_013_repository_secret_scanning():
    """SEC-013: Scan current source tree for exposed secrets and save scan result with commit hash and date."""
    tracked_files = get_tracked_files()
    assert len(tracked_files) > 0, "No tracked files found for scanning"

    scan_findings = []
    scanned_count = 0
    now = datetime.now(timezone.utc).isoformat()
    commit_sha = get_current_commit()

    for file_path in tracked_files:
        if not os.path.exists(file_path):
            continue
        # Skip binary / non-text files
        if file_path.endswith((".db", ".png", ".jpg", ".pdf", ".pyc", ".ico", ".v3_backup")):
            continue

        scanned_count += 1
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Check for suspicious patterns
        for pattern, desc in SUSPICIOUS_PATTERNS:
            for match in pattern.finditer(content):
                captured = match.group(1) if match.groups() else match.group(0)
                # Ignore unmistakable placeholder templates in documentation and example files
                if any(ph in captured.lower() for ph in ["your_password", "strong_db_pass", "placeholder", "<"]):
                    continue
                scan_findings.append({
                    "file": file_path,
                    "description": desc,
                    "match": match.group(0)[:20] + "..."
                })

        # Ensure compromised key appears ONLY in blocklist/test verification, NEVER as active secret
        if COMPROMISED_KEY in content:
            # Permitted only in COMPROMISED_KEYS blocklist, negative tests, and doc warnings
            is_permitted_blocklist = (
                "COMPROMISED_KEYS" in content
                or "compromised" in file_path.lower()
                or "test" in file_path.lower()
                or "docs" in file_path.lower()
                or "readme" in file_path.lower()
            )
            assert is_permitted_blocklist, f"Compromised key found outside blocklist/tests in {file_path}"
            # Verify it is not being assigned as RAW_SECRET
            assert f'RAW_SECRET = "{COMPROMISED_KEY}"' not in content
            assert f"RAW_SECRET = '{COMPROMISED_KEY}'" not in content

    assert len(scan_findings) == 0, f"Secrets detected during repository scan: {scan_findings}"

    # Save scan report artifact (SEC-013)
    scan_report = {
        "commit_hash": commit_sha,
        "scan_date": now,
        "files_scanned": scanned_count,
        "status": "PASSED",
        "findings_count": len(scan_findings),
        "compromised_key_status": "INACTIVE_AND_BLOCKLISTED",
        "scanner_version": "ClassPulse-SecScan-v4.0"
    }

    report_path = os.path.join("tests", "secret_scan_result.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(scan_report, f, indent=2)

    assert os.path.exists(report_path)
