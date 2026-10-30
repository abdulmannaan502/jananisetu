# JananiSetu — Technical Security Audit & Phase 3 ANC Digitisation Report

## 1. Phase 2 Independent Security Audit & Remediations

Prior to implementing Phase 3, an audit of the Phase 2 implementation was conducted:

| Area Audited | Phase 2 Finding | Phase 3 Security Remediation |
| :--- | :--- | :--- |
| **`X-Staff-ID` Legacy Header** | `JANANI_ALLOW_LEGACY_HEADER` defaulted to `"true"` in `app/config.py`, and could remain enabled if not explicitly unset in production. | Changed default to `"false"` and enforced an unconditional override (`self.allow_legacy_header = False`) whenever `JANANI_ENV=production`. Updated `tests/test_api.py` to use signed JWT Bearer tokens and assert `X-Staff-ID` is rejected (`401`). |
| **Demo Account Seeding & Disclosure** | `/api/auth/seed-demo` and `/api/auth/demo-accounts` were accessible regardless of `JANANI_ENV`, and `GET /api/staff` allowed unauthenticated fallback during bootstrap. | Disabled `/api/auth/seed-demo` and `/api/auth/demo-accounts` (`403 Forbidden`) when `JANANI_ENV=production` or `JANANI_ENABLE_DEMO_MODE=false`. Locked `GET /api/staff` behind mandatory `Depends(who)`. |
| **JWT Storage & Token Revocation** | Frontend stored JWTs in `localStorage` (exposed to XSS), and backend lacked a token revocation list (`jti`) or `token_version` invalidation on logout/password change. | Removed `localStorage` persistence in `frontend/src/api.ts` (using in-memory token + `HttpOnly; SameSite=Lax` cookie). Added `RevokedToken` table (`jti` checked on every request) and `Staff.token_version` incremented on password change or account deactivation. |
| **Password Policy** | Allowed 6-character passwords without complexity rules. | Added `validate_password_strength()` enforcing ≥8 characters with at least one letter and one digit across registration, staff creation, and password change. |
| **Transactional Migrations & Startup DDL** | `ensure_schema_and_migrate_legacy(engine)` ran unconditionally on startup, and Alembic logged `Will assume non-transactional DDL` on SQLite. | Disabled automatic startup DDL in production (`if not settings.is_production`). Enabled `transactional_ddl=True` and `transaction_per_migration=True` in `alembic/env.py` and added revision `0002_phase3_anc_digitisation`. |
| **Private Document Storage** | Scans were stored in `data/scans/{id}.img` without SHA-256 integrity hashing or clinic directory partitioning. | Partitioned private storage by clinic (`data/private_storage/{clinic}/{id}.bin` and `{id}_preview.png`), verified magic bytes and PDF safety, and enforced clinic isolation on `/file` and `/preview`. |

---

## 2. Phase 3: Real ANC Card Digitisation & Evidence-Linked Verification Architecture

### 2.1 OCR & Document Processing Pipeline ([ocr_engine.py](file:///c:/Projects/Healthathon/jananisetu/app/ocr_engine.py))
- **Supported Formats**: `image/jpeg`, `image/png`, `image/webp`, and `application/pdf` (≤ 5 MB).
- **Content & Malware Validation**: Checks magic bytes (`\x89PNG`, `\xff\xd8\xff`, `RIFF..WEBP`, `%PDF-`), blocks disguised executables (`MZ`, ELF, HTML/JS, PHP), enforces Pillow `MAX_IMAGE_PIXELS`, and rejects PDFs containing `/JavaScript`, `/JS`, `/Launch`, or `/RichMedia` actions.
- **Open-Source OCR Engine**: Uses Tesseract 5 (`pytesseract.image_to_data`) for word-level text, confidence (`0..100%`), and bounding-box coordinates (`x, y, w, h`), combined with `pypdf` for PDF inspection and page rendering.
- **Third-Party API Privacy Guard**: External vision providers are disabled by default (`JANANI_EXTERNAL_OCR_ENABLED=false`) and strictly blocked (`403 Forbidden`) unless `JANANI_EXTERNAL_OCR_ENABLED=true`, `JANANI_EXTERNAL_OCR_DATA_SAFEGUARD_ACK=true`, and recorded patient consent (`mother.consent == True`) are all satisfied.
- **Permitted Administrative Fields Only**:
  - `patient_name`, `patient_identifier`, `contact_phone`, `facility_name`, `registration_date`, `lmp_date`, `edd_date`, `visit_date`, `follow_up_date`, `address`.
  - **Zero Clinical Inference**: Missing fields (such as a blank `edd_date` when `lmp_date` is present) are never calculated or inferred. Invalid dates (e.g., `2026-13-45`) are flagged as uncertain with `normalized_value = None`.

### 2.2 Measured OCR Benchmark Across Synthetic ANC Fixtures ([anc_fixtures.py](file:///c:/Projects/Healthathon/jananisetu/app/anc_fixtures.py))

Measured live using `evaluate_fixtures_benchmark()` (`GET /api/documents/fixtures/evaluate`) with Tesseract 5:

| Synthetic Fixture | Description | Present Fields Matched | Measured Field Accuracy | Mean Token Confidence | Missing Fields Detected | Conflicts / Uncertainties Detected |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. `printed_clear`** (PNG & PDF) | Clean machine-printed ANC card | **10 / 10** | **100.0%** | **95.1%** | None (`[]`) | 0 conflicts; all 10 fields high confidence with exact bounding boxes |
| **2. `partially_handwritten`** | Printed labels + handwritten-style ink values & dual follow-up dates | **8 / 10** | **80.0%** | **90.6%** | None (`[]`) | Intra-document conflict detected on `follow_up_date` (`2026-11-18` vs `2926-11-28`); handwritten OCR error on `visit_date` (`2926-10-29`, conf `60.0%`) caught and blocked from normalization |
| **3. `difficult_incomplete`** | Degraded noisy scan with blank EDD/Address & smudged phone/date | **6 / 6** valid present fields | **100.0%** of valid present fields (2 invalid/illegible fields flagged) | **93.3%** | `edd_date`, `address` (EDD not inferred from LMP) | `contact_phone` (`9800??illegible`) and `visit_date` (`2026-13-45`) flagged as uncertain (`normalized_value = None`) |
| **Overall Benchmark** | Across all 3 synthetic fixtures | **24 / 26** | **92.3%** | **93.0%** | — | All missing, illegible, and conflicting fields accurately flagged for human review |

---

## 3. Database Tables & Alembic Migrations (`0002_phase3_anc_digitisation`)

- `revoked_tokens`: JWT revocation by `jti`
- `documents`: Extended with `version_number`, `supersedes_document_id`, `stored_path`, `preview_path`, `file_size_bytes`, `sha256_hash`, `image_width`, `image_height`, `page_count`, `ocr_status`, `ocr_engine`, `ocr_error`, `review_status`
- `ocr_jobs`: Job execution timing, word counts, mean confidence, missing fields, and conflicts
- `extracted_fields`: Per-field raw value, normalized value, confidence, uncertainty flags, conflict flags, bounding box, and verification status (`unreviewed`, `accepted`, `corrected`, `rejected`, `illegible_manual`)
- `field_source_locations`: Token-level bounding boxes (`page_number, x, y, width, height, token_text, token_confidence`)
- `verification_decisions`: Immutable log of every staff field decision and document confirmation
- `document_versions`: Version lineage and confirmed administrative snapshots per mother
- `admin_change_proposals`: Proposed profile updates and follow-up date notes requiring explicit staff approval without overwriting confirmed patient profiles or doctor-authorised `CarePlan` records

---

## 4. Phase 4: Durable Closed-Loop Follow-Up, Messaging & Privacy Compliance (`0003_phase4_followup_and_messaging`)

### 4.1 Durable Reminder & Transactional Outbox Architecture
- **Database Tables**:
  - `reminder_jobs`: Persistent scheduled jobs with unique `idempotency_key`, `Asia/Kolkata` timezone calculation from doctor-authorised `CarePlan.visit_date`, attempt counters, exponential backoff `next_retry_at`, `dead_lettered_at`, and `cancellation_reason`.
  - `transactional_outbox`: Written in the same database transaction as `ReminderJob` creation or cancellation to guarantee zero lost jobs between DB commit and worker dispatch.
  - `webhook_events`: Idempotency ledger (`event_id` unique) for signed delivery callbacks and inbound messages.
  - `contact_attempts`: Multi-channel staff outreach log (`phone_call`, `home_visit`, `whatsapp_followup`, `asha_liaison`) linked to follow-up tasks and care plans.
  - `caregiver_consents`: Separate, revocable caregiver permission records for administrative-only appointment reminders.
  - `clinic_comm_configs`: Clinic-scoped reminder offsets, acknowledgement deadlines, retry parameters, and approved template names.

### 4.2 Indian Privacy (DPDP Act 2023) & Healthcare Compliance Controls
1. **Purpose Limitation & Explicit Consent**: Mother reminders require `Mother.consent == True`; caregiver reminders require both `CaregiverConsent.consent_granted == True` and `allow_admin_reminders == True`. Withdrawing consent or replying `STOP` immediately cancels all pending reminder jobs.
2. **Data Minimisation & Caregiver Boundary**: `validate_privacy_safe_content()` blocks clinical findings, diagnoses, lab results, and ANC scan URLs from messaging templates, and enforces a strict administrative-only filter on caregiver messages.
3. **PII Masking & Webhook Integrity**: Phone numbers are masked via `mask_phone()` in logs and API responses (`recipient_phone_masked`), and `/api/webhooks/whatsapp` enforces `X-Hub-Signature-256` HMAC-SHA256 verification.
4. **Honest Provider Readiness**: `MetaWhatsAppCloudAdapter` and `SmsGatewayAdapter` report `credentials_required` unless live credentials and approved templates are explicitly configured, while `LocalSimulatorAdapter` provides deterministic offline testing.

---

## 5. Phase 5: Healthcare Workforce, Field Visits, Hospital Partnerships, Transport Operations & Governance (`0004_phase5_workforce_operations_governance`)

### 5.1 Phase 5 Normalized Database Schema
- `staff_workforce_profiles`: Separates employment/contract status (`full_time_employee`, `part_time_employee`, `contract_clinician`, `nhm_deputed`, `community_honorarium`) and `onboarding_status` from clinical/system role (`Staff.role`).
- `staff_credential_documents`: Professional council registrations (`medical_council_registration`, `nursing_license`, `degree_certificate`), expiry tracking, and supervisor verification (`unverified` → `verified` | `rejected` | `expired`). Self-entered credentials are never treated as verified, and self-verification is blocked (`403 Forbidden`).
- `staff_shifts` & `staff_leave_requests`: Shift scheduling with overlapping time-window and approved-leave conflict detection (`409 Conflict`), attendance check-in/out, and leave replacement staff coverage.
- `service_requests`: Operational service lifecycle (`service_requested` → `staff_assigned` → `scheduled` → `in_progress` → `completed` → `verified` → `closed`, plus `cancelled`, `no_show`, `reassignment_required`, `unavailable_personnel`, `failed_visit`) with clinical qualification enforcement.
- `field_visits`: Nurse and field-worker daily visit schedules, patient consent verification, role-scoped notes, optional purpose-limited point-in-time location check-in (`location_consent_granted` required), completion evidence, and idempotent offline draft synchronization (`offline_draft_id`).
- `partner_facilities` & `hospital_referrals`: Empaneled referral hospitals, diagnostic laboratories, and ultrasound centres with agreement validity dates, clinician-authorised referrals, partner acknowledgement tracking, and automatic contractual `Expense` creation upon verification.
- `transport_partners`, `transport_vehicles_drivers`, & extended `transports`: Non-emergency scheduled maternal transport partners, driver licence & vehicle insurance verification gates, driver acceptance/rejection, trip completion with voucher `Expense` creation, and failed-pickup driver reassignment.
- `governance_incidents` & `record_correction_logs`: Clinical and organisational governance incident escalation/resolution and immutable human-approved record correction auditing.

### 5.2 Regulatory, Legal & Clinical Review Requirements Before Real-World Deployment (India)
1. **National Medical Commission (NMC) & State Medical/Nursing Council Verification**:
   - Before live deployment, clinician onboarding must verify Registered Medical Practitioner (RMP) credentials against the official **NMC National Medical Register (NMR)** / State Medical Council and **Indian Nursing Council (INC) Nurses Registration & Tracking System (NRTS)**, in accordance with the *NMC Registered Medical Practitioner (Professional Conduct) Regulations* and *Telemedicine Practice Guidelines (2020)*.
2. **Pre-Conception and Pre-Natal Diagnostic Techniques (PCPNDT) Act, 1994**:
   - Partner ultrasound centres (`ultrasound_centre`) must hold an active, verified **PCPNDT registration certificate** and Form-F statutory record compliance. Sex-selection or fetal sex disclosure is strictly illegal under Indian law.
3. **Clinical Establishments (Registration and Regulation) Act & Partner MOUs**:
   - Partner hospitals, diagnostic labs (NABL-accredited where applicable), and blood banks must have executed, legally vetted Memoranda of Understanding (MOUs), verified state Clinical Establishment registrations, and documented clinical transfer protocols.
4. **Digital Personal Data Protection (DPDP) Act, 2023 & ABDM Health Data Standards**:
   - Maternal health records and optional field-visit check-in coordinates require explicit, informed, revocable Data Principal consent in the beneficiary's preferred language (`te`, `hi`, `en`), strict purpose limitation, data retention schedules, and Data Protection Board breach-notification procedures.
5. **Motor Vehicles Act & Non-Emergency Maternal Transport Boundary**:
   - Scheduled clinic transport partners must maintain commercial passenger permits, comprehensive vehicle insurance, and valid commercial driving licences. Acute obstetric emergencies must be routed to state **108 / 102 Emergency Ambulance Services** equipped with Basic/Advanced Life Support.

---

## 6. Phase 6: Government Contracts, Programme Budgets, Healthcare Payroll, Transport Expenses & Funding Accountability (`0005_phase6_contracts_budgets_payroll_finance`)

### 6.1 Phase 6 Normalized Financial Schema & Reuse of Existing `expenses` Table
- **Extended `expenses` Table**: Added `contract_id`, `budget_id`, `expense_claim_id`, `payroll_run_id`, `funding_claim_id`, `reimbursement_status`, and `payment_ref` so Phase 5 transport trip vouchers, referral charges, Phase 6 expense claims, and payroll disbursements all reconcile through the single `expenses` table without creating duplicate expenditure records.
- **Contracts & Milestones**: `funding_organisations`, `programme_contracts`, `contract_milestones`, and `contract_amendments`.
- **Budgets & Financial Control**: `programme_budgets`, `budget_category_lines` (`allocated_paise`, `committed_paise`, `incurred_paise`, `approved_paise`, `paid_paise`, `reimbursed_paise`), and `budget_amendment_logs`.
- **Healthcare Workforce Payroll**: `payroll_statutory_configs`, `staff_compensation_agreements`, `payroll_runs`, and `payslip_records` (with unique index `ux_payslip_clinic_month_staff` preventing duplicate monthly payroll per staff member).
- **Expense Policy & Reimbursements**: `expense_policy_rules` and `expense_claims`.
- **Service-to-Funding Evidence & Immutable Financial Governance**: `funding_claims`, `service_funding_evidence_links`, `financial_audit_ledger` (with unique `idempotency_key`), and `financial_correction_records`.

### 6.2 Strict Financial & Statutory Governance Rules Enforced in Code
1. **Exact Integer `paise` & `Decimal` Monetary Arithmetic**: All monetary columns are stored as integer `paise` and all basis-point (`bps`), pro-rata attendance, and currency formatting calculations use `decimal.Decimal` (`ROUND_HALF_UP`) — binary floating-point arithmetic (`float`) is never used for money.
2. **Draft Contract Governance & Anti-Fabrication**: Contracts in `draft` or `submitted` state explicitly report `is_approved_funding = False` and cannot be used to create budgets, expense claims, or funding claims. Simulated demo approvals require `is_simulated_approval = True` and display an explicit `SIMULATED / DEMO APPROVAL` disclaimer.
3. **Separation of Duties & Anti-Self-Approval**: Submitter/calculator cannot self-verify or self-approve contracts, payroll runs, or expense claims (`403 Forbidden`).
4. **Public Health Scheme Private Transport Guard**: Claims with `transport_mode = "private_unapproved"` are rejected (`400 Bad Request`) unless both `ProgrammeContract.allow_private_transport_reimbursement` and `ExpensePolicyRule.allow_private_transport` are explicitly `True`.
5. **Privacy-Preserving Supporting Evidence Packages**: `GET /api/finance/funding-claims/{id}/evidence-package` links `Contract` → `Budget` → `ServiceCategory` → `Staff` → `ServiceRequest / FieldVisit / Transport / HospitalReferral` → `Expense` → `FundingClaim` using deterministic HMAC-SHA256 anonymised beneficiary identifiers (`BEN-...`) without exposing patient names, phone numbers, or clinical notes.
