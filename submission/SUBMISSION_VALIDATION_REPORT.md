# JananiSetu – Submission Validation Report (5 Nov 2026)

**Nothing has been submitted to the Health-a-thon portal.** Submission needs the team's explicit approval, a confirmed portal deadline/timezone (not available to this audit; 7 Nov 2026 is treated as the internal deadline), and the placeholders below filled.

## 1. Deliverables
| Deliverable | File | Status |
|---|---|---|
| A. Functional MVP | https://jananisetu-demo.onrender.com (Render free plan, synthetic data); `MVP_ACCESS_GUIDE.md`, `MVP_VERIFICATION_REPORT.md`, `FORM_FIELDS_TO_PASTE.md` | **Live and checked on 7 Nov 2026 from this machine only** (health, doctor/nurse login, OCR upload, benchmark 24/26). Not yet checked from another network or a phone. Free plan sleeps when idle. |
| B. Final presentation | `JananiSetu_Healthathon_Final_Presentation.pptx` (+ `JananiSetu_Final_Presentation.pdf`) | Built by editing the official template: 12 slides, original order and headings. Every slide rendered and inspected (twice). |
| C. Two-page brief | `JananiSetu_Two_Page_Solution_Brief.pptx` (+ PDF) | Edited the official template: exactly 2 pages, all 11 sections filled. Removed a stray leftover word ("Armman") from the template's page 1. |
| D. Demo video | `JananiSetu_Final_Demo.mp4` (6 min 29 s, 1280×720, 10 fps, AAC) | Produced (see 3). Script and shot list: `VIDEO_RECORDING_SCRIPT.md`, `VIDEO_SHOT_LIST.md`. |
| Supporting | `EVIDENCE_REGISTER.md`, `COST_MODEL.md`, `COMPETITOR_POSITIONING.md`, `screenshots/` (15 synthetic-data screenshots) | – |

## 2. Fresh verification (5 Nov 2026)
57/57 pytest; 7/7 Playwright; OCR 24/26 (92.3%) on 3 synthetic fixtures re-computed. Details: `MVP_VERIFICATION_REPORT.md`.

## 3. Video checks
- Duration 6:29 (limit 7:00); frame gaps ≤ 0.12 s after re-recording (the first take had a 30 s capture stall and was discarded).
- It is a scripted real-browser walkthrough of the running app (frames captured from Chrome), not a continuous screen-recorder capture; the narration is a synthetic TTS voice (Microsoft Zira). Audio is placed at each scene's measured start time; spot frames at 16 scenes were inspected and matched their narration and captions.
- During the take the nurse accepted six OCR fields and saved (audit log: `confirm_extraction … confirmed_fields=6`), the doctor authorised a date, reminders were dispatched via the simulator, a task was created, and finance/audit screens were shown.
- The login screen's demo-password hint is hidden in the recording. Permanent badge: "SYNTHETIC DATA | WHATSAPP = LOCAL SIMULATOR".
- The video was re-rendered after the team details arrived; opening and closing cards now name Team Zulfiqar, Abdul Mannaan Sayyad and Dr. Sarwaat Ayesha.
- Known blemishes: some captions cover the bottom of the UI; the phone view is an embedded 390 px frame, not a resized browser. I did not listen to the audio end-to-end; sync was checked from timing data and frames only.

## 4. Integrity checks
- No invented team, doctor, affiliation, partnership, URL, grant or outcome: all are marked `[… TO CONFIRM]`.
- No password in the deck, brief, PDFs, video or screenshots (screenshot 01 and the misleading screenshot 05 were left out).
- Synthetic data only; screenshots show "(Demo NNNN)" names and synthetic personas.
- Claims corrected relative to older repo docs: audit hashing, salted beneficiary hashes, geo-tagging, Kilkari = SMS (EVIDENCE_REGISTER rows 14–17). Those older docs in `docs/` have **not** been edited and still contain the over-claims.
- The requested subtitle said "handwritten ANC records"; it was changed to "paper ANC records" because OCR was only tested on typeset synthetic cards.
- Automated scan of both PPTX files: no shapes outside the slide; no leftover template instructions.

## 5. Unresolved blockers / information needed
Filled from the team (5-7 Nov 2026): team name **Zulfiqar**; engineer **Abdul Mannaan Sayyad**; doctor partner **Dr. Sarwaat Ayesha** (shown as "Dr." with no qualification or speciality stated, as instructed); contact email; "share publicly" = **No**; no dated milestones; repository not shared publicly.
1. **Team code** (slides 1, 12) – still a placeholder.
2. Experience details for both members, and the doctor's actual role in reviewing the workflow (slide 2, brief page 1) – placeholders. No clinical validation or endorsement is claimed. Note: the organiser's rules reportedly require each final team to include a *practising* doctor as Clinical Lead; the team should confirm eligibility.
3. Video link https://youtu.be/5K3hKn5RtTE and MVP link are now on slide 12 and brief page 2. The video lacks the team-introduction and doctor-collaboration segment the form asks for.
4. Test the MVP and video links in a private window before ticking the form's checkbox.
5. Portal deadline: the Internshala listing (single secondary source, not cross-checked) gives **8 Nov 2026**; timezone unknown. Confirm on the portal.
6. No calendar dates are used for sprint milestones (per instruction).
7. Statistics: re-check NFHS-5 and SRS figures against primary reports; WhatsApp and hosting prices against vendor quotes (COST_MODEL.md).
8. Optional: replace the TTS voice with a human voiceover; the PPT text-fit was checked via PowerPoint rendering on this machine only.
9. Not verified anywhere: live WhatsApp, Redis/Celery, Docker, PostgreSQL, real handwritten cards.

## 6. Housekeeping
The E2E run overwrote `docs/screenshots/*` and changed `data/janani.db`; `git status` shows these as modified and nothing was committed. Build scripts live in `submission/_build/` and can be deleted before sharing.

## 7. Hosting findings (7 Nov 2026)
On Render the benchmark first scored 42.3% (11/26) because synthetic cards were rendered with a fallback font on Linux; Tesseract itself was fine (the Windows-made PNG uploaded to Render OCR'd perfectly). Fixed by evaluating committed reference PNGs; the live benchmark now returns 24/26. The 15 s OCR timeout also failed on the free CPU and is now configurable. A clean-data-dir run of the full suite after the change gave 57 passed; re-running tests against a reused `data/janani.db` can fail because some tests are not idempotent on a dirty database.
