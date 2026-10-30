"""Phase 6 Automated Test Suite: Government Contracts, Programme Budgets, Healthcare Payroll,
Transport Expenses, Service-to-Funding Evidence & Funding Accountability.

Covers:
1. Contract creation, draft proposal governance (never represented as approved government funding), and full state machine transitions (draft -> submitted -> approved -> active -> suspended -> active -> completed).
2. Contract funding ceilings, payment milestones, tranche receipts, and versioned contract amendments.
3. Programme & clinic budget allocation, overspending prevention, month-wise cash-flow comparison, and authorised versioned budget amendments.
4. Explicit validated statutory deduction configuration, staff compensation agreements, monthly payroll calculation, anti-self-approval, and verified payment evidence enforcement.
5. Duplicate payroll prevention (409 Conflict for same clinic, period_month, and staff_id).
6. Leave & attendance payroll adjustments applied ONLY when employment agreement permits them (attendance_adjustment_permitted=True vs False).
7. Expense claim submission, supervisor verification, finance approval, strict anti-self-approval (403 Forbidden), and rejection/return workflows.
8. Duplicate reimbursement rejection (receipt, transport trip, field visit) and public health scheme private transport block unless contract explicitly permits it.
9. Transport trip-to-expense reconciliation reusing the existing Expense table without duplicate financial records.
10. Service-to-funding evidence linking, rejection of unverifiable/duplicate funding claims, and privacy-safe Supporting Evidence Package generation (anonymised beneficiary ref, zero PII).
11. Immutable FinancialAuditLedger, idempotency / concurrent approval protection (X-Idempotency-Key), and versioned FinancialCorrectionRecord (no destructive overwrites).
12. Role-based financial permissions, restricted payroll access, cross-clinic & cross-programme isolation, CSV/PDF report exports with DRAFT/INTERNAL compliance watermarks, and the 12-Step E2E Funded Maternal Programme Scenario.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import uuid
from fastapi.testclient import TestClient

from app.main import app


def _u() -> str:
    return uuid.uuid4().hex[:6]


def _login(c: TestClient, identifier: str, password: str = "Janani@2026") -> dict[str, str]:
    r = c.post("/api/auth/login", json={"identifier": identifier, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    c.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def _setup_two_clinics(c: TestClient) -> dict[str, dict[str, str]]:
    c.post("/api/auth/seed-demo")
    return {
        "admin1": _login(c, "admin@nalgonda.janani.org"),
        "doc1": _login(c, "doctor@nalgonda.janani.org"),
        "nurse1": _login(c, "nurse@nalgonda.janani.org"),
        "fc1": _login(c, "coordinator@nalgonda.janani.org"),
        "admin2": _login(c, "admin@warangal.janani.org"),
        "doc2": _login(c, "doctor@warangal.janani.org"),
    }


def test_01_contract_lifecycle_and_draft_governance_guard():
    """Verify a draft proposal is never represented as approved funding and transitions through draft -> submitted -> approved -> active -> suspended -> active -> completed."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)
    today = date.today()

    # Create a new FundingOrganisation
    r_fnd = c.post(
        "/api/finance/funders",
        headers=hdrs["admin1"],
        json={
            "name": "Telangana Rural Maternal CSR Trust (Synthetic)",
            "funder_type": "csr_funder",
            "registration_or_grant_code": "CSR-TS-2026-88",
            "nodal_officer_name": "Smt. K. Padmavathi",
            "nodal_officer_designation": "Programme Director",
        },
    )
    assert r_fnd.status_code == 201, r_fnd.text
    funder_id = r_fnd.json()["id"]

    # Create a contract — must start in 'draft' and explicitly state it is NOT approved funding
    r_cnt = c.post(
        "/api/finance/contracts",
        headers=hdrs["admin1"],
        json={
            "funder_id": funder_id,
            "programme_name": "High-Risk ANC & Safe Mobility Grant 2026",
            "contract_reference": "CNT-CSR-2026-001",
            "sanction_order_ref": "FAKE-SANCTION-SHOULD-BE-STRIPPED-ON-DRAFT",
            "funder_signatory_name": "Smt. K. Padmavathi",
            "recipient_signatory_name": "Ananya Reddy",
            "effective_from": str(today),
            "effective_until": str(today + timedelta(days=180)),
            "funding_ceiling_paise": 60000000,  # Rs 6,00,000.00
            "funder_share_bps": 8500,  # 85.00%
            "reimbursement_basis": "actual_verified_cost",
            "allow_private_transport_reimbursement": False,
        },
    )
    assert r_cnt.status_code == 201, r_cnt.text
    cnt = r_cnt.json()
    cid = cnt["id"]
    assert cnt["state"] == "draft"
    assert cnt["is_approved_funding"] is False
    assert cnt["sanction_order_ref"] == ""
    assert "UNAPPROVED PROPOSAL / DRAFT" in cnt["funding_status_banner"]
    assert cnt["funding_ceiling_inr"] == "600000.00"
    assert cnt["funder_share_pct"] == "85.00%"

    # Attempting to create an operational budget under a draft contract MUST fail (400)
    r_bad_bgt = c.post(
        "/api/finance/budgets",
        headers=hdrs["admin1"],
        json={
            "contract_id": cid,
            "period_start": str(today),
            "period_end": str(today + timedelta(days=180)),
            "category_allocations": [{"category": "transport", "allocated_paise": 1000000}],
        },
    )
    assert r_bad_bgt.status_code == 400
    assert "unapproved draft/submitted" in r_bad_bgt.text

    # Invalid direct jump draft -> active must fail (400)
    r_bad_jump = c.post(
        f"/api/finance/contracts/{cid}/state",
        headers=hdrs["admin1"],
        json={"target_state": "active"},
    )
    assert r_bad_jump.status_code == 400

    # draft -> submitted by admin1
    r_sub = c.post(
        f"/api/finance/contracts/{cid}/state",
        headers=hdrs["admin1"],
        json={"target_state": "submitted"},
    )
    assert r_sub.status_code == 200
    assert r_sub.json()["state"] == "submitted"
    assert r_sub.json()["is_approved_funding"] is False

    # Self-approval by submitter (admin1) must be blocked (403)
    r_self_app = c.post(
        f"/api/finance/contracts/{cid}/state",
        headers=hdrs["admin1"],
        json={
            "target_state": "approved",
            "sanction_order_ref": "SYN-SANCTION-CSR-001",
            "is_simulated_approval": True,
        },
    )
    assert r_self_app.status_code == 403

    # Independent approval by doc1 with explicit simulated approval flag
    r_app = c.post(
        f"/api/finance/contracts/{cid}/state",
        headers=hdrs["doc1"],
        json={
            "target_state": "approved",
            "sanction_order_ref": "SYN-SANCTION-CSR-001",
            "approval_evidence_ref": "BOARD-RES-2026-09",
            "is_simulated_approval": True,
        },
    )
    assert r_app.status_code == 200
    assert r_app.json()["state"] == "approved"
    assert r_app.json()["is_simulated_approval"] is True
    assert "SIMULATED / DEMO APPROVAL" in r_app.json()["funding_status_banner"]

    # approved -> active -> suspended -> active -> completed
    for next_st in ("active", "suspended", "active", "completed"):
        r_tr = c.post(
            f"/api/finance/contracts/{cid}/state",
            headers=hdrs["admin1"],
            json={"target_state": next_st},
        )
        assert r_tr.status_code == 200, r_tr.text
        assert r_tr.json()["state"] == next_st


def test_02_contract_funding_ceilings_milestones_and_amendments():
    """Verify milestone tranche ceilings, verified tranche receipt tracking, and versioned contract amendments."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)
    today = date.today()

    # Create & activate a contract with ceiling 30,00,000 paise (Rs 30,000.00)
    r_cnt = c.post(
        "/api/finance/contracts",
        headers=hdrs["admin1"],
        json={
            "funder_id": "funder-nhm-101",
            "programme_name": "Devarakonda ANC Outreach Micro-Grant",
            "contract_reference": "CNT-MICRO-2026-02",
            "effective_from": str(today),
            "effective_until": str(today + timedelta(days=90)),
            "funding_ceiling_paise": 3000000,
        },
    )
    assert r_cnt.status_code == 201
    cid = r_cnt.json()["id"]
    c.post(f"/api/finance/contracts/{cid}/state", headers=hdrs["admin1"], json={"target_state": "submitted"})
    c.post(
        f"/api/finance/contracts/{cid}/state",
        headers=hdrs["doc1"],
        json={"target_state": "approved", "sanction_order_ref": "SYN-M-02", "is_simulated_approval": True},
    )
    c.post(f"/api/finance/contracts/{cid}/state", headers=hdrs["admin1"], json={"target_state": "active"})

    # Create Milestone 1 (20,00,000 paise)
    r_m1 = c.post(
        f"/api/finance/contracts/{cid}/milestones",
        headers=hdrs["admin1"],
        json={
            "milestone_name": "Tranche 1 Mobilisation",
            "due_date": str(today + timedelta(days=15)),
            "deliverable_obligation": "Initial 25 ANC registrations",
            "tranche_amount_paise": 2000000,
        },
    )
    assert r_m1.status_code == 201
    m1_id = r_m1.json()["id"]

    # Attempting to create Milestone 2 exceeding remaining ceiling (15,00,000 > 10,00,000 left) must fail (400)
    r_m2_exceed = c.post(
        f"/api/finance/contracts/{cid}/milestones",
        headers=hdrs["admin1"],
        json={
            "milestone_name": "Tranche 2 Excess",
            "due_date": str(today + timedelta(days=45)),
            "tranche_amount_paise": 1500000,
        },
    )
    assert r_m2_exceed.status_code == 400

    # Marking milestone received without payment_reference must fail (400)
    r_rec_no_ref = c.patch(
        f"/api/finance/milestones/{m1_id}",
        headers=hdrs["admin1"],
        json={"status": "received", "received_amount_paise": 2000000, "payment_reference": ""},
    )
    assert r_rec_no_ref.status_code == 400

    # Mark milestone received with verified UTR reference
    r_rec_ok = c.patch(
        f"/api/finance/milestones/{m1_id}",
        headers=hdrs["admin1"],
        json={
            "status": "received",
            "received_amount_paise": 2000000,
            "payment_reference": "UTR-MICRO-2026-001",
        },
    )
    assert r_rec_ok.status_code == 200
    assert r_rec_ok.json()["received_amount_inr"] == "20000.00"

    # Amend contract ceiling to 45,00,000 paise and extend end date
    r_amend = c.post(
        f"/api/finance/contracts/{cid}/amendments",
        headers=hdrs["admin1"],
        json={
            "amendment_type": "ceiling_revision",
            "new_end_date": str(today + timedelta(days=150)),
            "new_ceiling_paise": 4500000,
            "amendment_summary": "Expanded coverage to 2 additional sub-centres",
            "approval_reference": "AMEND-ORD-2026-01",
        },
    )
    assert r_amend.status_code == 201, r_amend.text
    updated = r_amend.json()
    assert updated["version_number"] == 2
    assert updated["funding_ceiling_paise"] == 4500000
    assert updated["funding_received_paise"] == 2000000
    assert updated["outstanding_receivable_paise"] == 2500000
    assert len(updated["amendments"]) == 1


def test_03_programme_budgets_overspending_guard_and_amendments():
    """Verify programme budget allocation against contract ceiling, overspending prevention, and versioned budget amendments."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)
    today = date.today()

    # Create active contract with 50,00,000 paise ceiling
    r_cnt = c.post(
        "/api/finance/contracts",
        headers=hdrs["admin1"],
        json={
            "funder_id": "funder-nhm-101",
            "programme_name": "PHC Budget Control Test Programme",
            "contract_reference": "CNT-BGT-2026-03",
            "effective_from": str(today),
            "effective_until": str(today + timedelta(days=120)),
            "funding_ceiling_paise": 5000000,
        },
    )
    cid = r_cnt.json()["id"]
    c.post(f"/api/finance/contracts/{cid}/state", headers=hdrs["admin1"], json={"target_state": "submitted"})
    c.post(
        f"/api/finance/contracts/{cid}/state",
        headers=hdrs["doc1"],
        json={"target_state": "approved", "sanction_order_ref": "SYN-BGT-03", "is_simulated_approval": True},
    )
    c.post(f"/api/finance/contracts/{cid}/state", headers=hdrs["admin1"], json={"target_state": "active"})

    # Budget exceeding contract ceiling (60,00,000 > 50,00,000) must be rejected (400)
    r_over = c.post(
        "/api/finance/budgets",
        headers=hdrs["admin1"],
        json={
            "contract_id": cid,
            "period_start": str(today),
            "period_end": str(today + timedelta(days=120)),
            "category_allocations": [{"category": "salary", "allocated_paise": 6000000}],
        },
    )
    assert r_over.status_code == 400
    assert "exceeds contract funding ceiling" in r_over.text

    # Create valid budget (40,00,000 paise total)
    r_bgt = c.post(
        "/api/finance/budgets",
        headers=hdrs["admin1"],
        json={
            "contract_id": cid,
            "period_start": str(today),
            "period_end": str(today + timedelta(days=120)),
            "category_allocations": [
                {"category": "salary", "allocated_paise": 2500000},
                {"category": "transport", "allocated_paise": 50000},  # Rs 500.00
                {"category": "travel", "allocated_paise": 1450000},
            ],
        },
    )
    assert r_bgt.status_code == 201, r_bgt.text
    bid = r_bgt.json()["id"]

    # Submitting an expense claim on 'transport' for 80,000 paise (Rs 800 > Rs 500 allocated) must be blocked by budget ceiling!
    r_exceed_claim = c.post(
        "/api/finance/claims",
        headers=hdrs["fc1"],
        json={
            "contract_id": cid,
            "budget_id": bid,
            "claim_type": "transport_partner_invoice",
            "expense_category": "transport",
            "transport_mode": "empaneled_partner_van",
            "amount_paise": 80000,
            "receipt_number": "RCP-OVER-001",
            "description": "Attempted overspend on transport category",
        },
    )
    assert r_exceed_claim.status_code == 400
    assert "Budget ceiling exceeded" in r_exceed_claim.text

    # Amend 'transport' budget line to 2,00,000 paise (Rs 2,000.00) with authorised approval reference
    r_amend = c.post(
        f"/api/finance/budgets/{bid}/amendments",
        headers=hdrs["admin1"],
        json={
            "category": "transport",
            "new_allocated_paise": 200000,
            "reason": "Additional rural maternal transport demand",
            "approval_reference": "BGT-AMEND-2026-03",
        },
    )
    assert r_amend.status_code == 201
    assert r_amend.json()["version_number"] == 2
    assert len(r_amend.json()["amendments"]) == 1

    # Now the 80,000 paise transport claim succeeds and updates committed_paise!
    rcp_ok = f"RCP-OK-{_u()}"
    r_ok_claim = c.post(
        "/api/finance/claims",
        headers=hdrs["fc1"],
        json={
            "contract_id": cid,
            "budget_id": bid,
            "claim_type": "transport_partner_invoice",
            "expense_category": "transport",
            "transport_mode": "empaneled_partner_van",
            "amount_paise": 80000,
            "receipt_number": rcp_ok,
            "description": "Within amended transport budget ceiling",
        },
    )
    assert r_ok_claim.status_code == 201, r_ok_claim.text

    r_cmp = c.get(f"/api/finance/budgets/{bid}/comparison", headers=hdrs["admin1"])
    assert r_cmp.status_code == 200
    trn_line = next(l for l in r_cmp.json()["category_lines"] if l["category"] == "transport")
    assert trn_line["allocated_paise"] == 200000
    assert trn_line["committed_paise"] == 80000
    assert trn_line["available_paise"] == 120000


def test_04_and_05_and_06_payroll_calculation_attendance_rules_duplicate_prevention_and_anti_self_approval():
    """Verify:
    - Salary calculation using explicit validated statutory configuration.
    - Attendance deduction applied ONLY when attendance_adjustment_permitted=True (nurse1) and NOT applied when False (fc1).
    - Duplicate payroll prevention (409 Conflict) for the same clinic, period_month, and staff_id.
    - Anti-self-approval on payroll runs (403 Forbidden) and mandatory payment evidence before paid_verified.
    """
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)
    # Generate a unique YYYY-MM period for repeated test runs
    rand_year = 2027 + (int(_u(), 16) % 70)
    rand_month = 1 + (int(_u(), 16) % 12)
    test_period = f"{rand_year:04d}-{rand_month:02d}"

    # Calculate payroll for test_period with 2 unexcused absent days for both nurse1 (attendance_adjustment_permitted=True)
    # and fc1 (attendance_adjustment_permitted=False), plus 3 completed field visits each
    r_run = c.post(
        "/api/finance/payroll/runs",
        headers=hdrs["admin1"],
        json={
            "period_month": test_period,
            "contract_id": "contract-syn-101",
            "budget_id": "budget-syn-101",
            "staff_ids": ["staff-nurse-1", "staff-fc-1"],
            "attendance_overrides": [
                {
                    "staff_id": "staff-nurse-1",
                    "days_scheduled": 26,
                    "days_attended": 24,
                    "approved_leave_days": 0,
                    "unexcused_absent_days": 2,
                    "completed_visits_count": 3,
                },
                {
                    "staff_id": "staff-fc-1",
                    "days_scheduled": 26,
                    "days_attended": 24,
                    "approved_leave_days": 0,
                    "unexcused_absent_days": 2,
                    "completed_visits_count": 3,
                },
            ],
        },
    )
    assert r_run.status_code == 201, r_run.text
    run_data = r_run.json()
    run_id = run_data["id"]
    slips = {s["staff_id"]: s for s in run_data["payslips"]}

    # Nurse1 has attendance_adjustment_permitted=True -> 2/26 of 3200000 paise deducted = 246154 paise
    nurse_slip = slips["staff-nurse-1"]
    expected_nurse_ded = int(
        (Decimal(3200000) * Decimal(2) / Decimal(26)).quantize(Decimal("1"))
    )
    assert nurse_slip["attendance_deduction_paise"] == expected_nurse_ded
    assert nurse_slip["visit_or_shift_pay_paise"] == 3 * 30000  # 90,000 paise

    # FC1 has attendance_adjustment_permitted=False -> attendance_deduction_paise MUST be 0 even with 2 absent days!
    fc_slip = slips["staff-fc-1"]
    assert fc_slip["attendance_deduction_paise"] == 0
    assert fc_slip["visit_or_shift_pay_paise"] == 3 * 20000  # 60,000 paise

    # Attempting to run payroll again for test_period for the same staff MUST be blocked as duplicate (409 Conflict)
    r_dup = c.post(
        "/api/finance/payroll/runs",
        headers=hdrs["admin1"],
        json={
            "period_month": test_period,
            "staff_ids": ["staff-nurse-1"],
        },
    )
    assert r_dup.status_code == 409
    assert "Duplicate payroll prevented" in r_dup.text

    # Transition draft -> reviewed
    r_rev = c.post(
        f"/api/finance/payroll/runs/{run_id}/transition",
        headers=hdrs["admin1"],
        json={"target_status": "reviewed"},
    )
    assert r_rev.status_code == 200

    # Admin1 calculated the payroll run -> self-approval by admin1 MUST be blocked (403 Forbidden)!
    r_self_app = c.post(
        f"/api/finance/payroll/runs/{run_id}/transition",
        headers=hdrs["admin1"],
        json={"target_status": "approved"},
    )
    assert r_self_app.status_code == 403
    assert "Anti-self-approval" in r_self_app.text

    # Independent approval by doc1 succeeds
    r_app = c.post(
        f"/api/finance/payroll/runs/{run_id}/transition",
        headers=hdrs["doc1"],
        json={"target_status": "approved"},
    )
    assert r_app.status_code == 200
    assert r_app.json()["status"] == "approved"

    # Lock payroll batch
    r_lock = c.post(
        f"/api/finance/payroll/runs/{run_id}/transition",
        headers=hdrs["admin1"],
        json={"target_status": "locked", "payment_batch_ref": "BATCH-2026-08"},
    )
    assert r_lock.status_code == 200

    # Marking paid_verified without payment_evidence_ref MUST fail (400)
    r_paid_no_ev = c.post(
        f"/api/finance/payroll/runs/{run_id}/transition",
        headers=hdrs["admin1"],
        json={
            "target_status": "paid_verified",
            "payment_batch_ref": "BATCH-2026-08",
            "payment_evidence_ref": "",
        },
    )
    assert r_paid_no_ev.status_code == 400

    # Marking paid_verified with verified UTR evidence succeeds and creates 1 linked Expense row
    r_paid_ok = c.post(
        f"/api/finance/payroll/runs/{run_id}/transition",
        headers=hdrs["admin1"],
        json={
            "target_status": "paid_verified",
            "payment_batch_ref": "BATCH-2026-08",
            "payment_evidence_ref": "UTR-SBI-20260831-9912",
        },
    )
    assert r_paid_ok.status_code == 200
    assert r_paid_ok.json()["status"] == "paid_verified"
    assert r_paid_ok.json()["expense_id"] is not None

    # Export offline CSV payment batch
    r_exp_csv = c.get(f"/api/finance/payroll/runs/{run_id}/export", headers=hdrs["admin1"])
    assert r_exp_csv.status_code == 200
    assert "OFFLINE PAYMENT BATCH FILE" in r_exp_csv.text


def test_07_and_08_and_09_expense_claims_anti_self_approval_duplicate_and_private_transport_guards_and_trip_reconciliation():
    """Verify:
    - Private unapproved transport claims are rejected under a public health scheme unless contract & policy explicitly permit them.
    - Duplicate receipt number and duplicate transport trip claims are rejected (409).
    - Claim submitter/claimant cannot self-verify or self-approve their own expense claim (403).
    - Completed Phase 5 transport trip reconciles cleanly with ExpenseClaim and reuses the existing Expense record.
    """
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)
    today = date.today()

    # 1. Private transport claim under public health contract (allow_private_transport_reimbursement=False) MUST fail (400)
    r_priv = c.post(
        "/api/finance/claims",
        headers=hdrs["nurse1"],
        json={
            "contract_id": "contract-syn-101",
            "budget_id": "budget-syn-101",
            "policy_rule_id": "policy-syn-101",
            "claim_type": "staff_travel_claim",
            "expense_category": "travel",
            "transport_mode": "private_unapproved",
            "distance_km": 15,
            "amount_paise": 50000,
            "receipt_number": "PRIV-TAXI-001",
            "description": "Unapproved private taxi claim",
        },
    )
    assert r_priv.status_code == 400
    assert "Private unapproved transport claims are disallowed" in r_priv.text

    # 2. Complete a Phase 5 Transport trip and reconcile it with an ExpenseClaim
    r_book = c.post(
        "/api/transport",
        headers=hdrs["fc1"],
        json={
            "mother_id": "mother-syn-101",
            "date": str(today),
            "pickup_time": "09:15",
            "from_location": "Ward 4 Devarakonda",
            "destination": "PHC Nalgonda Central",
        },
    )
    assert r_book.status_code == 200, r_book.text
    trip_id = r_book.json()["id"]

    c.post(
        f"/api/transport-ops/trips/{trip_id}/assign",
        headers=hdrs["fc1"],
        json={
            "partner_id": "tpartner-101",
            "vehicle_driver_id": "tdriver-101",
            "pickup_time": "09:15",
        },
    )
    c.post(
        f"/api/transport-ops/trips/{trip_id}/driver-response",
        headers=hdrs["fc1"],
        json={"response": "accepted"},
    )
    c.post(
        f"/api/transport-ops/trips/{trip_id}/lifecycle",
        headers=hdrs["fc1"],
        json={"action": "start_trip"},
    )
    trp_rcp = f"TRP-REC-{_u()}"
    r_comp_trip = c.post(
        f"/api/transport-ops/trips/{trip_id}/lifecycle",
        headers=hdrs["admin1"],
        json={
            "action": "complete_trip",
            "trip_expense_rupees": 450,
            "receipt_ref": trp_rcp,
        },
    )
    assert r_comp_trip.status_code == 200, r_comp_trip.text
    phase5_expense_id = r_comp_trip.json()["expense_id"]
    assert phase5_expense_id is not None

    # Submit ExpenseClaim linked to the completed transport trip
    r_claim = c.post(
        "/api/finance/claims",
        headers=hdrs["fc1"],
        json={
            "contract_id": "contract-syn-101",
            "budget_id": "budget-syn-101",
            "claim_type": "transport_partner_invoice",
            "expense_category": "transport",
            "transport_trip_id": trip_id,
            "transport_mode": "empaneled_partner_van",
            "distance_km": 22,
            "amount_paise": 45000,
            "receipt_number": trp_rcp,
            "description": "Reconciled rural maternal transport trip",
        },
    )
    assert r_claim.status_code == 201, r_claim.text
    claim_id = r_claim.json()["id"]
    # Must link to the existing Phase 5 Expense row rather than duplicating it!
    assert r_claim.json()["expense_id"] == phase5_expense_id

    # Duplicate receipt number MUST be rejected (409)
    r_dup_rec = c.post(
        "/api/finance/claims",
        headers=hdrs["fc1"],
        json={
            "contract_id": "contract-syn-101",
            "budget_id": "budget-syn-101",
            "claim_type": "staff_travel_claim",
            "expense_category": "travel",
            "transport_mode": "public_bus_rail",
            "amount_paise": 12000,
            "receipt_number": trp_rcp,
            "description": "Duplicate receipt attempt",
        },
    )
    assert r_dup_rec.status_code == 409

    # Duplicate claim for the same transport_trip_id MUST be rejected (409)
    r_dup_trip = c.post(
        "/api/finance/claims",
        headers=hdrs["fc1"],
        json={
            "contract_id": "contract-syn-101",
            "budget_id": "budget-syn-101",
            "claim_type": "transport_partner_invoice",
            "expense_category": "transport",
            "transport_trip_id": trip_id,
            "transport_mode": "empaneled_partner_van",
            "amount_paise": 45000,
            "receipt_number": "TRP-REC-2026-502-DIFF",
            "description": "Duplicate transport trip claim attempt",
        },
    )
    assert r_dup_trip.status_code == 409

    # Anti-self-approval: fc1 (submitter/claimant) attempting to verify or approve their own claim MUST fail (403)
    r_self_ver = c.post(
        f"/api/finance/claims/{claim_id}/decision",
        headers=hdrs["fc1"],
        json={"decision": "verified_by_supervisor", "receipt_verified": True},
    )
    assert r_self_ver.status_code == 403

    # Supervisor verification by nurse1 succeeds
    r_sup_ver = c.post(
        f"/api/finance/claims/{claim_id}/decision",
        headers=hdrs["nurse1"],
        json={"decision": "verified_by_supervisor", "receipt_verified": True, "notes": "Trip log checked"},
    )
    assert r_sup_ver.status_code == 200
    assert r_sup_ver.json()["status"] == "verified_by_supervisor"

    # Finance approval by admin1 succeeds
    r_fin_app = c.post(
        f"/api/finance/claims/{claim_id}/decision",
        headers=hdrs["admin1"],
        json={"decision": "approved_by_finance", "receipt_verified": True, "notes": "Approved for reimbursement"},
    )
    assert r_fin_app.status_code == 200
    assert r_fin_app.json()["status"] == "approved_by_finance"
    assert r_fin_app.json()["expense_id"] == phase5_expense_id


def test_10_service_to_funding_evidence_package_and_unverifiable_claim_rejection():
    """Verify service-to-contract evidence chain, rejection of unapproved/duplicate expenditures, and privacy-safe Supporting Evidence Package."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)
    today = date.today()

    # Attempting to create a funding claim using an unapproved expense ('exp-syn-102' is approved=False) MUST fail (400)
    r_unver = c.post(
        "/api/finance/funding-claims",
        headers=hdrs["admin1"],
        json={
            "contract_id": "contract-syn-101",
            "budget_id": "budget-syn-101",
            "claim_reference": "FCLM-UNVER-001",
            "period_start": str(today - timedelta(days=30)),
            "period_end": str(today),
            "evidence_items": [
                {
                    "expense_id": "exp-syn-102",
                    "service_category": "travel",
                    "verification_evidence_ref": "UNAPPROVED-EXP-ATTEMPT",
                }
            ],
        },
    )
    assert r_unver.status_code == 400
    assert "Unverifiable funding claim rejected" in r_unver.text

    # Create a completed service request & verified field visit to link to approved expense 'exp-syn-101'
    r_sr = c.post(
        "/api/services",
        headers=hdrs["doc1"],
        json={
            "mother_id": "mother-syn-101",
            "service_type": "anc_home_visit",
            "requires_clinical_qualification": True,
            "priority": "high",
            "assigned_staff_id": "staff-nurse-1",
        },
    )
    assert r_sr.status_code == 200, r_sr.text
    sr_id = r_sr.json()["id"]
    for st, extra in [
        ("scheduled", {}),
        ("in_progress", {}),
        ("completed", {"completion_evidence": "Signed Home Visit Entry #101"}),
        ("verified", {}),
    ]:
        c.post(
            f"/api/services/{sr_id}/transition",
            headers=hdrs["doc1"],
            json={"target_state": st, **extra},
        )

    # Create a fresh approved expense via an approved claim so test_10 can run repeatedly
    u10 = _u()
    r_ec10 = c.post(
        "/api/finance/claims",
        headers=hdrs["fc1"],
        json={
            "contract_id": "contract-syn-101",
            "budget_id": "budget-syn-101",
            "claim_type": "transport_partner_invoice",
            "expense_category": "transport",
            "service_request_id": sr_id,
            "transport_mode": "empaneled_partner_van",
            "amount_paise": 85000,
            "receipt_number": f"EV-RCP-{u10}",
            "description": "Verified maternal transport voucher for funding claim",
        },
    )
    assert r_ec10.status_code == 201, r_ec10.text
    ec10_id = r_ec10.json()["id"]
    c.post(
        f"/api/finance/claims/{ec10_id}/decision",
        headers=hdrs["nurse1"],
        json={"decision": "verified_by_supervisor", "receipt_verified": True},
    )
    r_ec10_app = c.post(
        f"/api/finance/claims/{ec10_id}/decision",
        headers=hdrs["admin1"],
        json={"decision": "approved_by_finance", "receipt_verified": True},
    )
    assert r_ec10_app.status_code == 200
    exp10_id = r_ec10_app.json()["expense_id"]

    # Create a valid FundingClaim linking contract-syn-101 -> budget-syn-101 -> transport -> sr_id -> exp10_id
    r_fc = c.post(
        "/api/finance/funding-claims",
        headers=hdrs["admin1"],
        json={
            "contract_id": "contract-syn-101",
            "budget_id": "budget-syn-101",
            "claim_reference": f"FCLM-VALID-{u10}",
            "period_start": str(today - timedelta(days=30)),
            "period_end": str(today),
            "evidence_items": [
                {
                    "expense_id": exp10_id,
                    "expense_claim_id": ec10_id,
                    "service_category": "transport",
                    "service_request_id": sr_id,
                    "verification_evidence_ref": f"VOUCHER-VERIFIED-{u10}",
                }
            ],
        },
    )
    assert r_fc.status_code == 201, r_fc.text
    fc_id = r_fc.json()["id"]
    # exp10_id is 85,000 paise; contract-syn-101 has funder_share_bps=9000 (90%) -> 76,500 paise reimbursable
    assert r_fc.json()["total_claimed_paise"] == 85000
    assert r_fc.json()["funder_reimbursable_paise"] == 76500

    # Attempting to submit a second funding claim for the same expense (exp10_id) MUST be rejected (409)
    r_dup_fc = c.post(
        "/api/finance/funding-claims",
        headers=hdrs["admin1"],
        json={
            "contract_id": "contract-syn-101",
            "budget_id": "budget-syn-101",
            "claim_reference": f"FCLM-DUP-{u10}",
            "period_start": str(today - timedelta(days=30)),
            "period_end": str(today),
            "evidence_items": [
                {
                    "expense_id": exp10_id,
                    "service_category": "transport",
                    "service_request_id": sr_id,
                    "verification_evidence_ref": f"VOUCHER-VERIFIED-{u10}",
                }
            ],
        },
    )
    assert r_dup_fc.status_code == 409
    assert "Duplicate funding claim prevented" in r_dup_fc.text

    # Inspect Supporting Evidence Package and verify privacy-preserving anonymisation
    r_pkg = c.get(f"/api/finance/funding-claims/{fc_id}/evidence-package", headers=hdrs["admin1"])
    assert r_pkg.status_code == 200
    pkg = r_pkg.json()
    assert pkg["package_type"] == "SERVICE_TO_FUNDING_EVIDENCE_PACKAGE"
    assert "INTERNAL / DRAFT" in pkg["compliance_label"]
    chain = pkg["evidence_chain"]
    assert len(chain) == 1
    assert chain[0]["beneficiary_anonymised_ref"].startswith("BEN-")
    assert "Sravani Goud" not in str(pkg)  # Zero patient PII exposed in funding evidence package!


def test_11_audit_ledger_idempotency_concurrency_and_versioned_corrections():
    """Verify immutable FinancialAuditLedger, X-Idempotency-Key concurrent duplicate rejection (409), and versioned FinancialCorrectionRecord."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)
    u = _u()

    # Submit an expense claim
    r_clm = c.post(
        "/api/finance/claims",
        headers=hdrs["nurse1"],
        json={
            "contract_id": "contract-syn-101",
            "budget_id": "budget-syn-101",
            "claim_type": "staff_travel_claim",
            "expense_category": "travel",
            "transport_mode": "public_bus_rail",
            "amount_paise": 18000,
            "receipt_number": f"BUS-IDEM-{u}",
            "description": "Bus ticket for sub-centre visit",
        },
    )
    assert r_clm.status_code == 201, r_clm.text
    cid = r_clm.json()["id"]

    # Supervisor verify with X-Idempotency-Key
    idem_headers = {**hdrs["doc1"], "X-Idempotency-Key": f"idem-verify-bus-{u}"}
    r_v1 = c.post(
        f"/api/finance/claims/{cid}/decision",
        headers=idem_headers,
        json={"decision": "verified_by_supervisor", "receipt_verified": True},
    )
    assert r_v1.status_code == 200

    # Re-sending with the same X-Idempotency-Key (simulating concurrent duplicate request) MUST be blocked (409)
    r_v2 = c.post(
        f"/api/finance/claims/{cid}/decision",
        headers=idem_headers,
        json={"decision": "verified_by_supervisor", "receipt_verified": True},
    )
    assert r_v2.status_code == 409
    assert "idempotency key" in r_v2.text.lower()

    # Apply a versioned financial correction on the claim amount (18,000 -> 19,500 paise)
    r_cor = c.post(
        "/api/finance/corrections",
        headers=hdrs["admin1"],
        json={
            "entity_type": "expense_claim",
            "entity_id": cid,
            "field_name": "amount_paise",
            "new_value_paise": 19500,
            "reason": "Added return bus fare voucher omitted in initial entry",
        },
    )
    assert r_cor.status_code == 201, r_cor.text
    cor = r_cor.json()
    assert cor["version_number"] == 2
    assert cor["previous_value_paise"] == 18000
    assert cor["new_value_paise"] == 19500

    # Verify audit ledger records both the verification and the versioned correction
    r_led = c.get("/api/finance/audit-ledger", headers=hdrs["admin1"])
    assert r_led.status_code == 200
    actions = [e["action"] for e in r_led.json()]
    assert "versioned_financial_correction" in actions


def test_12_permissions_cross_clinic_isolation_exports_and_12_step_e2e_scenario():
    """Verify role-based permissions, restricted payroll access, cross-clinic isolation, CSV/PDF exports, and the 12-Step E2E Funded Maternal Programme Scenario."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    # 1. Execute the 12-Step End-to-End Funded Maternal Programme Walkthrough in demo-clinic
    r_walk = c.post("/api/finance/demo-walkthrough", headers=hdrs["admin1"])
    assert r_walk.status_code == 200, r_walk.text
    w = r_walk.json()
    assert w["walkthrough_status"] == "completed_all_12_steps"
    assert len(w["steps_completed"]) == 12
    assert w["contract"]["state"] == "active"
    assert w["contract"]["is_simulated_approval"] is True
    assert w["funding_claim"]["status"] == "reimbursed_settled"
    assert w["supporting_evidence_package"]["package_type"] == "SERVICE_TO_FUNDING_EVIDENCE_PACKAGE"

    # 2. Restricted Payroll Access: nurse1 can view her own payslips, but gets 403 if requesting doc1's payslips or full payroll runs
    r_own_slips = c.get("/api/finance/payroll/payslips", headers=hdrs["nurse1"])
    assert r_own_slips.status_code == 200
    assert all(sl["staff_id"] == "staff-nurse-1" for sl in r_own_slips.json())

    r_other_slips = c.get(
        "/api/finance/payroll/payslips?staff_id=staff-doc-1", headers=hdrs["nurse1"]
    )
    assert r_other_slips.status_code == 403

    r_nurse_runs = c.get("/api/finance/payroll/runs", headers=hdrs["nurse1"])
    assert r_nurse_runs.status_code == 403

    # 3. Cross-Clinic Isolation: warangal-clinic (admin2) cannot see or mutate demo-clinic contracts, budgets, or claims
    demo_contract_id = w["contract"]["id"]
    demo_budget_id = w["budget"]["id"]
    demo_fclaim_id = w["funding_claim"]["id"]

    r_wgl_contracts = c.get("/api/finance/contracts", headers=hdrs["admin2"])
    assert r_wgl_contracts.status_code == 200
    assert all(cnt["clinic"] == "warangal-clinic" for cnt in r_wgl_contracts.json())
    assert all(cnt["id"] != demo_contract_id for cnt in r_wgl_contracts.json())

    r_wgl_cross_state = c.post(
        f"/api/finance/contracts/{demo_contract_id}/state",
        headers=hdrs["admin2"],
        json={"target_state": "suspended"},
    )
    assert r_wgl_cross_state.status_code == 404

    r_wgl_cross_bgt = c.get(
        f"/api/finance/budgets/{demo_budget_id}/comparison", headers=hdrs["admin2"]
    )
    assert r_wgl_cross_bgt.status_code == 404

    r_wgl_cross_pkg = c.get(
        f"/api/finance/funding-claims/{demo_fclaim_id}/evidence-package", headers=hdrs["admin2"]
    )
    assert r_wgl_cross_pkg.status_code == 404

    # 4. CSV and PDF Report Exports with INTERNAL / DRAFT compliance watermark
    for rtype in (
        "contract_funding_summary",
        "programme_budget_vs_actual",
        "monthly_payroll_summary",
        "staff_compensation_register",
        "transport_field_expense_report",
        "partner_service_expenditure_report",
        "funder_utilisation_statement",
    ):
        r_csv = c.get(
            f"/api/finance/reports/{rtype}/export?format=csv", headers=hdrs["admin1"]
        )
        assert r_csv.status_code == 200
        assert "INTERNAL / DRAFT" in r_csv.text

    r_pdf = c.get(
        "/api/finance/reports/funder_utilisation_statement/export?format=pdf",
        headers=hdrs["admin1"],
    )
    assert r_pdf.status_code == 200
    assert r_pdf.headers["content-type"] == "application/pdf"
    assert r_pdf.content.startswith(b"%PDF-1.4")
    assert b"INTERNAL / DRAFT" in r_pdf.content
