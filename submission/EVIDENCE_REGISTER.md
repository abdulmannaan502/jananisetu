# JananiSetu – Evidence Register (Health-a-thon 2026 final submission)

Prepared 5 Nov 2026 from the repository at `C:\Projects\Healthathon\jananisetu` (HEAD `0e1cdd5`). Status key: **VERIFIED** (re-run or inspected in this audit), **LOCAL** (works only on local infrastructure), **SIMULATED**, **UNVERIFIED**, **CORRECTED** (an earlier project document overstated it), **MISSING** (no information exists).

| # | Claim | Source / how checked | Status | Permitted wording |
|---|---|---|---|---|
| 1 | 57 backend tests pass | `pytest -q` re-run 5 Nov 2026: `57 passed, 1 warning in 42.96s` | VERIFIED | "57/57 backend tests passed (re-run 5 Nov 2026)." |
| 2 | 7 browser E2E tests pass | `npx playwright test` re-run 5 Nov 2026: `7 passed (37.3s)`, Chrome headless | VERIFIED | "7/7 browser tests passed." The journey spec guards several steps with `if (visible)`, so a pass does not prove every optional step executed. |
| 3 | OCR 24/26 fields = 92.3% | `evaluate_fixtures_benchmark()` re-run: printed_clear 10/10 (mean conf 95.1); partially_handwritten 8/10 (conf 90.6; date misread as "2926-11-28"); difficult_incomplete 6/6 (conf 93.3; two absent fields correctly flagged) | VERIFIED – synthetic only | "24 of 26 labelled fields matched on 3 synthetic, machine-generated ANC cards." Never "real-world accuracy"; never "handwriting accuracy" (the "handwritten" card is typeset in a font). The fixtures were used during development. |
| 4 | OCR engine | `requirements.txt`, `app/ocr_engine.py`; `/api/health` reports `tesseract-5`, `external_ocr_enabled:false` | VERIFIED | "Local Tesseract OCR." |
| 5 | AI / LLM use | grep of `app/` and `requirements.txt` finds no LLM, OpenAI, Anthropic, Bhashini or Twilio code | VERIFIED | "The only AI component is Tesseract OCR; no generative AI." Round 1 items (GPT-4o/Claude extraction, Bhashini voice, keyword triage, ranked daily call list) were **not built**. |
| 6 | WhatsApp | `messaging.py`; `/api/health` `messaging: simulated`; Meta Cloud adapter coded, no live credentials | SIMULATED / UNVERIFIED | "WhatsApp is simulated locally; a Meta Cloud API adapter is coded but not verified live." |
| 7 | Redis / Celery | `celery_app.py` exists; no Redis on host; DB outbox runs jobs | UNVERIFIED | "Coded, not exercised." |
| 8 | PostgreSQL | demo runs SQLite (`database_dialect: sqlite`); PostgreSQL compatibility asserted in earlier audit, not run here | LOCAL / UNVERIFIED | "SQLite for the demo; PostgreSQL-ready." |
| 9 | Docker | no Docker CLI on host | UNVERIFIED | Do not claim containerised deployment works. |
| 10 | Doctor-only care plans | `test_phase5::test_04_*`, `test_phase7b::test_clinical_authority_*` pass | VERIFIED | "Non-doctor roles receive 403 when authorising plans." |
| 11 | Consent / opt-out cancels reminders | `test_phase4::test_01_*`, `test_03_*` pass | VERIFIED | As stated. |
| 12 | Clinic isolation | cross-clinic tests in phases 2, 4, 5, 7 pass | VERIFIED | As stated. |
| 13 | Signed webhooks, retry, dead-letter | `test_phase4::test_05–08` pass against the simulator (HMAC-SHA256) | VERIFIED – simulated provider | "Tested against the simulator." |
| 14 | "Cryptographic tamper-evident audit with SHA-256 integrity hashes" (older docs) | `Event` model has no hash or chain; SHA-256 is used for uploaded files and webhook payloads only | **CORRECTED** | "Append-only audit/event log with actor, role, time." Do not claim cryptographic tamper-evidence. |
| 15 | "Salted SHA-256 beneficiary hashes" (older docs) | `anonymise_beneficiary_ref` = unsalted `sha256(clinic:mother_id)[:10]` | **CORRECTED** | "Pseudonymous beneficiary reference (BEN-…); treat as personal data." |
| 16 | "Geo-tagged outreach tasks" (older docs) | location check-in is optional and consent-gated | **CORRECTED** | Do not claim geo-tagging. |
| 17 | "Kilkari/ANMOL send one-way bulk SMS" (older docs) | Kilkari is an MoHFW voice (IVR) service fed from RCH; ANMOL is an ANM tablet app | **CORRECTED** | Describe Kilkari as one-way voice messages. |
| 18 | Government funding / NHM contract | seed data tagged "SIMULATED / DEMO APPROVAL ONLY", ₹25,00,000 | SIMULATED | "Simulated grant workflow; no real NHM sanction; no secured funding." |
| 19 | Hospital / transport partners | synthetic seeded records; no MoUs | SIMULATED | "Synthetic partner records; no real agreements." |
| 20 | Doctor partner / team members | Supplied by the team in chat on 5 Nov 2026: Abdul Mannaan Sayyad (engineer), Dr. Sarwaat Ayesha (doctor partner; shown as "Dr." only). No document substantiates experience or any clinical review. "Dr. Kavitha Rao" is a seeded demo persona | TEAM-SUPPLIED | Name and role as given. No speciality, experience, validation or endorsement claimed. |
| 21 | Team name, team code, contact email | Name "Zulfiqar" and email supplied in chat; team code not supplied | PARTIAL | Team code stays a placeholder. |
| 22 | About 58% of women had 4+ ANC visits | NFHS-5 (2019-21): 58.1% in secondary summaries; NFHS-6 restates NFHS-5 as 58.5% | VERIFIED via secondary sources | "About 58% (NFHS-5, 2019-21)." Re-check against the IIPS report PDF before final. |
| 23 | MMR 88 per 100,000 live births | RGI SRS Special Bulletin on Maternal Mortality 2020-22 (via search summary) | VERIFIED via secondary summary | National context only, not causal. |
| 24 | Round 1: "2nd–3rd trimester is when most follow-ups are missed" | no source | UNVERIFIED | Dropped. |
| 25 | Four-week sprint timeline | `git log`: 3 commits 29–30 Oct 2026 (squashed); tag v2.0 30 Oct | PARTIAL | Week labels indicative; dates TO CONFIRM by team. |
| 26 | Code size | `wc -l`: app/*.py 17,079; frontend components 6,195 | VERIFIED | "about 17,000 lines Python, 6,200 TS/TSX". |
| 27 | Patient outcomes, time saved | none measured | NOT DEMONSTRATED | "Expected; to be measured in a pilot." |
| 28 | DPDP / ISO 14971 / DCB0129 | docs say "aligned with principles"; no assessment | UNVERIFIED | "Designed with these principles in mind; not assessed or certified." |
| 29 | Costs | `submission/COST_MODEL.md` | ESTIMATE | "Illustrative estimate, not vendor quotes." WhatsApp rate not checked against Meta's rate card. |
| 30 | Screenshots | 16 PNGs in `submission/screenshots/`, regenerated by the 5 Nov E2E run; `01_staff_login…` excluded because it displays the demo password | VERIFIED | Synthetic data only. |
| 31 | Portal deadline | not available to this audit | UNVERIFIED | Treat 7 Nov 2026 as internal deadline; team must confirm the portal deadline and timezone. |

## Information the team must supply
Team name and code; member names, roles, experience; named doctor (name, speciality, experience, role) and affiliation; contact email; actual portal deadline/timezone; Yes/No on public sharing; video hosting link; MVP URL (none exists); whether the repository may be shared.
