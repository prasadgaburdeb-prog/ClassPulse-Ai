# ClassPulse AI — Full Git History Secret Review Report
**SRS v5.0 Deliverable D-02 | Requirements: FR-SEC-01 to FR-SEC-06**  
**Audit Date:** 18 November 2026  
**Scanner Version:** ClassPulse-SecScan-v5.0  

---

## 1. Executive Summary

A comprehensive, history-aware cryptographic and credential scan was executed across all reachable commits in the Git repository history. The scan examined all 30 reachable commits across branches and references, analyzing commit diffs, tree snapshots, and deleted files.

- **Total Commits Evaluated:** 30 reachable commits
- **Tracked Working Tree Files Scanned:** 47 text files
- **Active Production Credentials Leaked:** **ZERO (0)**
- **Cloud Provider Credentials (AWS/GCP/Azure/Stripe/Slack):** **ZERO (0)**
- **Compromised Key Disposition:** 1 historical fallback JWT key (`classpulse-super-secure-...`) introduced in commit `cca0eea` was subsequently removed in commit `1d9d96b`, permanently blocklisted in `COMPROMISED_KEYS` in `app/main.py`, rejected with HTTP 401 across all endpoints, and verified via automated test suites.
- **Git History Rewriting Recommendation:** **DO NOT REWRITE**. Rewriting history is neither necessary nor justified: the key is permanently blocklisted in code and test fixtures, poses zero live risk, and rewriting would disrupt collaborator forks and repository traceability.

---

## 2. History Scan Scope & Coverage

| Metric | Inspected Scope |
| :--- | :--- |
| **Commit Reachability** | `git rev-list --all` (100% of all reachable commit objects) |
| **Commit Count** | 30 commits |
| **Branches Evaluated** | `main`, `srs_v5_remediation`, `fix/core-remediation-v3`, `improvement/srs-v2-hardening` |
| **File Filters** | All source text files scanned; binary artifacts (`.db`, `.png`, `.jpg`, `.pdf`, `.v3_backup`) excluded |
| **Pattern Categories** | AWS Keys, Private Key Headers, Live DB Passwords, Cloud Tokens, High-Entropy Secret Assignments |

---

## 3. Findings Inventory & Dispositions

| Finding ID | Commit (Short SHA) | File / Path | Category | Classification | Redacted Context / Disposition |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SEC-F01** | `cca0eea` | `app/main.py` | JWT Secret Key | **Inactive / Revoked** | Fallback key `classpulse-super-secure...` introduced as default fallback. Removed in `1d9d96b`, placed into `COMPROMISED_KEYS` blocklist. Zero live validity. |
| **SEC-F02** | `c6c6f89` | `docs/deployment.md` | DB Connection String | **False Positive (Documentation)** | Sample connection string `...://root:password@127.0.0.1...` used as documentation placeholder. |
| **SEC-F03** | `99ba2cf`, `37354be` | `.env.example`, `docs/deployment.md` | DB Connection String | **False Positive (Template)** | Documentation placeholders `...://classpulse_user:STRONG_DB_PASS@...` and `...://root:YOUR_PASSWORD@...`. |
| **SEC-F04** | `1d9d96b`, `1861ccd` | `tests/test_jwt_lifecycle.py`, `tests/test_srs_v2.py` | Test Secret Fixture | **False Positive (Test Fixture)** | Synthetic test keys used strictly within unit test suites to verify token parsing, tampering, and key length validation. |
| **SEC-F05** | `1861ccd` | `.github/workflows/ci.yml` | JWT Secret Key | **False Positive (CI Dummy)** | CI workflow dummy key `ci-testing-jwt-secret-key-...` used exclusively for ephemeral Ubuntu pytest runner. |

---

## 4. Credential Rotation & Invalidation Status

- **Live Production Secrets:** None exposed. No cloud provider API keys, AWS credentials, or live database connection strings have ever been committed.
- **Historical Fallback Key:**
  - **Key Identifier:** `classpulse-super-secure-production-jwt-key-2026-deb-prasad`
  - **Issuing Service:** Internal application JWT signing engine.
  - **Current Status:** Permanently blocklisted in `COMPROMISED_KEYS` (`app/main.py:61`).
  - **Enforcement:** `decode_token()` actively verifies signatures against this string and raises `HTTP 401 Unauthorized` with message `"Token was signed with a compromised signing key."`
  - **Validation Evidence:** Automated regression tests `test_at_jwt_06_compromised_key_rejected` and `test_sec_010_token_revocation_replay_rejected` pass.

---

## 5. History Rewriting Assessment (FR-SEC-05)

- **Option Considered:** Force-pushing a rewritten Git history using `git-filter-repo` or `git rebase`.
- **Engineering Recommendation:** **REJECTED / UNNECESSARY**.
  - The historical secret was never a live cloud or production credential.
  - The key is actively blocklisted in the source code; even if an attacker obtained this string from history, the server explicitly rejects tokens signed with it.
  - Force-pushing would rewrite all 30 commit SHAs, break existing clone worktrees, and destroy verification audit trails.
