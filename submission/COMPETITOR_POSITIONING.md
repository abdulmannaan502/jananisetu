# JananiSetu – Competitor and Novelty Positioning

JananiSetu is **not** the first maternal follow-up application in India and makes no patent-level novelty claim. Existing programmes already do parts of this job:

| Programme | What it does (public descriptions; secondary sources, verify before citing) | Gap relevant to JananiSetu's workflow |
|---|---|---|
| **RCH portal** (MoHFW) | Registration and tracking of mothers and children; feeds other services | Data entry is manual; it is a reporting system, not a clinic-level follow-up workflow with failed-contact recovery |
| **ANMOL** (MoHFW) | Tablet app for ANMs with due lists and data entry | Replaces paper entry with typing; no paper-card extraction, no delivery tracking of reminders |
| **Kilkari** (MoHFW) | One-way weekly voice messages to registered pregnant women and mothers, using LMP/DoB from RCH | Informational messages tied to gestational age; not tied to a doctor-authorised appointment, and no staff ownership of non-response |
| Generic HIMS/EHRs | Hospital records and billing | Heavier, electronic-only input; not designed around paper ANC cards |

## Distinctive contribution (what is actually implemented)
An integrated, evidence-linked, accountable workflow in one small system:
1. Paper-card extraction with per-field evidence and confidence (Tesseract; synthetic-card benchmark only).
2. Mandatory human verification before anything is used.
3. Doctor-only authority over visit dates; reminders derive only from them.
4. Follow-up state tracking that separates delivery, acknowledgement and attendance.
5. Failed-contact recovery: unanswered follow-ups become staff-owned tasks.
6. Audit log of actor, role and time.

Why this is operationally useful: it targets the handoff gaps between the paper record, the doctor's plan, the reminder, and the person who must act when the mother does not respond. **Not claimed:** clinical superiority, better outcomes, integration with RCH/ANMOL/Kilkari (none exists), or real-world OCR performance.
