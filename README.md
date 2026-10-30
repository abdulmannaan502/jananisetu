# JananiSetu — End-to-End Maternal Healthcare Operations, Workforce, Field Visits, Hospital Partnerships, Closed-Loop Follow-Up & Funding Accountability Platform (Phase 6)

JananiSetu is a multi-clinic maternal healthcare service, workforce operations, care-coordination, and public/institutional funding accountability platform developed for **Health-a-thon 2026**.

> **Healthcare, Clinical & Financial Governance Boundary**
> JananiSetu is an assistive administrative care-coordination, healthcare operations, and financial accountability platform operating on **synthetic patient and institutional grant records only**. It **never** performs autonomous diagnosis, prescriptions, clinical risk scoring, AI referral destination selection, or AI-generated treatment decisions. Missing clinical/administrative dates (such as EDD from LMP) or appointment dates are **never** inferred. All care plans and clinical referrals must be authored by licensed clinicians (`doctor` role), and all ANC card OCR outputs and staff professional credentials require explicit human verification before taking effect.
> In financial operations, JananiSetu **never** uses binary floating-point arithmetic (`float`) for money (all monetary amounts use exact integer `paise` and `decimal.Decimal` arithmetic), **never** represents a `draft` or `submitted` proposal as government-approved funding, **never** invents real government sanction orders (demo approvals are explicitly badged as `SIMULATED / DEMO APPROVAL`), **never** assumes universal Indian statutory tax/PF/ESI/PT rates without an explicitly validated `PayrollStatutoryConfig`, and **never** executes live bank transfers or marks payroll/expense claims as paid without verified payment evidence.

---

## Key Capabilities (Phases 1–6)

1. **Hardened Authentication, Token Revocation & RBAC**:
   - `bcrypt` password hashing, password strength enforcement (≥8 chars, letters + digits), signed JWT Bearer tokens + `HttpOnly` session cookies, and server-side token revocation (`revoked_tokens` table + `token_version`).
   - Legacy `X-Staff-ID` header is disabled (`401 Unauthorized`). Demo account seeding and disclosure are disabled in production (`JANANI_ENV=production`).
   - Strict clinic-scoped multi-tenancy and role-based access control for `admin`, `doctor`, `nurse`, and `field_coordinator`.
2. **Real Open-Source ANC Card Digitisation (JPG, PNG, WEBP, PDF)**:
   - Validates file size (≤5 MB), magic bytes, image decompression bounds, and rejects malicious PDFs (`/JavaScript`, `/Launch`) or disguised executables.
   - Extracts only permitted administrative fields (`patient_name`, `patient_identifier`, `contact_phone`, `facility_name`, `registration_date`, `lmp_date`, `edd_date`, `visit_date`, `follow_up_date`, `address`) using local **Tesseract 5 OCR** + **pypdf** with word-level bounding-box coordinates and confidence scores.
3. **Evidence-Linked React Verification & Document Version Management**:
   - Split-screen verification workspace ([AncDocumentReview.tsx](file:///c:/Projects/Healthathon/jananisetu/frontend/src/components/AncDocumentReview.tsx)) with SVG bounding-box highlights, per-field Accept / Correct / Reject / Illegible decisions, version comparison, and `AdminChangeProposal` workflow that never overwrites doctor-authorised `CarePlan` records.
4. **Durable Reminder Infrastructure ([followup_engine.py](file:///c:/Projects/Healthathon/jananisetu/app/followup_engine.py), [celery_app.py](file:///c:/Projects/Healthathon/jananisetu/app/celery_app.py))**:
   - **Redis + Celery Worker & Celery Beat** scheduling with a database-backed **Transactional Outbox** (`transactional_outbox` + `reminder_jobs`) so no jobs are lost between DB commit and worker dispatch, and local/test environments run deterministically even without an external Redis service.
   - **India Timezone (`Asia/Kolkata`)** appointment-based scheduling using **only** doctor-authorised `CarePlan.visit_date` and clinic-configurable offsets (default `[-48, -24, 0]` hours).
   - **Automatic Cancellation**: Superseding a `CarePlan` or withdrawing mother/caregiver consent immediately cancels all pending/retrying reminder jobs.
   - **Exponential Backoff & Dead-Letter Queue**: Transient provider failures retry with exponential backoff up to `max_attempts`, transition to `dead_letter`, and support 1-click operator retry (`POST /api/reminders/jobs/{jid}/retry`).
5. **Provider-Independent Messaging & Signed Webhooks ([messaging.py](file:///c:/Projects/Healthathon/jananisetu/app/messaging.py))**:
   - Includes **Meta WhatsApp Cloud API** adapter (`whatsapp-cloud`), **SMS Gateway** adapter (`sms-gateway`), and deterministic **Local Simulator** (`local-simulator`).
   - Honest live-readiness reporting: never claims live WhatsApp is operational unless verified Meta Cloud API credentials (`JANANI_WHATSAPP_PHONE_NUMBER_ID`, `JANANI_WHATSAPP_ACCESS_TOKEN`) and approved templates (`JANANI_WHATSAPP_TEMPLATE_APPROVED=true`) are configured.
   - **Signed Webhook Verification**: Verifies `X-Hub-Signature-256` (`HMAC-SHA256`) on `/api/webhooks/whatsapp`, deduplicates `event_id` in `webhook_events`, and enforces monotonic delivery rank ordering (`queued` → `sent` → `delivered` → `read` → `acknowledged`) so out-of-order callbacks never downgrade higher states.
6. **Closed-Loop Follow-Up State Machine & Human Escalation ([FollowupCommHub.tsx](file:///c:/Projects/Healthathon/jananisetu/frontend/src/components/FollowupCommHub.tsx))**:
   - Explicit state machine: `scheduled` → `reminder_sent` → `delivered` → `acknowledged` → `visit_confirmed` → `closed` (plus operational alternative states `delivery_failed`, `no_acknowledgement`, `missed_appointment`, `contact_required`, `staff_assigned`, `contact_attempted`, `rescheduled_by_authorised_staff`, `resolved`, `unreachable`).
   - Delivery, acknowledgement, clinic attendance, and closure are strictly distinct; invalid state transitions are rejected (`409 Conflict`).
7. **Caregiver Permissions & Indian Privacy (DPDP Act 2023) Controls**:
   - Explicit, revocable `CaregiverConsent` per mother (`allow_admin_reminders`).
   - Strict privacy guard blocks any clinical terms, lab/vital terms, or ANC scan links from caregiver reminders. Phone numbers are masked (`******0101`) in logs and UI metadata.
8. **Healthcare Workforce Management ([phase5_routes.py](file:///c:/Projects/Healthathon/jananisetu/app/phase5_routes.py), [WorkforceOperationsHub.tsx](file:///c:/Projects/Healthathon/jananisetu/frontend/src/components/WorkforceOperationsHub.tsx))**:
   - Doctor, nurse, field coordinator, and admin profiles (`StaffWorkforceProfile`), keeping **employment/contractor status** (`full_time_employee`, `part_time_employee`, `contract_clinician`, `nhm_deputed`, `community_honorarium`) strictly distinct from clinical role (`Staff.role`).
   - Professional registration numbers, credential documents (`StaffCredentialDocument`), expiry tracking, and supervisor human verification (`POST /api/workforce/credentials/{id}/verify`) with **anti-self-verification enforcement (`403 Forbidden`)**.
   - Shift assignment (`StaffShift`) with **overlapping shift & approved leave conflict detection (`409 Conflict`)**, attendance check-in/out, leave requests (`StaffLeaveRequest`) with replacement staff coverage, and staff offboarding that flags active service assignments as `unavailable_personnel`.
9. **Patient Service Coordination, Field Visits & Offline Draft Sync**:
   - Full service lifecycle (`ServiceRequest`): `service_requested` → `staff_assigned` → `scheduled` → `in_progress` → `completed` → `verified` → `closed` (plus `cancelled`, `no_show`, `reassignment_required`, `unavailable_personnel`, `failed_visit`), enforcing clinical qualification requirements.
   - Nurse and field-worker daily schedules (`FieldVisit`), patient consent verification, role-scoped notes (blocking non-clinicians from entering clinical observations), purpose-limited optional location check-in requiring explicit `location_consent_granted=True`, and idempotent offline draft synchronization (`POST /api/field-visits/offline-sync`).
10. **Hospital & Diagnostic Partnerships, Transport Operations, Operations Centre & Governance**:
    - Partner facility registry (`PartnerFacility`) with agreement dates & scheduled charges, and clinician-authorised referral lifecycle (`HospitalReferral`) with automatic contractual `Expense` recording upon verification.
    - Non-emergency maternal transport partners (`TransportPartner`), vehicle & driver licence/insurance verification (`TransportVehicleDriver`), trip lifecycle (`assigned` → `in_transit` → `completed` | `failed_pickup` | `cancelled`), and automatic trip voucher `Expense` creation.
    - Live **Operations Centre Dashboard** (`GET /api/operations/dashboard`), **Governance Incident** escalation/resolution (`GovernanceIncident`), immutable **Record Correction Audit Log** (`RecordCorrectionLog`), and a 1-click **10-Step End-to-End Operational Walkthrough** (`POST /api/operations/demo-walkthrough`).
11. **Government & Institutional Contracts & Programme Budgets ([phase6_routes.py](file:///c:/Projects/Healthathon/jananisetu/app/phase6_routes.py), [FinancialAccountabilityHub.tsx](file:///c:/Projects/Healthathon/jananisetu/frontend/src/components/FinancialAccountabilityHub.tsx))**:
    - Supports government health departments, NHM authorities, public hospitals, NGOs, and CSR funders (`FundingOrganisation`, `ProgrammeContract`) across `draft` → `submitted` → `approved` → `active` → `suspended` | `completed` | `terminated`.
    - Enforces strict draft governance: `draft` and `submitted` contracts are never represented as approved funding and cannot anchor operational budgets or reimbursable claims.
    - Tracks payment milestones (`ContractMilestone`), versioned contract amendments (`ContractAmendment`), programme/clinic budgets (`ProgrammeBudget`, `BudgetCategoryLine` across `salary`, `travel`, `transport`, `clinical_services`, `diagnostics`, `technology`, `administration`), overspending blocks, and authorised budget amendments (`BudgetAmendmentLog`).
12. **Healthcare Workforce Payroll, Transport & Field Expense Reimbursements & Service-to-Funding Evidence**:
    - Explicit, versioned statutory deduction & employer contribution configuration (`PayrollStatutoryConfig`) validated by a named payroll professional, staff compensation agreements (`StaffCompensationAgreement`), attendance adjustments applied **only** when `attendance_adjustment_permitted=True`, duplicate payroll prevention (`409 Conflict` per `(clinic, period_month, staff_id)`), anti-self-approval (`403 Forbidden`), and offline CSV payment batch export.
    - Staff travel & transport partner invoice reimbursement (`ExpensePolicyRule`, `ExpenseClaim`) reusing the existing `Expense` table without duplicate records, enforcing duplicate receipt/trip/visit rejection (`409 Conflict`), anti-self-approval (`403 Forbidden`), and blocking private unapproved transport under public health schemes unless both the contract and policy explicitly permit it.
    - Complete **Service-to-Funding Evidence Chain** (`FundingClaim`, `ServiceFundingEvidenceLink`) generating privacy-safe **Supporting Evidence Packages** (`BEN-...` anonymised beneficiary references with zero patient PII), CSV/PDF report exports watermarked `INTERNAL / DRAFT`, immutable `FinancialAuditLedger` with `X-Idempotency-Key` concurrency protection, versioned `FinancialCorrectionRecord`, and a 1-click **12-Step Funded Maternal Programme Walkthrough** (`POST /api/finance/demo-walkthrough`).

---

## Startup & Verification Commands

### 1. Run Transactional Database Migrations (Alembic)

```powershell
.\.venv\Scripts\alembic.exe upgrade head
```

### 2. Build Frontend & Start Application Server

```powershell
# Build React + TypeScript + Tailwind frontend into app/static/dist
cd frontend
npm run build
cd ..

# Start FastAPI server on http://127.0.0.1:8000
.\.venv\Scripts\uvicorn.exe app.main:app --reload --host 127.0.0.1 --port 8000
```

### 3. Start Celery Worker & Celery Beat (When Redis is Running)

```powershell
# Start Celery worker
.\.venv\Scripts\celery.exe -A app.celery_app:celery_app worker --loglevel=info --pool=solo

# Start Celery Beat scheduler (Asia/Kolkata timezone)
.\.venv\Scripts\celery.exe -A app.celery_app:celery_app beat --loglevel=info
```

*(Note: When running locally without a live Redis service, the deterministic Transactional Outbox runner `POST /api/reminders/worker/run` dispatches due jobs directly from PostgreSQL/SQLite.)*

### 4. Run All Automated Tests (47 Tests Across Phases 1–6)

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```
