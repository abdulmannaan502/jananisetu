# Phase 2 form: what to paste where (status 7 Nov 2026)

## 1. Functional Solution MVP (link, credentials, access instructions)
Verified live on 7 Nov 2026 (from this machine, not from a phone or another network): `https://jananisetu-demo.onrender.com` returns `status ok`, simulator messaging, Tesseract; doctor and nurse logins work; an ANC card upload runs OCR; the "Measure OCR Accuracy" benchmark returns 24/26 (92.3%), matching the local result after the fixes below.

Paste (the demo password is in `docs/FINAL_RELEASE_AUDIT.md` section 3 and on the login screen; put it in the form field only):

> JananiSetu staff web app. Synthetic data only; WhatsApp is a local simulator. Free hosting: the first load can take about a minute to wake.
> Link: https://jananisetu-demo.onrender.com
> Login: click any one-click role account on the sign-in screen (Clinic Admin, Dr. Kavitha Rao (doctor), Lakshmi Devi (ANM nurse), Padma Kumari (field coordinator)); the shared password is shown on that screen: [PASSWORD].
> 10-minute path: (1) nurse > Mothers & Consent: register a synthetic mother; (2) ANC Scans & OCR: click "#1 Printed PNG", review fields (Accept / Correct / Reject), Save Confirmed Administrative Record, then "Measure OCR Accuracy on 3 Fixtures"; (3) doctor > Care Plans & Visits: authorise a visit date; (4) Reminders & Replies > Dispatch Due Reminders Now; (5) Follow-up Tasks, Operations & Workforce; (6) admin > Contracts, Budgets & Finance, Analytics & Audit.
> Source repository: private, not shared; no access steps needed.

## 2. Two-page overview
Upload `JananiSetu_Two_Page_Solution_Brief.pdf` (or `.pptx`). Contains the MVP and video links. Placeholders left: experience details for both members, Dr. Sarwaat Ayesha's role.

## 3. Final presentation
Upload `JananiSetu_Final_Presentation.pdf` (or `.pptx`). The form says "complete every placeholder". Still open: **team code**, member experience, the doctor's role. The form also asks for "team collaboration with doctor and technology partners": slide 2 has no collaboration description because no facts were supplied.

## 4. Demo walkthrough video
https://youtu.be/5K3hKn5RtTE (opens without a Google sign-in from this machine; check in a private window yourself). The form wants the team introduced, the approach, and the collaboration with doctor and technology partners; the current video only has a title card for the team and no collaboration segment.

## Fixes made while publishing (all pushed to the private repo)
- Start command: inline `dockerCommand` failed on Render; replaced by `scripts/start_demo.sh`.
- OCR timeout: the hard 15 s Tesseract limit failed on Render's free CPU; now `JANANI_OCR_TIMEOUT` (set to 180 in `render.yaml`).
- Benchmark mismatch: on Linux the synthetic cards were rendered with a fallback bitmap font and scored 42.3% (11/26) instead of 92.3%. The benchmark now uses the committed reference PNGs (`data/fixtures`), so every host gives 24/26. The 24/26 figure is unchanged; it is a result on 3 fixed synthetic images.
