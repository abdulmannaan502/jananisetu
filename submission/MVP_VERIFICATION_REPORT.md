# JananiSetu – MVP Verification Report (5 Nov 2026)

Environment: Windows 10, Python 3.14.3, SQLite, Chrome (Playwright), local Tesseract 5, uvicorn on 127.0.0.1:8000. No code was rewritten for this submission. Defects found are listed in section 3.

## 1. Fresh test runs
| Check | Result |
|---|---|
| `python -m pytest -q` | **57 passed** in 42.96 s (1 deprecation warning) |
| `npx playwright test` | **7 passed** in 37.3 s |
| OCR benchmark (`evaluate_fixtures_benchmark`) | 24/26 = 92.3% (10/10, 8/10, 6/6) on 3 synthetic fixtures |
| `GET /api/health` | ok; sqlite; messaging simulated; OCR tesseract-5; clinical_advice/diagnosis/risk scoring false |
| Frontend build | not re-run (the existing `app/static/dist` served correctly) |

## 2. Required-area check
| # | Area | Evidence | Verdict |
|---|---|---|---|
| 1 | Authentication and roles | phase2/3/7 tests; login screen; role-restricted care-plan test | Verified |
| 2 | Patient registration and consent | phase4 test_01; E2E test 2; screenshot 02 | Verified |
| 3 | ANC document upload | phase3 tests (JPG/PNG/PDF, malicious/oversize rejection); screenshot 03 | Verified (synthetic files) |
| 4 | Real OCR extraction | Tesseract run on fixtures, result above | Verified – synthetic only |
| 5 | Evidence-linked human verification | phase3 versioning/proposal tests; screenshot 05 shows per-field Accept/Correct/Reject | Verified in UI; **see defect D1** |
| 6 | Doctor-authorised follow-up dates | phase5 test_04, phase7b clinical authority | Verified |
| 7 | Persistent reminder scheduling | phase4 tests (IST offsets, outbox, restart recovery) | Verified (DB outbox, not Redis) |
| 8 | WhatsApp communication | simulator only; signed-webhook tests | Simulated – labelled in UI banner |
| 9 | Staff follow-up task assignment | phase4 test_10/11; screenshot 09 | Verified |
| 10 | Field visits | phase5 test_06 | Verified |
| 11 | Partner referral records | phase5 test_07 | Verified (synthetic partners) |
| 12 | Non-emergency transport | phase5 test_08; phase7b emergency guard | Verified |
| 13 | Budget and finance tracking | phase6 tests, phase7 reconciliation | Verified (simulated grant) |
| 14 | Audit history | events table, screenshot 16 | Verified; not cryptographically chained |
| 15 | Dashboard metrics | screenshots 08, 16 | Verified visually |
| 16 | Responsive usability | E2E test 6; screenshot 17 (375×667) | Verified |

A complete synthetic-patient workflow was also driven through the browser while recording the demo video (see SUBMISSION_VALIDATION_REPORT.md for what that run did and did not exercise).

## 3. Defects and over-claims found (not code-fixed; wording corrected in submission)
- **D1** The E2E "human verification confirmed" step clicks *Save Confirmed Administrative Record* without accepting any field: the 5 Nov audit log shows `confirm_extraction … confirmed_fields=0`, and `05_human_verification_confirmed.png` shows fields still "UNREVIEWED". That screenshot is therefore **not** used as proof of confirmation. The demo video accepts fields before saving.
- **D2** Several E2E steps are guarded by `if (isVisible())`, so a pass is weaker than it looks.
- **D3** Older docs overstate audit hashing, beneficiary-hash salting, geo-tagging, and describe Kilkari as SMS (see EVIDENCE_REGISTER rows 14–17).
- **D4** The login screen displays the shared demo password; this is acceptable for a local synthetic demo but must be removed (or the accounts restricted) before any public deployment. Screenshot `01_…` is excluded for this reason.
- **D5** Conflict card: Tesseract read "2026-11-28" as "2926-11-28"; the conflict is flagged for human review, but the value is not self-corrected.

## 4. Not verified
Live WhatsApp; Redis/Celery workers; Docker; PostgreSQL run; real handwritten cards; any real clinical use; any public deployment.
