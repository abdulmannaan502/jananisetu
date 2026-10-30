# Production completion backlog — ordered acceptance gates

The working local application is a functional foundation, **not** an end-to-end deployable medical service.

1. **Identity and security**: replace public demo role creation and X-Staff-ID with verified authentication, session/refresh token protections, staff invitations, fine-grained permissions, clinic tenancy and tests against IDOR. Gate: every endpoint unauthorized-by-default, audited.
2. **Operational data**: migrate SQLite to PostgreSQL with Alembic, clinic foreign keys everywhere, field encryption as required, data retention, consent history and deletion workflows. Gate: tenant leak tests and restores tested.
3. **Documents**: secured object storage, anti-malware scanning, OCR source bounding boxes, typed fields with confidence, versioned human approval, explicit LMP/EDD handling with *no* AI clinical inference. Gate: human sees source evidence and changes before approval.
4. **Care plans and scheduler**: date-driven durable Celery/Redis tasks; staff-approved reminder schedules; cancel/supersede on plan revisions; idempotent sends; delivery-receipt handling. Gate: survives restart and repeated webhooks.
5. **WhatsApp**: official API adapter, opt-in checks, approved templates, secure webhook verification, provider delivery failures and retries. Gate: sandbox signed-webhook tests and live provider test with an authorised test number.
6. **Language**: reviewed Telugu/Hindi/English copy with access to recorded voice/TTS if approved; safe fallback channels. Gate: human translation sign-off.
7. **Workforce**: scheduled visits, clinical staff rosters and identity/credential verification, worker routing, attendance with consent, verified service reports. Gate: supervisor approval and no fabricated visits.
8. **Clinical operations**: only with licensed care partners, clinician-authored notes, referrals and lab partner workflows; secure clinical records and professional review. Gate: real clinic protocol and legal sign-off.
9. **Transport**: provider-approved partners, entitlement checks, booking integrations where available, no dispatch claims without provider confirmation, safety escalation pathways. Gate: full reconciliation on mock provider and approved live sandbox.
10. **Finance**: restricted budgets, dual approvals, receipts, exports, document attachment, procurement contract mappings, government-specific reporting only after contract requirements are known. Gate: independently traceable and reviewable ledger.
11. **Production quality**: HTTPS, monitoring, encrypted backups, disaster recovery, CI/CD, load tests, full browser Playwright scenarios and vulnerability review. Gate: independent deployment checklist.
12. **Evidence and outcomes**: synthetic demo test cases, study metrics definitions, IRB/ethics/privacy evaluation where applicable, actual pilot baseline and verified outcome evaluation. Gate: no unsubstantiated clinical efficacy claim.

## Competitor/novelty positioning

The meaningful differentiator is NOT OCR, reminder messages or clinician staffing individually. It is the auditable integration of handwritten-plan verification, signed human coordination, follow-up lifecycle and documented field outcomes. A definitive first-in-market or patent novelty claim has NOT been established.
