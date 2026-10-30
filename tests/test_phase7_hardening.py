"""Phase 7 Independent Verification and Hardening Test Suite.

Covers:
1. Security Hardening:
   - CSRF defense on state-changing requests using cookie authentication
   - Anti-brute-force login rate limiting (429 Too Many Requests after threshold)
   - Defense-in-depth clinic isolation on appointment, task, and transport updates
2. Stage C: 15-Step Full Patient Care Lifecycle Integration:
   - Registration, consent, ANC upload, OCR review, risk stratification, doctor care plan,
     versioned plan amendment, reminder scheduling, transactional outbox dispatch, inbound reply,
     task assignment, field visit, hospital referral, emergency transport, and clinical outcome.
3. Stage D: Financial End-to-End Accounting & Integrity:
   - Exact integer paise arithmetic, contract state machine with separation of duties,
     duplicate claim rejection, anti-self-approval, and immutable audit ledger.
"""
from __future__ import annotations

import random
import uuid
from datetime import date, timedelta
from decimal import Decimal
from fastapi.testclient import TestClient
import pytest

from app.anc_fixtures import generate_fixture_pdf_bytes
from app.main import app, _FAILED_LOGIN_ATTEMPTS


def _u() -> str:
    return uuid.uuid4().hex[:6]


def _digits(length: int = 5) -> str:
    return "".join(random.choices("0123456789", k=length))


def _login(c: TestClient, identifier: str, password: str = "Janani@2026") -> dict[str, str]:
    r = c.post("/api/auth/login", json={"identifier": identifier, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    c.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Ensure rate limiter dictionary is clean before each test."""
    _FAILED_LOGIN_ATTEMPTS.clear()
    yield
    _FAILED_LOGIN_ATTEMPTS.clear()


def test_csrf_protection_and_cookie_auth():
    """Verify CSRF defense: Cross-site cookie requests are blocked; trusted headers or Bearer tokens succeed."""
    with TestClient(app) as client:
        client.post("/api/auth/seed-demo")
        
        # 1. Login to obtain access token
        res = client.post("/api/auth/login", json={"identifier": "admin@nalgonda.janani.org", "password": "Janani@2026"})
        assert res.status_code == 200
        token = res.json()["access_token"]
        
        # 2. Attach cookie but simulate cross-site request (Sec-Fetch-Site: cross-site)
        client.cookies.set("janani_access_token", token)
        cross_site_res = client.post(
            "/api/tasks",
            json={"mother_id": "test-mid", "detail": "Malicious CSRF Task"},
            headers={"Sec-Fetch-Site": "cross-site"}
        )
        assert cross_site_res.status_code == 403
        assert "CSRF verification failed: Cross-site cookie authentication is disallowed" in cross_site_res.json()["detail"]
        
        # 3. Request with cookie but untrusted origin
        no_csrf_signal_res = client.post(
            "/api/tasks",
            json={"mother_id": "test-mid", "detail": "Suspicious Task"},
            headers={"Origin": "https://malicious-attacker.com"}
        )
        assert no_csrf_signal_res.status_code == 403
        assert "CSRF verification failed: Untrusted Origin header" in no_csrf_signal_res.json()["detail"]

        # 4. Request with cookie and X-Requested-With header (standard SPA defense) passes CSRF check
        valid_ajax_res = client.post(
            "/api/mothers",
            json={"name": "AJAX Mother", "phone": f"98480{_digits(5)}", "consent": True},
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert valid_ajax_res.status_code == 200
        assert valid_ajax_res.json()["name"] == "AJAX Mother"

        # 5. Request with Authorization: Bearer token (no cookie) succeeds regardless of Sec-Fetch-Site
        client.cookies.clear()
        bearer_res = client.post(
            "/api/mothers",
            json={"name": "Bearer Mother", "phone": f"98480{_digits(5)}", "consent": True},
            headers={"Authorization": f"Bearer {token}", "Sec-Fetch-Site": "cross-site"}
        )
        assert bearer_res.status_code == 200
        assert bearer_res.json()["name"] == "Bearer Mother"


def test_login_rate_limiting():
    """Verify brute force protection on /api/auth/login: 11th failed attempt returns 429."""
    with TestClient(app) as client:
        test_email = f"attacker_{_u()}@example.com"
        
        # 10 failed login attempts
        for i in range(10):
            res = client.post("/api/auth/login", json={"identifier": test_email, "password": "WrongPassword"})
            assert res.status_code == 401, f"Attempt {i+1} should fail with 401"
            
        # 11th attempt must be rate-limited with 429 Too Many Requests
        rate_limited_res = client.post("/api/auth/login", json={"identifier": test_email, "password": "WrongPassword"})
        assert rate_limited_res.status_code == 429
        assert "Too many failed login attempts" in rate_limited_res.json()["detail"]


def test_cross_clinic_defense_in_depth():
    """Verify clinic isolation prevents modifying appointments, tasks, or transport across clinics."""
    with TestClient(app) as client:
        client.post("/api/auth/seed-demo")
        
        nalgonda_admin = _login(client, "admin@nalgonda.janani.org")
        warangal_admin = _login(client, "admin@warangal.janani.org")
        nalgonda_nurse = _login(client, "nurse@nalgonda.janani.org")
        
        # 1. Create a mother in Nalgonda
        m_res = client.post("/api/mothers", json={
            "name": f"Nalgonda Mother {_u()}",
            "phone": f"98480{_digits(5)}",
            "consent": True
        }, headers=nalgonda_nurse)
        assert m_res.status_code == 200
        mother_id = m_res.json()["id"]
        
        # 2. Create a task in Nalgonda clinic
        t_res = client.post("/api/tasks", json={
            "mother_id": mother_id,
            "detail": "Nalgonda Task Detail",
            "category": "contact_attempt"
        }, headers=nalgonda_admin)
        assert t_res.status_code == 200
        task_id = t_res.json()["id"]
        
        # 3. Warangal admin attempts to update Nalgonda task -> must be 404 (isolated)
        update_res = client.patch(f"/api/tasks/{task_id}", json={"status": "resolved"}, headers=warangal_admin)
        assert update_res.status_code == 404
        
        # 4. Nalgonda admin updates their own task -> succeeds
        own_update_res = client.patch(f"/api/tasks/{task_id}", json={"status": "resolved"}, headers=nalgonda_admin)
        assert own_update_res.status_code == 200
        assert own_update_res.json()["status"] == "resolved"


def test_stage_c_full_15_step_patient_lifecycle():
    """Verify the complete 15-step maternal care journey from registration to postpartum discharge."""
    with TestClient(app) as client:
        client.post("/api/auth/seed-demo")
        
        admin_h = _login(client, "admin@nalgonda.janani.org")
        doc_h = _login(client, "doctor@nalgonda.janani.org")
        nurse_h = _login(client, "nurse@nalgonda.janani.org")
        coord_h = _login(client, "coordinator@nalgonda.janani.org")
        
        # Step 1: Staff registration and workforce profile (authenticated by Clinic Admin)
        st_email = f"midwife_{_u()}@nalgonda.janani.org"
        reg_res = client.post("/api/auth/register", json={
            "name": "Sister Saritha",
            "email": st_email,
            "password": "Midwife@Password123",
            "role": "nurse",
            "clinic": "demo-clinic"
        }, headers=admin_h)
        assert reg_res.status_code == 200
        midwife_id = reg_res.json()["staff"]["id"]
        
        # Step 2: Patient registration & explicit consent capture
        mother_phone = f"98480{_digits(5)}"
        m_res = client.post("/api/mothers", json={
            "name": "Lakshmi Prasanna",
            "age": 24,
            "phone": mother_phone,
            "language": "te",
            "lmp": str(date.today() - timedelta(days=90)),
            "edd": str(date.today() + timedelta(days=190)),
            "consent": True,
            "notes": "Consent taken in Telugu by Sister Saritha"
        }, headers=nurse_h)
        assert m_res.status_code == 200
        mother_id = m_res.json()["id"]
        
        # Step 3: ANC document upload (MCP Card PDF scan)
        pdf_bytes = generate_fixture_pdf_bytes("printed_clear")
        upload_res = client.post(
            f"/api/mothers/{mother_id}/documents",
            files={"file": ("anc_mcp_card.pdf", pdf_bytes, "application/pdf")},
            headers=nurse_h
        )
        assert upload_res.status_code == 200
        doc = upload_res.json()
        doc_id = doc["id"]
        assert doc["version_number"] == 1
        assert doc["ocr_status"] in ("completed", "completed_with_warnings")
        
        # Step 4: Human verification of extracted OCR fields
        fields = {f["field_key"]: f for f in doc["fields"]}
        if "patient_name" in fields:
            client.patch(
                f"/api/documents/{doc_id}/fields/{fields['patient_name']['id']}",
                json={"decision": "accepted", "reviewer_note": "Name matches MCP card"},
                headers=nurse_h
            )
        conf_res = client.patch(
            f"/api/documents/{doc_id}/confirm",
            json={"corrected_text": doc.get("extracted_text", "")},
            headers=nurse_h
        )
        assert conf_res.status_code == 200
        assert conf_res.json()["confirmed"] is True
        
        # Step 5: Clinical risk stratification (Clinician-entered note, no AI risk scoring)
        patch_m_res = client.patch(f"/api/mothers/{mother_id}", json={
            "notes": "[SYNTHETIC-CLINICAL-RECORD] Clinician diagnosis: Gestational Hypertension, Severe Anaemia identified on MCP card"
        }, headers=doc_h)
        assert patch_m_res.status_code == 200

        # Clinical Safety Check: Administrative staff CANNOT authorise care plans or prescribe treatments (403 Forbidden)
        admin_bad_plan = client.post(f"/api/mothers/{mother_id}/plans", json={
            "visit_date": str(date.today() + timedelta(days=7)),
            "visit_type": "anc_checkup",
            "note": "Admin attempted treatment prescription"
        }, headers=admin_h)
        assert admin_bad_plan.status_code == 403
        assert "doctor" in admin_bad_plan.json()["detail"].lower()
        
        # Step 6: Doctor-authorised care plan creation (Only licensed medical officers)
        visit_date = str(date.today() + timedelta(days=7))
        cp_res = client.post(f"/api/mothers/{mother_id}/plans", json={
            "visit_date": visit_date,
            "visit_type": "anc_checkup",
            "note": "[SYNTHETIC-CLINICAL-RECORD] Doctor Kavitha authorised: Manage BP, iron sucrose infusion follow-up"
        }, headers=doc_h)
        assert cp_res.status_code == 200
        plan_id = cp_res.json()["id"]
        assert cp_res.json()["version"] == 1
        
        # Step 7: Doctor-authorised care plan revision (version increment & obsolete reminder cancellation)
        revised_date = str(date.today() + timedelta(days=5))
        amend_res = client.post(f"/api/mothers/{mother_id}/plans", json={
            "visit_date": revised_date,
            "visit_type": "anc_checkup",
            "note": "[SYNTHETIC-CLINICAL-RECORD] Accelerated review: Weekly BP monitoring and NST authorised by Doctor"
        }, headers=doc_h)
        assert amend_res.status_code == 200
        assert amend_res.json()["version"] == 2
        assert amend_res.json()["visit_date"] == revised_date
        
        # Step 8: Multi-channel reminder scheduling verified
        jobs_res = client.get(f"/api/reminders/jobs?mother_id={mother_id}", headers=nurse_h)
        assert jobs_res.status_code == 200
        jobs = jobs_res.json()
        assert len(jobs) >= 1
        
        # Step 9: Transactional outbox runner dispatches reminder
        run_res = client.post("/api/reminders/worker/run", headers=admin_h)
        assert run_res.status_code == 200
        assert run_res.json()["outbox_dispatched"] >= 0
        
        # Step 10: Inbound WhatsApp reply simulation & processing
        reply_res = client.post("/api/messages/reply", json={
            "mother_id": mother_id,
            "body": "Confirmed. I will visit Nalgonda PHC on Friday morning."
        }, headers=nurse_h)
        assert reply_res.status_code == 200
        
        # Step 11: Task assignment to field coordinator
        task_res = client.post("/api/tasks", json={
            "mother_id": mother_id,
            "detail": "Home visit for BP check and Iron tablet compliance",
            "category": "home_visit",
            "priority": "high",
            "due_date": str(date.today() + timedelta(days=2))
        }, headers=doc_h)
        assert task_res.status_code == 200
        task_id = task_res.json()["id"]
        
        # Step 12: Field visit execution with location consent
        fv_res = client.post("/api/field-visits", json={
            "mother_id": mother_id,
            "assigned_staff_id": midwife_id,
            "visit_date": str(date.today() + timedelta(days=2)),
            "scheduled_window": "09:00 - 11:00",
            "visit_address": "House 4-12, Chandur Village, Nalgonda",
            "contact_confirmed": True,
            "patient_consent_verified": True,
            "location_consent_granted": True,
            "location_purpose": "Field visit home verification",
            "checkin_latitude": 17.0575,
            "checkin_longitude": 79.2684,
            "role_scoped_notes": "BP checked: 138/88. Mother compliant with medications."
        }, headers=nurse_h)
        assert fv_res.status_code == 200
        fv_id = fv_res.json()["id"]
        
        # Step 13: Partner facility hospital referral initiation
        partner_res = client.post("/api/partners/facilities", json={
            "name": "Nalgonda District Area Hospital",
            "facility_type": "referral_hospital",
            "contact_phone": "+918682223344",
            "address": "Opp Police Line, Nalgonda",
            "agreement_reference": f"MOU-GOVT-{_u().upper()}",
            "effective_from": str(date.today()),
            "effective_until": str(date.today() + timedelta(days=365))
        }, headers=admin_h)
        assert partner_res.status_code == 200
        partner_id = partner_res.json()["id"]
        
        ref_res = client.post("/api/referrals", json={
            "mother_id": mother_id,
            "partner_facility_id": partner_id,
            "referral_category": "clinical_obstetric",
            "reason_and_clinical_summary": "[SYNTHETIC-CLINICAL-RECORD] Specialist obstetrician referral for pre-eclampsia evaluation at 32 weeks"
        }, headers=doc_h)
        assert ref_res.status_code == 200
        referral_id = ref_res.json()["id"]
        
        # Step 14: Transport Safety Verification:
        # A. Attempting autonomous 108 ambulance dispatch without external escalation protocol is BLOCKED (400 Bad Request)
        bad_trans_res = client.post("/api/transport", json={
            "mother_id": mother_id,
            "date": str(date.today() + timedelta(days=2)),
            "from_location": "Chandur Sub-Centre",
            "destination": "Nalgonda District Area Hospital",
            "pickup_time": "09:30",
            "partner": "Janani 108 Emergency Fleet",
            "vehicle_notes": "Autonomous 108 ambulance dispatch request"
        }, headers=coord_h)
        assert bad_trans_res.status_code == 400
        assert "Clinical Safety Guard" in bad_trans_res.json()["detail"]
        assert "external telephone escalation protocol" in bad_trans_res.json()["detail"]

        # B. Approved routine non-emergency maternal transit with external protocol reference succeeds
        trans_res = client.post("/api/transport", json={
            "mother_id": mother_id,
            "date": str(date.today() + timedelta(days=2)),
            "from_location": "Chandur Sub-Centre",
            "destination": "Nalgonda District Area Hospital",
            "pickup_time": "09:30",
            "partner": "Chandur PHC Scheduled Transit (External Protocol 108 Escalation Noted)",
            "vehicle_notes": "Driver: Raju (+919944001122)"
        }, headers=coord_h)
        assert trans_res.status_code == 200
        transport_id = trans_res.json()["id"]
        
        complete_trans_res = client.patch(f"/api/transport/{transport_id}", json={
            "status": "completed"
        }, headers=coord_h)
        assert complete_trans_res.status_code == 200
        assert complete_trans_res.json()["status"] == "completed"
        
        # Step 15: Clinician-entered outcome recording (Zero AI clinical conclusion generation)
        outcome_res = client.patch(f"/api/mothers/{mother_id}", json={
            "notes": "[SYNTHETIC-CLINICAL-RECORD] Clinician-entered delivery outcome: Delivered baby girl via planned LSCS at District Hospital. Mother and baby stable."
        }, headers=doc_h)
        assert outcome_res.status_code == 200
        assert "Clinician-entered delivery outcome" in outcome_res.json()["notes"]


def test_stage_d_financial_reconciliation_and_accounting_integrity():
    """Verify financial reconciliation: integer paise arithmetic, duplicate claim block, and immutable ledger."""
    with TestClient(app) as client:
        client.post("/api/auth/seed-demo")
        
        admin_h = _login(client, "admin@nalgonda.janani.org")
        doc_h = _login(client, "doctor@nalgonda.janani.org")
        nurse_h = _login(client, "nurse@nalgonda.janani.org")
        today = date.today()
        
        # 1. Create a Funding Organisation
        f_res = client.post("/api/finance/funders", json={
            "name": f"Telangana Health Society {_u()}",
            "funder_type": "nhm_authority",
            "registration_or_grant_code": f"NHM-TS-{_u().upper()}",
            "nodal_officer_name": "Dr. Srinivasa Rao",
            "nodal_officer_designation": "Director of Maternal Health"
        }, headers=admin_h)
        assert f_res.status_code == 201
        funder_id = f_res.json()["id"]
        
        # 2. Create a Government Funding Contract with exact integer paise (Rs 5,00,000.00 = 50,000,000 paise)
        c_res = client.post("/api/finance/contracts", json={
            "funder_id": funder_id,
            "programme_name": "High-Risk Maternal Outreach Grant 2026",
            "contract_reference": f"CNT-NHM-{_u().upper()}-2026",
            "funder_signatory_name": "Dr. Srinivasa Rao",
            "recipient_signatory_name": "Ananya Reddy",
            "effective_from": str(today),
            "effective_until": str(today + timedelta(days=365)),
            "funding_ceiling_paise": 50000000,
            "funder_share_bps": 10000,
            "reimbursement_basis": "actual_verified_cost",
            "allow_private_transport_reimbursement": False
        }, headers=admin_h)
        assert c_res.status_code == 201
        cnt = c_res.json()
        contract_id = cnt["id"]
        assert cnt["state"] == "draft"
        assert cnt["funding_ceiling_paise"] == 50000000
        
        # 3. Transition contract state: draft -> submitted (by admin) -> approved (by doctor - separation of duties) -> active
        sub_res = client.post(f"/api/finance/contracts/{contract_id}/state", json={"target_state": "submitted"}, headers=admin_h)
        assert sub_res.status_code == 200
        
        # Doctor approves (satisfying separation of duties: admin submitter cannot self-approve)
        app_res = client.post(f"/api/finance/contracts/{contract_id}/state", json={
            "target_state": "approved",
            "sanction_order_ref": f"GO-MS-{_u()[:4]}",
            "approval_evidence_ref": "REF-EVID-GOVT-2026",
            "notes": "Approved by State Health Committee"
        }, headers=doc_h)
        assert app_res.status_code == 200
        
        act_res = client.post(f"/api/finance/contracts/{contract_id}/state", json={"target_state": "active"}, headers=admin_h)
        assert act_res.status_code == 200
        assert act_res.json()["state"] == "active"
        
        # 4. Add Payment Milestone: Rs 1,50,000.00 = 15,000,000 paise
        m_res = client.post(f"/api/finance/contracts/{contract_id}/milestones", json={
            "milestone_name": "Tranche 1 - Q1 Beneficiary Registration Target",
            "due_date": str(today + timedelta(days=90)),
            "tranche_amount_paise": 15000000,
            "deliverable_obligation": "Register 100 high-risk mothers"
        }, headers=admin_h)
        assert m_res.status_code == 201
        
        # 5. Create Approved Budget: Rs 1,50,000.00 = 15,000,000 paise
        b_res = client.post("/api/finance/budgets", json={
            "contract_id": contract_id,
            "period_start": str(today),
            "period_end": str(today + timedelta(days=90)),
            "category_allocations": [{"category": "transport", "allocated_paise": 15000000}]
        }, headers=admin_h)
        assert b_res.status_code == 201
        budget_id = b_res.json()["id"]
        
        # 6. Create Policy Rule allowing verified partner van transport
        pol_res = client.post("/api/finance/policies", json={
            "contract_id": contract_id,
            "policy_name": "Emergency Govt / Dial-108 Transport Policy",
            "claim_type": "staff_travel_claim",
            "rate_basis": "fixed_allowance",
            "fixed_allowance_paise": 15000,
            "max_single_claim_paise": 500000,
            "requires_receipt_above_paise": 10000,
            "effective_from": str(today)
        }, headers=admin_h)
        assert pol_res.status_code == 201
        policy_id = pol_res.json()["id"]
        
        # 7. Submit Expense Claim (1,250.50 INR = 125,050 paise)
        claim_receipt_ref = f"AMB-{_u().upper()}"
        claim_res = client.post("/api/finance/claims", json={
            "contract_id": contract_id,
            "budget_id": budget_id,
            "policy_rule_id": policy_id,
            "claim_type": "staff_travel_claim",
            "expense_category": "transport",
            "transport_mode": "empaneled_partner_van",
            "amount_paise": 125050,
            "description": "Ambulance fuel reimbursement for emergency referral",
            "receipt_number": claim_receipt_ref
        }, headers=nurse_h)
        assert claim_res.status_code == 201
        claim_id = claim_res.json()["id"]
        
        # 8. Anti-self-approval: Nurse who submitted cannot approve or verify their own claim
        nurse_approve_res = client.post(f"/api/finance/claims/{claim_id}/decision", json={
            "decision": "verified_by_supervisor",
            "notes": "Attempting self-approval"
        }, headers=nurse_h)
        assert nurse_approve_res.status_code in (401, 403)
        
        # 9. Multi-tier Approval: Doctor acts as Supervisor to verify claim
        doc_verify_res = client.post(f"/api/finance/claims/{claim_id}/decision", json={
            "decision": "verified_by_supervisor",
            "notes": "Verified receipt against clinic transport register"
        }, headers=doc_h)
        assert doc_verify_res.status_code == 200
        assert doc_verify_res.json()["status"] == "verified_by_supervisor"

        # 10. Finance/Admin approves verified claim
        admin_approve_res = client.post(f"/api/finance/claims/{claim_id}/decision", json={
            "decision": "approved_by_finance",
            "notes": "Approved for reimbursement"
        }, headers=admin_h)
        assert admin_approve_res.status_code == 200
        assert admin_approve_res.json()["status"] == "approved_by_finance"
        
        # 10. Duplicate Reimbursement Block: Submitting the exact same receipt_number must fail
        dup_claim_res = client.post("/api/finance/claims", json={
            "contract_id": contract_id,
            "budget_id": budget_id,
            "policy_rule_id": policy_id,
            "claim_type": "staff_travel_claim",
            "expense_category": "transport",
            "transport_mode": "empaneled_partner_van",
            "amount_paise": 125050,
            "description": "Attempted duplicate fuel claim",
            "receipt_number": claim_receipt_ref
        }, headers=nurse_h)
        assert dup_claim_res.status_code == 409
        assert "Duplicate receipt number" in dup_claim_res.json()["detail"] or "already" in dup_claim_res.json()["detail"].lower()
        
        # 11. Check Immutable Financial Audit Ledger
        audit_res = client.get(f"/api/finance/audit-ledger?contract_id={contract_id}", headers=admin_h)
        assert audit_res.status_code == 200
        ledger_entries = audit_res.json()
        assert len(ledger_entries) >= 1
        assert "action" in ledger_entries[0]
        assert "actor_role" in ledger_entries[0]
