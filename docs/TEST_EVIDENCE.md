# JananiSetu — Comprehensive Test Evidence & Audit Logs

## 1. Automated Backend Test Execution (`pytest`)

**Execution Command**: `.\.venv\Scripts\python.exe -m pytest -v`  
**Execution Environment**: Python 3.14.3, Pytest 9.2.0, Windows host  
**Total Tests**: 57  
**Passed**: 57 (100% Pass Rate)  
**Execution Time**: 81.21 seconds

```
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.2.0, pluggy-1.7.0 -- C:\Projects\Healthathon\jananisetu\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Projects\Healthathon\jananisetu
plugins: anyio-4.15.1
collected 57 items

tests/test_api.py::test_flow PASSED                                      [  1%]
tests/test_phase2.py::test_authentication_and_jwt_lifecycle PASSED       [  3%]
tests/test_phase2.py::test_role_based_access_control PASSED              [  5%]
tests/test_phase2.py::test_cross_clinic_data_isolation PASSED            [  7%]
tests/test_phase2.py::test_patient_documents_appointments_tasks_transport_expenses PASSED [  8%]
tests/test_phase2.py::test_data_migration_utility PASSED                 [ 10%]
tests/test_phase2.py::test_health_and_frontend_serving PASSED            [ 12%]
tests/test_phase3.py::test_phase2_security_hardening_and_token_revocation PASSED [ 14%]
tests/test_phase3.py::test_valid_image_and_pdf_uploads_and_ocr_extraction PASSED [ 15%]
tests/test_phase3.py::test_unsupported_malicious_and_external_provider_safeguards PASSED [ 17%]
tests/test_phase3.py::test_missing_uncertain_conflicting_fields_and_no_clinical_inference PASSED [ 19%]
tests/test_phase3.py::test_human_verification_versioning_and_change_proposals PASSED [ 21%]
tests/test_phase3.py::test_cross_clinic_and_role_based_document_isolation_and_persistence PASSED [ 22%]
tests/test_phase4.py::test_01_consent_enforcement_and_opt_out_cancellation PASSED [ 24%]
tests/test_phase4.py::test_02_reminder_creation_from_doctor_approved_plan_with_ist_offsets PASSED [ 26%]
tests/test_phase4.py::test_03_automatic_cancellation_when_plan_is_superseded PASSED [ 28%]
tests/test_phase4.py::test_04_idempotent_scheduling_and_transactional_outbox PASSED [ 29%]
tests/test_phase4.py::test_05_exponential_backoff_retry_and_dead_letter_with_operator_retry PASSED [ 31%]
tests/test_phase4.py::test_06_signed_webhook_verification_hmac_sha256 PASSED [ 33%]
tests/test_phase4.py::test_07_duplicate_webhook_event_idempotency PASSED [ 35%]
tests/test_phase4.py::test_08_out_of_order_delivery_status_callbacks_never_downgrade PASSED [ 36%]
tests/test_phase4.py::test_09_patient_acknowledgement_and_closed_loop_distinct_stages PASSED [ 38%]
tests/test_phase4.py::test_10_unacknowledged_reminder_escalation_creates_clinic_followup_task PASSED [ 40%]
tests/test_phase4.py::test_11_staff_contact_attempt_logging_and_supervisor_escalation PASSED [ 42%]
tests/test_phase4.py::test_12_invalid_state_transition_rejection PASSED  [ 43%]
tests/test_phase4.py::test_13_caregiver_permission_enforcement_and_privacy_guard PASSED [ 45%]
tests/test_phase4.py::test_14_cross_clinic_isolation_across_reminders_messages_tasks_caregivers PASSED [ 47%]
tests/test_phase4.py::test_15_worker_restart_recovery_from_transactional_outbox_and_clinician_review PASSED [ 49%]
tests/test_phase5.py::test_01_doctor_and_nurse_onboarding_and_employment_role_separation PASSED [ 50%]
tests/test_phase5.py::test_02_credential_verification_and_anti_self_verification PASSED [ 52%]
tests/test_phase5.py::test_03_shift_assignment_and_conflict_detection PASSED [ 54%]
tests/test_phase5.py::test_04_role_permission_enforcement_and_clinical_authority PASSED [ 56%]
tests/test_phase5.py::test_05_service_request_lifecycle_and_cancellation_reassignment PASSED [ 57%]
tests/test_phase5.py::test_06_field_visit_lifecycle_location_consent_guard_and_offline_sync PASSED [ 59%]
tests/test_phase5.py::test_07_partner_hospital_registration_and_clinician_authorised_referral_lifecycle PASSED [ 61%]
tests/test_phase5.py::test_08_transport_partner_driver_verification_trip_lifecycle_and_failed_pickup PASSED [ 63%]
tests/test_phase5.py::test_09_cross_clinic_access_denial_across_all_phase5_modules PASSED [ 64%]
tests/test_phase5.py::test_10_governance_incidents_record_corrections_and_db_persistence PASSED [ 66%]
tests/test_phase5.py::test_11_end_to_end_10_step_operational_scenario_and_dashboard PASSED [ 68%]
tests/test_phase6.py::test_01_contract_lifecycle_and_draft_governance_guard PASSED [ 70%]
tests/test_phase6.py::test_02_contract_funding_ceilings_milestones_and_amendments PASSED [ 71%]
tests/test_phase6.py::test_03_programme_budgets_overspending_guard_and_amendments PASSED [ 73%]
tests/test_phase6.py::test_04_and_05_and_06_payroll_calculation_attendance_rules_duplicate_prevention_and_anti_self_approval PASSED [ 75%]
tests/test_phase6.py::test_07_and_08_and_09_expense_claims_anti_self_approval_duplicate_and_private_transport_guards_and_trip_reconciliation PASSED [ 77%]
tests/test_phase6.py::test_10_service_to_funding_evidence_package_and_unverifiable_claim_rejection PASSED [ 78%]
tests/test_phase6.py::test_11_audit_ledger_idempotency_concurrency_and_versioned_corrections PASSED [ 80%]
tests/test_phase6.py::test_12_permissions_cross_clinic_isolation_exports_and_12_step_e2e_scenario PASSED [ 82%]
tests/test_phase7_hardening.py::test_csrf_protection_and_cookie_auth PASSED [ 84%]
tests/test_phase7_hardening.py::test_login_rate_limiting PASSED          [ 85%]
tests/test_phase7_hardening.py::test_cross_clinic_defense_in_depth PASSED [ 87%]
tests/test_phase7_hardening.py::test_stage_c_full_15_step_patient_lifecycle PASSED [ 89%]
tests/test_phase7_hardening.py::test_stage_d_financial_reconciliation_and_accounting_integrity PASSED [ 91%]
tests/test_phase7b_clinical_and_security.py::test_distributed_multi_worker_login_rate_limiting PASSED [ 92%]
tests/test_phase7b_clinical_and_security.py::test_advanced_csrf_defense_scenarios PASSED [ 94%]
tests/test_phase7b_clinical_and_security.py::test_clinical_authority_boundaries_and_anti_administrative_prescribing PASSED [ 96%]
tests/test_phase7b_clinical_and_security.py::test_emergency_transport_regulatory_guard PASSED [ 98%]
tests/test_phase7b_clinical_and_security.py::test_zero_pii_in_financial_evidence_and_exports PASSED [100%]

================== 57 passed, 1 warning in 81.21s ===================
```

---

## 2. Browser End-to-End Test Execution (`playwright`)

**Execution Command**: `cd frontend; npx playwright test`  
**Execution Environment**: Chromium Headless, Node.js v22  
**Total Tests**: 7  
**Passed**: 7 (100% Pass Rate)  
**Execution Time**: 42.5 seconds

```
Running 7 tests using 1 worker

  ok 1 e2e\demo_journey.spec.ts:26:3 › JananiSetu 16-Step Guided Demonstration Journey › Execute complete 16-step maternal care, clinical safety & financial governance journey (25.6s)
  ok 2 e2e\workflow.spec.ts:18:3 › JananiSetu End-to-End System & Usability Audit › 1. Authentication, Role Dashboards, and Session Management (966ms)
  ok 3 e2e\workflow.spec.ts:29:3 › JananiSetu End-to-End System & Usability Audit › 2. Patient Registration, Consent & List Persistence (3.3s)
  ok 4 e2e\workflow.spec.ts:69:3 › JananiSetu End-to-End System & Usability Audit › 3. Doctor CarePlan Authorisation & Followup Communication Hub (2.5s)
  ok 5 e2e\workflow.spec.ts:103:3 › JananiSetu End-to-End System & Usability Audit › 4. Workforce, Field Operations & Transport Operations Hub (2.1s)
  ok 6 e2e\workflow.spec.ts:121:3 › JananiSetu End-to-End System & Usability Audit › 5. Financial Accountability Hub & Funding Governance (2.1s)
  ok 7 e2e\workflow.spec.ts:139:3 › JananiSetu End-to-End System & Usability Audit › 6. Responsive Layout & Usability Verification (1.5s)

  7 passed (42.5s)
```

---

## 3. Frontend Production Build Verification

**Execution Command**: `cd frontend; npm run build`  
**Result**: 1,582 modules compiled without TypeScript errors. Bundled artifacts output cleanly to `app/static/dist`.
- `index.html`: `0.48 kB`
- `assets/index-*.css`: `40.92 kB`
- `assets/index-*.js`: `398.42 kB`
- Build Duration: `6.41 seconds`

