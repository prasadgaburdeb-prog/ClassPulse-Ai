# ClassPulse AI — CI Warning Inventory & Remediation Report
**SRS v5.0 Deliverable D-04 | Requirements: FR-CI-01 to FR-CI-06**  
**Audit Date:** 18 November 2026  
**Status:** Remediated & Documented  

---

## 1. Summary of Warnings Baseline vs. Remediated

In the initial audit baseline, continuous integration jobs reported **93 warnings per Python job**. Following root-cause investigation and surgical code remediation, the warning count was reduced to **1 justified third-party dependency warning**.

| Metric | Pre-Remediation Baseline | Post-Remediation Status |
| :--- | :--- | :--- |
| **Total Warnings** | **93** | **1** |
| **Project-Induced Cryptographic Warnings** | 92 (`InsecureKeyLengthWarning`) | **0 (Eliminated via contextual scoping)** |
| **Third-Party Dependency Deprecations** | 1 (`StarletteDeprecationWarning`) | **1 (Documented justified remainder)** |
| **Total Test Count** | 53 tests passing | **56 tests passing (100%)** |
| **Global Warning Suppression** | None | **None (FR-CI-05 strictly adhered to)** |

---

## 2. Warning Categorization and Root-Cause Analysis

### Category 1: Project-Induced Cryptographic Warnings (92 occurrences) — REMEDIATED
- **Warning Class:** `jwt.InsecureKeyLengthWarning`
- **Location:** `jwt/api_jwt.py:370` called from `app/main.py:331` (`decode_token`)
- **Root Cause:** In `app/main.py`, the token verification logic strictly enforces security requirement **SEC-JWT-01** by testing incoming JWTs against a blocklist of known compromised and insecure keys (`COMPROMISED_KEYS`). This list contains intentionally weak keys (e.g. `"secret"` [6 bytes], `"test"` [4 bytes], `"changeme"` [8 bytes], `"replace-this-before-hosting"` [27 bytes]). PyJWT evaluates the key length against RFC 7518 recommendations and emitted an `InsecureKeyLengthWarning` during each verification step.
- **Action Taken (FR-CI-03, FR-CI-05):** In `app/main.py`, wrapped only the specific `COMPROMISED_KEYS` signature validation loop in a narrow `warnings.catch_warnings()` context manager specifically filtering `jwt.InsecureKeyLengthWarning`. This ensures the security check continues to reject tokens signed with compromised keys while eliminating spurious warnings. No global pytest warning filters were introduced.

---

### Category 2: Third-Party Dependency Deprecation (1 occurrence) — JUSTIFIED REMAINDER
- **Warning Class:** `starlette.exceptions.StarletteDeprecationWarning`
- **Message:** `Using httpx with starlette.testclient is deprecated; install httpx2 instead.`
- **Origin:** `fastapi.testclient` (`from starlette.testclient import TestClient as TestClient`)
- **Package Affected:** `starlette` / `fastapi`
- **Justification (FR-CI-04):** This is an upstream Starlette/FastAPI library deprecation informing consumers of upcoming client backend transitions in future major versions. Attempting to force-install an unreleased `httpx2` or altering FastAPI's internal `TestClient` imports would violate stability and scope boundaries.
- **Review Trigger:** Upgrade review scheduled upon the official FastAPI release migrating to `httpx2` or native ASGI client standards.
