# JananiSetu – Demo Video Shot List and Re-recording Commands

Capture method actually used: a scripted Chrome session (Playwright) drives the real running app and grabs screenshots at roughly 5–8 frames per second; frames are resampled to 10 fps and muxed with synthetic-voice narration using the ffmpeg bundled with `imageio-ffmpeg`. It is a real browser walkthrough of the real application, but **not** a continuous screen recorder capture, so motion is slightly stepped. Cards (title, boundary, results, close) are HTML overlays rendered in the same browser.

| Scene | Chapter | Screen | Action performed |
|---|---|---|---|
| intro, boundary | Problem and introduction | Title card; "assistive only" card | none |
| login | Login and registration | Role login → nurse dashboard | clicks the nurse account (password hint hidden) |
| register | Login and registration | Mothers & Consent | fills synthetic name/phone, registers, searches |
| upload | ANC card OCR | ANC Scans & OCR | uploads `data/fixtures/printed_clear.png`, runs OCR |
| review | ANC card OCR | per-field review panel | accepts up to six fields one by one |
| benchmark | ANC card OCR | OCR benchmark panel | runs "Measure OCR Accuracy on 3 Fixtures" (24/26) |
| confirm | ANC card OCR | confirm button | saves confirmed administrative record |
| careplan | Doctor approval and reminders | doctor login → Care Plans | authorises a visit date |
| reminders, loop | Doctor approval and reminders | Reminders & Replies | dispatches due reminders (simulator), shows delivery states |
| tasks, field | Follow-up recovery | Follow-up Tasks; Field Visits | creates a task; shows field visits |
| referral, transport | Referral and transport | Hospital Partnerships; Transport Fleet | shows synthetic partner and non-emergency boundary |
| finance, reports, audit | Budgets and accountability | admin → Contracts/Budgets, Reports, Analytics & Audit | shows simulated grant, pseudonymous report, audit trail |
| mobile | Safety and results | 390 px wide phone frame of the same app (embedded frame) | none |
| results, close | Safety and results | results/limitations card; closing card | none |

## Re-record
```powershell
# server must be running on 127.0.0.1:8000
cd C:\Projects\Healthathon\jananisetu\submission\_build\video
powershell -File tts.ps1 -Json beats.json -OutDir <wavdir>        # narration WAVs
# write <wavdir>\dur.json = {beat id: seconds}, then:
node record.mjs beats.json <wavdir>\dur.json <recdir>             # frames + timing
python -I assemble.py <recdir> <wavdir> ..\..\JananiSetu_Final_Demo.mp4
```
Replace the synthetic voice with a human voiceover by recording one WAV per beat id (same file names) and re-running `assemble.py`.
