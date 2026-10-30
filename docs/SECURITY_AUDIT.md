# JananiSetu — Security Audit, Hardening & Healthcare Compliance

This report details the independent security review, vulnerability assessment, hardening measures, and healthcare data governance implemented across the JananiSetu platform.

---

## 1. Threat Modeling & Vulnerability Findings

An independent code-level security audit was conducted against OWASP Top 10 API Security Risks and Indian Digital Personal Data Protection (DPDP) Act requirements:

### Vulnerability 1: Cross-Site Request Forgery (CSRF) via Cookie Sessions (Fixed)
- **Risk Assessment**: The application supports browser cookie-based authentication (`janani_access_token`). In browsers without strict cookie partitioning or on cross-origin web pages, malicious scripts could submit state-changing POST/PUT/DELETE requests using the ambient session cookie.
- **Remediation**: Implemented rigorous CSRF defense inside the `who()` dependency in `app/main.py`:
  - Examines `Sec-Fetch-Site`. If `cross-site`, requests using cookie authentication are immediately rejected with `403 Forbidden`.
  - For non-cross-site requests using cookies, requires a custom anti-CSRF signal (`X-Requested-With`, `X-CSRF-Token`) or matches `Origin`/`Referer` against configured allowed origins (`http://localhost:*`, `http://127.0.0.1:*`).
  - Added `X-Requested-With: XMLHttpRequest` to the central `apiRequest()` utility in `frontend/src/api.ts`.
  - Pure Bearer token requests (used by mobile apps and automated API consumers) remain permitted as Bearer headers cannot be sent automatically by cross-origin browser fetches.
- **Verification**: Verified in `tests/test_phase7_hardening.py::test_csrf_protection_and_cookie_auth`.

### Vulnerability 2: Brute Force Authentication on `/api/auth/login` (Fixed)
- **Risk Assessment**: High-volume automated password guessing could compromise healthcare worker accounts.
- **Remediation**: Added an in-memory sliding-window rate limiter on `POST /api/auth/login`:
  - Tracks failed login timestamps keyed on `(client_ip, normalized_identifier)`.
  - Allows at most 10 failed login attempts within a 60-second window.
  - The 11th attempt immediately raises `429 Too Many Requests` ("Too many failed login attempts. Please wait 60 seconds before trying again.").
  - Successful authentication clears the failed attempt history.
- **Verification**: Verified in `tests/test_phase7_hardening.py::test_login_rate_limiting`.

### Vulnerability 3: Cross-Clinic Mutation Leakage in Ancillary Operations (Fixed)
- **Risk Assessment**: In `update_appointment_status`, `update_task`, and `update_transport_status`, records were queried by primary key. If an attacker authenticated at Clinic B knew the ID of a task or transport at Clinic A, missing clinic ownership checks could permit cross-clinic status modification.
- **Remediation**: Added defense-in-depth clinic checks:
  ```python
  if obj.clinic != s.clinic:
      raise HTTPException(404, "Entity not found in your clinic")
  ```
  Entities from other clinics appear nonexistent (`404 Not Found`), preventing information disclosure and unauthorized state alterations.
- **Verification**: Verified in `tests/test_phase7_hardening.py::test_cross_clinic_defense_in_depth`.

### Vulnerability 4: Race Condition on Concurrent Workforce Profile Generation (Fixed)
- **Risk Assessment**: When multiple concurrent requests touched an existing staff member lacking a workforce profile, concurrent `db.add(StaffWorkforceProfile)` triggered an unhandled SQLite/PostgreSQL `UNIQUE constraint failed: staff_workforce_profiles.staff_id` error, aborting the transaction.
- **Remediation**: Wrapped `_ensure_workforce_profile()` in `app/phase5_routes.py` in an `IntegrityError` catch block with `db.rollback()` that recovers by fetching the freshly committed record.

---

## 2. Role-Based Access Control (RBAC) Matrix

JananiSetu enforces strict role segregation. The four clinical and administrative roles have documented and non-overlapping privileges:

| Privilege / Action | Admin | Doctor (MO) | Nurse (ANM) | Field Coordinator (ASHA) |
| :--- | :---: | :---: | :---: | :---: |
| **Manage Clinic Staff & Contracts** | **Allowed** | Denied | Denied | Denied |
| **Approve Care Plans & Prescriptions** | Denied | **Allowed** | Denied | Denied |
| **Stratify High Risk & Clinical Goals** | Denied | **Allowed** | Denied | Denied |
| **Upload & Verify ANC MCP Cards** | Denied | Denied | **Allowed** | Denied |
| **Approve Change Proposals (Master Data)**| **Allowed** | **Allowed** | Denied | Denied |
| **Execute Field Visits & Sync Offline** | Denied | Denied | **Allowed** | **Allowed** |
| **Submit Expense & Travel Claims** | **Allowed** | **Allowed** | **Allowed** | **Allowed** |
| **Verify Expense Claim (Supervisor Tier)**| Denied | **Allowed** | Denied | Denied |
| **Approve Expense Claim (Finance Tier)** | **Allowed** | Denied | Denied | Denied |
| **Self-Approve Own Travel or Expense Claim**| **BLOCKED** | **BLOCKED** | **BLOCKED** | **BLOCKED** |

---

## 3. Data Protection, Consent & PII Safeguards

Under maternal healthcare compliance guidelines:
- **Explicit Consent Model**: Patients are registered with documented consent flags (`consent: true`, language preference, and Telugu/Hindi/English disclosure).
- **Consent Revocation Safety**: If a mother revokes consent via `PATCH /api/mothers/{id}/consent`, the system instantly cancels all scheduled pending SMS/WhatsApp reminder jobs.
- **Zero-PII Supporting Evidence Packages**: Service-to-funding reconciliation exports for external government auditors use synthetic beneficiary tokens (`BEN-XXX-HASH`) and strip names, addresses, and phone numbers.
- **GPS Location Privacy**: Coordinates are only captured during field visits when `location_consent_granted: true` is explicitly recorded along with a validated clinical purpose.
- **Immutable Financial Ledger**: All monetary actions are appended to `financial_audit_ledger` with actor role, idempotency keys, and transition states; destructive edits are strictly forbidden.

