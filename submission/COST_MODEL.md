# JananiSetu – Illustrative Cost Model (INR, November 2026)

**All figures are planning estimates, not vendor quotes.** No cost has been validated with a provider. Currency INR, excluding GST. WhatsApp per-message pricing was **not** checked against Meta's current India rate card; the range is a planning assumption (including a possible provider mark-up) and must be replaced by a quote.

## Assumptions
| Item | Assumption |
|---|---|
| Person-day (engineering/onboarding), blended | ₹10,000 |
| Pilot | 2 facilities, ~300 enrolled mothers, 90 days |
| Scale case for per-facility cost | 10 facilities share one deployment, 100 active mothers each |
| Messages per pregnancy | 3 reminders (app default offsets −48 h, −24 h, 0 h) × ~7 visits ≈ 21, rounded to 20 |
| Message cost (utility template incl. provider fee) | ₹0.15–0.80 |
| OCR | local Tesseract; ≈₹0 marginal per document (staff review time not costed) |
| Shared infrastructure (small VM, managed PostgreSQL, backups, monitoring) | ₹6,000–12,000 per month |

## Cost layers (kept separate)
1. **Software-only SaaS** – hosting, support, maintenance.
2. **Managed maternal-care service** – an optional coordinator running outreach for a clinic.
3. **Clinical staffing** – doctors and ANMs, paid by the facility; not included here.
4. **Transport and field operations** – trips and field-visit reimbursements; pass-through, not included.
5. **External messaging/provider charges** – WhatsApp/SMS fees, shown per message.

## Results
| Item | Calculation | Estimate |
|---|---|---|
| A. One-time, 2-facility pilot (configuration, WhatsApp onboarding, templates, training) | 15–25 person-days × ₹10,000 | ₹1.5–2.5 lakh |
| B. Ongoing infrastructure | as assumed | ₹6,000–12,000 / month |
| C. Per message / per mother | 20 × ₹0.15–0.80 | ₹3–16 per pregnancy |
| D. Per facility per month, software only | infra ₹9,000 (mid) ÷ 10 = ₹900; messages 100 mothers × ~2.2/month × ₹0.15–0.80 ≈ ₹33–176; total ≈ ₹950–1,100, rounded up for monitoring/support | ₹1,000–1,500 cost-to-serve, before margin |
| E. 90-day pilot, software | A + 3 × B + messages (300 × 20 × ₹0.15–0.80 ≈ ₹0.9k–4.8k) | ₹2.0–3.5 lakh |
| E2. 90-day pilot, optional managed coordinator | ~₹20,000–33,000 per month × 3 | ₹0.6–1.0 lakh extra |
| F. Possible revenue / funding (none secured) | facility subscription; per-enrolled-mother service fee; NGO/CSR grants; institutional or NHM procurement after evidence | – |
| G. Prerequisites | Meta WhatsApp Business verification and approved templates; DLT registration for SMS; DPDP Act compliance; hospital MoUs; clinical safety review; state-level approvals | not priced |

Infrastructure dominates at small scale; messaging matters only if reminders per mother rise sharply. Government funding is a possible future route, not secured revenue.
