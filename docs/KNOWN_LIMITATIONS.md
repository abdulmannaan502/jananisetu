# JananiSetu — Known Limitations & Operational Boundaries

In accordance with strict healthcare software disclosure standards, this document lists all known operational boundaries, external dependencies, and simulated capabilities in the current release.

---

## 1. External Integrations: Simulated vs. Integrated

| Integration | Claimed Reality | Technical Reality in Codebase |
| :--- | :--- | :--- |
| **Emergency 108 / 102 Ambulance** | **No API Integration** | There is **no automated API dispatch** with National Health Mission / GVK EMRI emergency dispatchers. Autonomous dispatch via API is rejected with `400 Bad Request`. System enforces a strict telephone escalation protocol. |
| **Meta WhatsApp Cloud API** | **Simulated Adapter** | Uses `WhatsAppSimulator` providing signed webhook emulation (`X-Hub-Signature-256`), delivery status callbacks, and out-of-order deduplication. Live delivery requires Meta WABA enterprise credentials and Indian DLT registration. |
| **Government PFMS / Treasury** | **Simulated Approval** | Contract sanction orders and funding tranches are clearly tagged with `[SIMULATED]`. No live integration with the Public Financial Management System (PFMS) exists. |
| **SMS DLT Gateway** | **Adapter Mock** | Trai DLT template registration headers are formatted correctly, but carrier dispatch runs through a logging stub. |

---

## 2. Infrastructure Limitations on Local Host

1. **Host Docker CLI**:
   - The current Windows host does not have the Docker CLI installed.
   - While `Dockerfile` and `docker-compose.yml` are production-grade and tested for Linux/Docker environments, local execution on this host runs directly via Python 3.14 venv and Uvicorn.
2. **Local Redis Absence**:
   - Background queuing defaults to the database Transactional Outbox engine (`/api/reminders/worker/run`), ensuring ACID transactional durability without requiring a separate Redis daemon.
3. **Local OCR Variability**:
   - Tesseract-5 execution on distorted or low-contrast mobile phone camera scans requires adequate lighting and resolution (≥200 DPI). Degraded handwriting falls back to human verification queues.

---

## 3. Data Privacy & Clinical Boundaries

1. **No Autonomous AI Diagnosis**:
   - JananiSetu will **never diagnose medical conditions**, calculate automated obstetric risk scores, or prescribe clinical therapies.
   - Care plan dates and medical advice can only be authorised by licensed clinicians (`doctor` role).
2. **Synthetic Data Only**:
   - All demonstration data in this repository consists entirely of synthetic names, synthetic phone numbers (`9800000xxx`, `98490xxxxx`), and synthetic financial amounts. No real patient data exists in this codebase.
