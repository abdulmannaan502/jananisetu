# JananiSetu — Clinical Safety Boundaries & Governance Charter

**Version**: 2.0 (Phase 8 Final Release)  
**Standard**: Aligned with principles of ISO 14971 (Medical Device Risk Management) and NHS DCB0129 (Clinical Risk Management for Health IT Systems).

---

## 1. Non-Negotiable Clinical Safety Rules

### Rule 1: Absolute Prohibition of AI Diagnosis & Automated Risk Scoring
JananiSetu is strictly an **operational care-coordination platform**, NOT a diagnostic medical device or clinical decision support system (CDSS).
- The platform does **not** evaluate laboratory test results (e.g., hemoglobin levels, proteinuria).
- The platform does **not** categorize pregnancies into autonomous "High-Risk Pregnancy (HRP)" tiers.
- Any clinical triage or risk assessment must be performed directly by a licensed medical practitioner.

### Rule 2: Strict Clinician Prescribing Boundary
- Administrative personnel (`admin`), field coordinators (`field_coordinator`), and nursing staff (`nurse`) are programmatically barred from authorising medical care plans or prescribing clinical treatments.
- Any non-clinician attempt to submit or alter a patient's care plan visit schedule returns `403 Forbidden` (`"Insufficient role ... Permitted roles: doctor"`).

### Rule 3: No Autonomous Emergency Dispatch
- Expectant mothers experiencing acute obstetric emergencies (e.g. eclamptic seizures, antepartum hemorrhage, obstructed labor) must **never** depend on automated web requests.
- The platform explicitly prohibits autonomous ambulance booking via 108/102.
- Any API call attempting to register an emergency dispatch returns `400 Bad Request` with instructions directing staff to execute the verbal emergency protocol: **Dial 108 immediately**.

### Rule 4: Human-in-the-Loop OCR Verification
- Optical Character Recognition (OCR) is inherently probabilistic.
- Text extracted from physical Mother & Child Protection (MCP) cards is presented as a draft overlay with bounding-box visual provenance.
- Extracted values **never** overwrite existing medical records automatically. Confirmed differences are held in an `Administrative Change Proposal` queue requiring explicit review.

---

## 2. Hazard Identification & Risk Controls

| Identified Clinical Hazard | Potential Harm | System Risk Control | Residual Risk |
| :--- | :--- | :--- | :---: |
| **Misread EDD Date from Scanned MCP Card** | Premature or delayed induction of labor | OCR values are flagged `UNCONFIRMED` until validated by staff; doctor's authorized CarePlan always supersedes OCR text. | **LOW** |
| **False Reliance on App for Ambulance Dispatch** | Delayed emergency obstetric care (EmOC) | Autonomous 108 dispatch blocked via API; persistent UI banners reinforce direct telephone protocol. | **NEGLIGIBLE** |
| **Administrative Override of Doctor Plan** | Inappropriate visit frequency for vulnerable mother | Strict RBAC (`permitted(s, "doctor")`) on CarePlan mutations. | **LOW** |
| **Unintended Message Delivery after Opt-Out** | Privacy violation & patient distress | Dynamic consent check on every reminder outbox dispatch; revocation cancels all pending reminders immediately. | **LOW** |
| **Secondary Caregiver Privacy Breach** | Disclosure of sensitive maternal health data to unauthorized family members | Caregivers must have explicit recorded consent and relation verification before receiving notification duplicates. | **LOW** |

