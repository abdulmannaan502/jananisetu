# JananiSetu — Live Demonstration Scripts (Health-a-thon 2026)

This document provides two structured presentation formats:
1. **The 3-Minute Executive Product Demonstration** (Optimised for hackathon judges & healthcare stakeholders).
2. **The 5-Minute Technical Deep-Dive Walkthrough** (Optimised for engineering reviewers & security auditors).

---

## Part A: 3-Minute Executive Demonstration Script

### Timing: 0:00 – 0:30 | The Problem & Patient Registration
- **Presenter**: "Welcome judges. Maternal mortality in rural India is not primarily caused by lack of medical science—it is driven by preventable care drop-offs between routine checkups and deliveries. This is JananiSetu."
- **Action**: Log in as ANM Staff Nurse `Lakshmi Devi`. Navigate to **Mothers & Consent**.
- **Demonstration**:
  - Show the registration form: Enter synthetic mother `Savitri Devi`, phone `9849012345`, select Telugu (`తెలుగు`), and toggle `Communication consent recorded`.
  - Click **Register Mother**. Filter by name to demonstrate instant persistence.
  - "Notice that communication consent is an explicit regulatory requirement before any automated notification can be queued."

### Timing: 0:30 – 1:15 | Evidence-Linked OCR & Human Verification
- **Action**: Navigate to **ANC Scans & OCR**.
- **Demonstration**:
  - Select `Savitri Devi` and upload the synthetic fixture `printed_clear.png`.
  - Click **Measure OCR Accuracy on 3 Fixtures** to display real Tesseract-5 extraction metrics (92.3% field accuracy across fixtures).
  - Highlight the dual-pane view: click on `Recorded EDD` on the right to display the highlighted bounding box on the original scan on the left.
  - "Critically, JananiSetu performs *no AI prescribing or automated clinical risk scoring*. Raw OCR never alters the patient record without explicit clinician confirmation."
  - Click **Save Confirmed Administrative Record**.

### Timing: 1:15 – 2:00 | Doctor Authority & Closed-Loop Follow-up
- **Action**: Sign out and log in as Medical Officer `Dr. Kavitha Rao`. Navigate to **Care Plans & Visits**.
- **Demonstration**:
  - Show that administrative staff are blocked from scheduling medical visits (enforced `403 Forbidden`).
  - Doctor authorises ANC Visit #3 for `2026-11-25` with note `[SYNTHETIC-CLINICAL-RECORD] Routine ANC follow-up`.
  - Switch to **Reminders & Replies**. Click **Dispatch Due Reminders Now**.
  - Show the Transactional Outbox transitioning reminder status from `scheduled` to `delivered` via signed webhook callbacks.
  - "If an expectant mother does not acknowledge, the engine automatically escalates the case into a high-priority follow-up task for the assigned field worker."

### Timing: 2:00 – 3:00 | Non-Emergency Transport & Funding Accountability
- **Action**: Log in as Clinic Administrator `Ananya Reddy`. Open **Operations & Workforce** -> **Transport Fleet & Trips**.
- **Demonstration**:
  - Show the empaneled community transport partner and verified driver `Srinivasulu Yadav`.
  - Highlight the clear clinical safety boundary banner: *"Non-Emergency Scheduled Transport Only. Dial 108 for obstetric emergencies."*
  - Switch to **Contracts, Budgets & Finance**. Show the active NHM synthetic grant (₹25,00,000.00 ceiling).
  - Open **Budgets & Cash-Flow** to demonstrate integer-paise accounting and anti-self-approval enforcement.
  - Navigate to **Reports & CSV/PDF Exports** and click **Export Funding Evidence Package**. Show that patient PII is completely sanitized to `BEN-<hash>` with redaction watermarks.
- **Closing**: "JananiSetu delivers assistive continuity from village field visits to public funding transparency—safely, accurately, and durably."

---

## Part B: 5-Minute Technical Deep-Dive Walkthrough

### 1. Architectural Foundation & Multi-Tenancy (0:00 – 1:00)
- **FastAPI + PostgreSQL + React + Vite + Tailwind Architecture**:
  - Explain the multi-tenant clinic isolation: Every SQLAlchemy query filters by `clinic == current_user.clinic`.
  - Cross-clinic access attempts yield strict `404 Not Found` or `403 Forbidden` responses.
  - Show the cookie-backed authentication pipeline: HttpOnly, SameSite=Lax session cookies paired with `X-Requested-With: XMLHttpRequest` anti-CSRF token verification.

### 2. OCR Provenance & Administrative Change Proposal Engine (1:00 – 2:00)
- **Tesseract-5 Image Processing**:
  - Multi-page PDF rasterization (300 DPI via `pypdfium2`) and contrast normalization.
  - Bounding box normalization: Pixel coordinates are converted into percentage ratios relative to image canvas dimensions, enabling responsive visual overlays on desktop and mobile.
  - Change Proposal Isolation: Confirmed OCR values that disagree with existing patient records do not overwrite them automatically; they create immutable `ChangeProposal` records for human review.

### 3. Transactional Outbox & Background Queue Durability (2:00 – 3:15)
- **Durable Scheduling without Queue Drift**:
  - Explain why direct Celery queueing is dangerous during app restarts: uncommitted database transactions lead to ghost tasks.
  - JananiSetu writes `ReminderJob` records to the database within the same ACID transaction as the doctor's `CarePlan`.
  - Outbox workers poll `pending` records with row-level locks (`with_for_update(skip_locked=True)` in Postgres), dispatch via the messaging adapter, and record webhook acknowledgments.
  - Show the signed webhook verification using HMAC-SHA256 (`X-Hub-Signature-256`) and idempotency deduplication keys preventing replay attacks.

### 4. Mathematical Exactness in Financial Systems (3:15 – 4:15)
- **Integer Paise Accounting**:
  - Financial calculations use integer `paise` (1 INR = 100 paise) and Python `Decimal` to avoid IEEE-754 floating-point rounding errors.
  - Budget lines track committed, incurred, approved, paid, and reimbursed amounts.
  - Anti-Self-Approval: The user who created an expense or payroll claim cannot approve it. Self-approval attempts return `400 Bad Request`.
  - Zero-PII Sanitization: Financial claims link to patient care evidence via cryptographic hashes (`sha256(mother_id + clinic)`), scrub clinical diagnosis text, and attach `REDACTED_FINANCIAL_AUDIT_COPY` watermarks.

### 5. Automated Verification & Verification Evidence (4:15 – 5:00)
- **Pytest & Playwright Test Automation**:
  - 57 backend tests covering all edge cases across phases 2 through 7B.
  - 7 browser tests in Playwright executing real persisted mutations across desktop, tablet, and mobile viewports.
  - All 17 automated demo screenshots generated live into `docs/screenshots/`.

