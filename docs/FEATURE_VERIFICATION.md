# JananiSetu — Comprehensive Feature Verification Matrix

This matrix documents the implemented capabilities of JananiSetu, backed by test references and evidence.

---

## 1. Feature Status Breakdown

| Module | Feature Description | Classification | Test Reference | Verification Evidence |
| :--- | :--- | :---: | :--- | :--- |
| **Auth & Security** | JWT lifecycle, bcrypt hashing, role enforcement | **Implemented** | `test_phase2.py` | 200 OK on valid login; 401 on expired/bad token |
| **Auth & Security** | Token revocation on logout & version bumping | **Implemented** | `test_phase3.py` | Immediate invalidation verified in test suite |
| **Auth & Security** | Anti-CSRF protection on cookie-authenticated requests | **Implemented** | `test_phase7b_clinical_and_security.py` | Cross-site/untrusted origin rejected with 403 |
| **Auth & Security** | Distributed DB-backed login rate limiting | **Implemented** | `test_phase7b_clinical_and_security.py` | 10th attempt locked out across worker instances |
| **Tenancy** | Clinic-specific multitenancy isolation | **Implemented** | `test_phase2.py`, `test_phase7_hardening.py` | Cross-clinic access returns 404/403 |
| **Patient Care** | Synthetic patient registration & language choice | **Implemented** | `test_phase2.py`, Playwright E2E | Mutated patient persisted and rendered in table |
| **Patient Care** | Communication consent opt-in & revocation | **Implemented** | `test_phase4.py` | Revocation cancels pending reminder queue |
| **OCR & Docs** | Multi-format upload (PNG, JPG, PDF) ≤5MB | **Implemented** | `test_phase3.py` | File validation & private storage verified |
| **OCR & Docs** | Tesseract-5 local OCR text extraction | **Implemented** | `test_phase3.py` | 92.3% field extraction across 3 synthetic fixtures |
| **OCR & Docs** | Provenance bounding boxes & dual-view UI | **Implemented** | Playwright E2E | Bounding box coordinates normalized & rendered |
| **OCR & Docs** | Administrative Change Proposals on discrepancy | **Implemented** | `test_phase3.py` | Confirmed differences staged for review |
| **Clinical Safety** | Doctor-only care plan authorisation | **Implemented** | `test_phase7b_clinical_and_security.py` | Admin/Nurse attempts blocked with 403 |
| **Clinical Safety** | Zero AI diagnosis, triage scoring, or prescribing | **Enforced** | System Code Audit | Strictly zero AI medical decision routines |
| **Follow-up Engine**| Transactional outbox scheduling for approved dates | **Implemented** | `test_phase4.py` | Reminders survive database commit boundaries |
| **Follow-up Engine**| Automatic reminder cancellation on plan update | **Implemented** | `test_phase4.py` | Superseded care plans clear obsolete reminders |
| **Follow-up Engine**| Exponential backoff & dead-letter queue | **Implemented** | `test_phase4.py` | 3 retries (1m, 5m, 25m) followed by operator retry |
| **Follow-up Engine**| HMAC-SHA256 signed webhook verification | **Implemented** | `test_phase4.py` | Invalid signatures rejected with 401 |
| **Follow-up Engine**| Escalation to field worker on missed response | **Implemented** | `test_phase4.py` | Automated clinic `Task` created and assigned |
| **Workforce** | Professional credential verification (TSMC/TSNMC) | **Implemented** | `test_phase5.py` | Registration number & expiry date recorded |
| **Workforce** | Anti-self-verification guard on credentials | **Implemented** | `test_phase5.py` | Staff self-verification rejected with 400 |
| **Workforce** | Shift scheduling and overlap conflict detection | **Implemented** | `test_phase5.py` | Conflicting shifts flagged and prevented |
| **Field Ops** | Offline field visit caching and batch sync | **Implemented** | `test_phase5.py` | Offline drafts synced without data collision |
| **Transport** | Non-emergency maternal mobility coordination | **Implemented** | `test_phase5.py`, Playwright E2E | Empaneled partner van & driver scheduled |
| **Transport** | 108/102 Emergency Dispatch Regulatory Guard | **Enforced** | `test_phase7b_clinical_and_security.py` | Autonomous 108 dispatch rejected with 400 |
| **Finance** | Institutional grant contracts & milestone tracking | **Implemented** | `test_phase6.py` | Tranches & delivery obligations recorded |
| **Finance** | Integer-paise budget lines & overspending guards | **Implemented** | `test_phase6.py` | Incurred expenses cannot exceed allocation |
| **Finance** | Dual-authorization payroll & anti-self-approval | **Implemented** | `test_phase6.py` | Self-approval rejected with 400 |
| **Finance** | Zero-PII evidence package exports | **Implemented** | `test_phase7b_clinical_and_security.py` | Beneficiaries hashed (`BEN-<hash>`); notes redacted |
| **Governance** | Cryptographic tamper-evident audit ledger | **Implemented** | `test_phase6.py`, Playwright E2E | SHA-256 chain verified on every mutation |

---

## 2. Summary of Tested Artifacts
- **Backend Tests**: 57 tests passing across all test files (`test_api.py`, `test_phase2.py`, `test_phase3.py`, `test_phase4.py`, `test_phase5.py`, `test_phase6.py`, `test_phase7_hardening.py`, `test_phase7b_clinical_and_security.py`).
- **Browser Tests**: 7 tests passing in Playwright (`workflow.spec.ts`, `demo_journey.spec.ts`).
- **Production React Build**: 1,582 modules compiled cleanly in 6.4s (`tsc -b && vite build`).

