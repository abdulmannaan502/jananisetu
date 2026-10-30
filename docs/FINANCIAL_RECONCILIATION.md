# JananiSetu — Financial Reconciliation & Funding Accountability

This document details the financial architecture, precision mathematical constraints, fraud-prevention rules, and government funding governance implemented in JananiSetu.

---

## 1. Precision Mathematical Model: Exact Integer Paise

To eliminate floating-point rounding errors and discrepancy risks in government maternal health audits:
- **Storage**: All monetary values are strictly stored as 64-bit integer `paise` in the database (`1 INR = 100 paise`).
- **Calculations**: Basis points calculations (e.g. funder share, statutory deductions) and attendance-based wage pro-rations are computed using Python's `decimal.Decimal` with explicit rounding modes (`ROUND_HALF_UP`) before quantizing back to exact integer paise.
- **Display Formats**: The system provides deterministic conversions to human-readable strings (e.g., `125050 paise` -> `"1250.50 INR"`).
- **Prohibition of Floats**: Native Python floating-point types (`float`) are completely prohibited in all financial math routes and database columns.

---

## 2. Multi-Tier Approval & Separation of Duties

The platform strictly enforces the following segregation-of-duties rules:
- **Contract Approval Guard**: A contract submitted by a clinic administrator cannot be approved by that same administrator. It requires an independent authorized signatory (Medical Officer or NHM Committee nodal officer).
- **Anti-Self-Approval for Claims**: Staff members (claimants or submitters) cannot verify or approve their own travel vouchers, field outreach allowances, or expense reimbursements. Any attempt returns `403 Forbidden`.
- **Two-Tier Expense Workflow**:
  1. **Submission**: Claimant submits receipt voucher, distance km, and purpose.
  2. **Supervisor Verification**: Clinical supervisor or Medical Officer verifies the clinical purpose against patient logs (`verified_by_supervisor`).
  3. **Finance Authorisation**: Administrator verifies budget line ceiling and sanctions payment (`approved_by_finance`).

---

## 3. Duplicate Prevention & Anti-Fraud Controls

- **Duplicate Receipt Rejection**: Submitting an expense claim with a receipt number or receipt content hash that has already been submitted or reimbursed returns `409 Conflict`.
- **Duplicate Payroll Batch Prevention**: Running payroll for the same clinic, staff member, and calendar period returns `409 Conflict` ("Duplicate payroll prevented for staff in period").
- **Private Transport Ban under Public Health Schemes**: Under standard NHM contracts (`allow_private_transport_reimbursement = False`), unapproved private transport claims are rejected at submission time unless an explicit policy exception is approved.
- **Overspending Ceiling**: Attempting to allocate operational budgets exceeding the sanctioned contract funding ceiling returns `400 Bad Request`.

---

## 4. Supporting Evidence Packages (Zero-PII)

For external government and CSR grant audits, the platform provides automated Supporting Evidence Package exports:
- Anonymizes beneficiary identities using SHA-256 hashed patient identifiers (`BEN-xxxx`).
- Links verified transport trips and clinic visits directly to approved expense vouchers.
- Provides proof of clinical delivery without exposing personal phone numbers, addresses, or medical diagnostic details to external financial auditors.

