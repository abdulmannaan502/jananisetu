# JananiSetu – MVP Access Guide

**Accessibility status: NOT publicly deployed.** No public URL exists, and none is invented here. The evaluation panel can test the MVP by running the reproducible local demo package below, or the team can deploy it using the checklist at the end (requires the team's explicit approval; synthetic data only).

## 1. Run locally (Windows, verified 5 Nov 2026 on the build host)
Prerequisites: Python 3.14 virtual environment at `.venv`, Node.js, Tesseract OCR (`C:\Program Files\Tesseract-OCR`).

```powershell
cd C:\Projects\Healthathon\jananisetu
.\.venv\Scripts\Activate.ps1
alembic upgrade head
python -m scripts.seed_demo_data          # idempotent synthetic data
cd frontend; npm run build; cd ..         # builds into app/static/dist
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Open http://127.0.0.1:8000. `GET /api/health` should report `database_dialect: sqlite`, `messaging: simulated`, `ocr_engine: tesseract-5`, `clinical_advice: false`.

## 2. Test accounts
Four synthetic role accounts (admin, doctor, ANM nurse, field coordinator) exist in the seeded `demo-clinic`. Their emails and the shared demo password are listed in `docs/FINAL_RELEASE_AUDIT.md` section 3 and on the app's login screen. **They are deliberately not repeated in this file or in any presentation, brief or video** (the video hides the password hint). Do not reuse these credentials anywhere else.

## 3. Suggested test path (about 10 minutes)
1. Sign in as the nurse → *Mothers & Consent*: register a synthetic mother.
2. *ANC Scans & OCR*: load/upload `data/fixtures/printed_clear.png` (synthetic). Review fields, Accept/Correct/Reject, then *Save Confirmed Administrative Record*. Run *Measure OCR Accuracy on 3 Fixtures* (expect 24/26 = 92.3%).
3. Sign in as the doctor → *Care Plans & Visits*: authorise a visit date. Try the same as the nurse: expect refusal.
4. *Reminders & Replies* → *Dispatch Due Reminders Now* (local simulator).
5. *Follow-up Tasks*: create/assign a task; *Operations & Workforce*: field visits, referrals, transport.
6. Sign in as admin → *Contracts, Budgets & Finance* (simulated grant), reports, *Analytics & Audit*.

## 4. Automated checks
```powershell
python -m pytest -q                       # 57 tests
cd frontend; npx playwright test          # 7 browser tests (starts the server if needed)
```
Note: the browser journey test overwrites `docs/screenshots/` and adds synthetic rows to `data/janani.db`.

## 5. Public deployment checklist (not done; needs team approval)
- [ ] Team approves deploying and confirms synthetic data only; no real patient data ever.
- [ ] Host on HTTPS (managed PostgreSQL, `JANANI_ENV=production` so demo-account seeding is disabled; create one restricted evaluator account instead).
- [ ] Set a strong `JANANI_JWT_SECRET` and restrict `JANANI_CORS_ORIGINS`; do not use `.env.example` defaults.
- [ ] Install Tesseract in the image; confirm `/api/health`.
- [ ] Keep WhatsApp in simulator mode; banner must stay visible.
- [ ] Rate-limit and expire the evaluator account after judging; rotate secrets.
- [ ] Verify the URL from a clean browser and a phone, then add it to the deck (slide 12) and brief (page 2).
- [ ] Docker/compose, Redis/Celery and PostgreSQL were **not** run on the build host: test them before relying on them.
