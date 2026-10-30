# JananiSetu — Novelty, Innovation & Differentiation Analysis

JananiSetu differentiates itself from existing public healthcare tools (e.g., ANMOL, RCH Portal, Kilkari) and generic hospital information management systems (HIMS) across five foundational architectural pillars.

---

## 1. Comparative Architecture Matrix

| Dimension | Standard Public Portals (ANMOL / RCH) | Generic Hospital EHRs | JananiSetu (Health-a-thon 2026) |
| :--- | :--- | :--- | :--- |
| **Digitisation Paradigm** | Manual, labor-intensive re-typing of paper MCP records. | Electronic-only input; physical scans stored as unindexed PDFs. | **Evidence-Linked Human OCR**: Dual-view bounding-box provenance linking extracted text to the physical card. |
| **Follow-up Reliability** | One-way bulk SMS blasts without delivery or read tracking. | Fragmented appointment portals requiring smartphone app install. | **Closed-Loop Durable Outbox**: WhatsApp & localized SMS tracking with automated task escalation for unacknowledged drop-offs. |
| **Clinical Governance** | Flexible data entry allowing non-doctors to record clinical plans. | Complex role systems often bypassed in emergency settings. | **Hardened Clinical Authority**: Mathematical role boundaries (`permitted(s, "doctor")`) blocking administrative prescribing. |
| **Mobility & Transit** | No integration with community transport. | Private ambulance dispatch stubs. | **Empaneled Maternal Transit Hub**: Driver/licence verification with strict separation from emergency 108 telephone protocols. |
| **Funding Accountability** | Aggregated annual financial reports disconnected from service events. | Proprietary billing systems with exposed patient PII. | **Paise-Accurate Evidence Packages**: Integer-paise accounting linking service events to grant tranches with zero patient PII. |

---

## 2. Five Core Technical Differentiators

### 1. Evidence-Linked Bounding Box Provenance (No Black-Box AI)
Unlike black-box AI tools that output unverified text, JananiSetu normalizes OCR coordinates to canvas percentage vectors, allowing healthcare workers to visually audit the source of every digitised character on the scanned MCP card.

### 2. Transactional Outbox Pattern for Rural Messaging
Standard webhooks suffer from lost notifications when workers restart or mobile signals fade. JananiSetu persists every reminder to the database within the doctor's atomic transaction, guaranteeing at-least-once delivery with exponential backoff and dead-letter queueing.

### 3. Closed-Loop Escalation Cycle
When an expectant mother fails to acknowledge an upcoming appointment reminder, JananiSetu does not simply mark the message as failed. It automatically spawns a geo-tagged outreach task for the assigned field coordinator or ANM nurse, closing the care loop.

### 4. Zero-PII Cryptographic Service-to-Funding Evidence
Public health financing requires verifying that funds were actually spent on eligible beneficiaries. JananiSetu compiles verifiable service evidence packages using salted SHA-256 hashes (`BEN-<sha256>`), allowing government and CSR auditors to verify deliverable completion without compromising patient privacy under the Indian DPDP Act.

### 5. Mathematical Exactness in Financial Systems
By enforcing integer paise (`amount_paise`) throughout all database schemas, API models, and frontend displays, JananiSetu eliminates floating-point rounding discrepancies that plague public health grant accounting.

