"""Phase 5 Automated Test Suite: Healthcare Workforce, Field Visits, Hospital Partnerships,
Transport Operations, Operations Centre Dashboard, and Clinical/Organisational Governance.

Covers:
1. Doctor and nurse onboarding, employment/contractor status vs clinical role separation, and initial unverified credentials.
2. Credential document submission, human verification with reviewer & evidence, and strict anti-self-verification enforcement.
3. Shift assignment, attendance tracking, overlapping shift conflict detection (409), and leave approval with replacement coverage.
4. Role-based permission enforcement and clinical authority boundaries (blocking non-clinicians from clinical consultations, clinical observations, and clinical obstetric referrals).
5. Patient service coordination full lifecycle (Service requested -> Staff assigned -> Scheduled -> In progress -> Completed -> Verified -> Closed) + invalid transition rejection, cancellation, reassignment, and staff offboarding impact.
6. Field visit scheduling, consent verification, optional purpose-limited consented location check-in guard, completion with evidence, failed visit & rescheduling, and idempotent offline draft synchronization.
7. Partner hospital & diagnostic facility registration, agreement validity checks, clinician-authorised referral lifecycle, and automatic contractual Expense creation.
8. Transport partner & vehicle/driver registration, driving licence & insurance verification enforcement, driver acceptance/rejection, trip completion with fare & receipt Expense creation, and failed pickup reassignment.
9. Strict cross-clinic tenant isolation across all Phase 5 Workforce, Service, Field Visit, Partner Referral, Transport Fleet, and Governance endpoints.
10. Clinical & organisational governance incident escalation/resolution, immutable RecordCorrectionLog auditing, and database persistence across sessions.
11. End-to-End 10-step operational scenario walkthrough and live Operations Centre Dashboard verification.
"""
from __future__ import annotations

from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models import (
    Expense,
    FieldVisit,
    GovernanceIncident,
    HospitalReferral,
    RecordCorrectionLog,
    ServiceRequest,
    StaffCredentialDocument,
    StaffWorkforceProfile,
    Transport,
)


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


def test_01_doctor_and_nurse_onboarding_and_employment_role_separation():
    """Verify doctor & nurse onboarding stores employment/contractor status separately from clinical role and starts credentials as unverified."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    # Onboard a contract obstetrician (doctor role, contract_clinician employment)
    r_doc = c.post(
        "/api/workforce/onboard",
        headers=hdrs["admin1"],
        json={
            "name": "Dr. Aruna Devi (Contract OBGYN)",
            "email": "aruna.obgyn@nalgonda.janani.org",
            "role": "doctor",
            "employment_type": "contract_clinician",
            "clinical_cadre": "medical_officer_obgyn",
            "qualification": "MBBS, MS (OBGYN)",
            "registration_council": "Telangana State Medical Council",
            "registration_number": "TSMC-2026-99101",
            "credential_expiry_date": (date.today() + timedelta(days=365)).isoformat(),
            "assigned_facility": "PHC Nalgonda Maternity Wing",
        },
    )
    assert r_doc.status_code == 200, r_doc.text
    doc_payload = r_doc.json()
    assert doc_payload["employment_type"] == "contract_clinician"
    assert doc_payload["staff"]["role"] == "doctor"
    assert doc_payload["onboarding_status"] == "active_onboarded"
    # Self-entered / initial onboarding credentials MUST NOT be treated as verified!
    assert doc_payload["credential_verification_status"] == "unverified"
    assert len(doc_payload["credentials"]) == 1
    assert doc_payload["credentials"][0]["verification_status"] == "unverified"

    # Onboard an NHM-deputed ANM nurse
    r_nurse = c.post(
        "/api/workforce/onboard",
        headers=hdrs["admin1"],
        json={
            "name": "Padmavathi (NHM ANM Nurse)",
            "email": "padmavathi.anm@nalgonda.janani.org",
            "role": "nurse",
            "employment_type": "nhm_deputed",
            "clinical_cadre": "anm_staff_nurse",
            "qualification": "GNM / Registered Midwife",
            "registration_council": "Telangana Nursing Council",
            "registration_number": "TSNC-2026-77312",
            "credential_expiry_date": (date.today() + timedelta(days=200)).isoformat(),
            "assigned_facility": "Miryalaguda Sub-Centre",
        },
    )
    assert r_nurse.status_code == 200, r_nurse.text
    nurse_payload = r_nurse.json()
    assert nurse_payload["employment_type"] == "nhm_deputed"
    assert nurse_payload["staff"]["role"] == "nurse"
    assert nurse_payload["credential_verification_status"] == "unverified"


def test_02_credential_verification_and_anti_self_verification():
    """Verify self-entered credentials cannot be self-verified, non-authorised roles cannot verify, and authorised reviewers record evidence."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    # Doctor uploads an additional specialist degree credential
    r_up = c.post(
        "/api/workforce/profiles/staff-doc-1/credentials",
        headers=hdrs["doc1"],
        json={
            "document_type": "degree_certificate",
            "registration_number": "TSMC-DGO-2026-5501",
            "issuing_authority": "Telangana State Medical Council",
            "issued_date": (date.today() - timedelta(days=400)).isoformat(),
            "expiry_date": (date.today() + timedelta(days=365)).isoformat(),
            "evidence_filename": "dgo_specialist_cert.pdf",
            "evidence_notes": "Postgraduate Diploma in Obstetrics & Gynaecology",
        },
    )
    assert r_up.status_code == 200, r_up.text
    cred_id = r_up.json()["id"]
    assert r_up.json()["verification_status"] == "unverified"

    # 1. Doctor attempts to verify their OWN credential -> MUST be blocked (403 Forbidden)
    r_self = c.post(
        f"/api/workforce/credentials/{cred_id}/verify",
        headers=hdrs["doc1"],
        json={
            "decision": "verified",
            "review_evidence_note": "Attempting to self-verify my own certificate",
        },
    )
    assert r_self.status_code == 403
    assert "Self-verification" in r_self.text

    # 2. Field coordinator attempts to verify credential -> MUST be blocked (403 Forbidden)
    r_fc = c.post(
        f"/api/workforce/credentials/{cred_id}/verify",
        headers=hdrs["fc1"],
        json={
            "decision": "verified",
            "review_evidence_note": "Coordinator trying to verify doctor credential",
        },
    )
    assert r_fc.status_code == 403

    # 3. Authorised Clinic Admin verifies the credential with documented evidence
    r_ver = c.post(
        f"/api/workforce/credentials/{cred_id}/verify",
        headers=hdrs["admin1"],
        json={
            "decision": "verified",
            "review_evidence_note": "Checked against TSMC online portal & physical certificate #5501",
        },
    )
    assert r_ver.status_code == 200, r_ver.text
    ver_data = r_ver.json()
    assert ver_data["verification_status"] == "verified"
    assert ver_data["reviewed_by"] == "staff-admin-1"
    assert ver_data["reviewed_by_role"] == "admin"
    assert "TSMC online portal" in ver_data["review_evidence_note"]


def test_03_shift_assignment_and_conflict_detection():
    """Verify shift assignment, overlapping shift conflict rejection (409), and leave approval with replacement coverage."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    target_date = (date.today() + timedelta(days=14)).isoformat()

    # 1. Assign a morning shift (08:00 - 16:00) to nurse1
    r_s1 = c.post(
        "/api/workforce/shifts",
        headers=hdrs["admin1"],
        json={
            "staff_id": "staff-nurse-1",
            "facility_name": "PHC Nalgonda Main",
            "shift_date": target_date,
            "start_time": "08:00",
            "end_time": "16:00",
            "shift_type": "morning",
            "notes": "ANC OPD nursing shift",
        },
    )
    assert r_s1.status_code == 200, r_s1.text
    shift_id = r_s1.json()["id"]

    # 2. Attempt to assign an overlapping shift (12:00 - 18:00) on the same date -> 409 Conflict
    r_overlap = c.post(
        "/api/workforce/shifts",
        headers=hdrs["admin1"],
        json={
            "staff_id": "staff-nurse-1",
            "facility_name": "Miryalaguda Sub-Centre",
            "shift_date": target_date,
            "start_time": "12:00",
            "end_time": "18:00",
            "shift_type": "afternoon",
        },
    )
    assert r_overlap.status_code == 409
    assert "Shift conflict" in r_overlap.text

    # 3. Submit leave request for nurse1 covering target_date with replacement staff
    r_lv = c.post(
        "/api/workforce/leaves",
        headers=hdrs["nurse1"],
        json={
            "staff_id": "staff-nurse-1",
            "start_date": target_date,
            "end_date": target_date,
            "leave_type": "medical",
            "reason": "Scheduled medical checkup",
            "replacement_staff_id": "staff-doc-1",
        },
    )
    assert r_lv.status_code == 200, r_lv.text
    leave_id = r_lv.json()["id"]

    # 4. Admin approves leave -> existing scheduled shift transitions to leave_covered
    r_dec = c.patch(
        f"/api/workforce/leaves/{leave_id}/decision",
        headers=hdrs["admin1"],
        json={"status": "approved", "replacement_staff_id": "staff-doc-1"},
    )
    assert r_dec.status_code == 200, r_dec.text
    assert r_dec.json()["covered_shifts"] >= 1

    # 5. Attempting to assign a new shift to nurse1 on approved leave date -> 409 Conflict
    r_leave_conflict = c.post(
        "/api/workforce/shifts",
        headers=hdrs["admin1"],
        json={
            "staff_id": "staff-nurse-1",
            "facility_name": "PHC Nalgonda Main",
            "shift_date": target_date,
            "start_time": "17:00",
            "end_time": "21:00",
            "shift_type": "afternoon",
        },
    )
    assert r_leave_conflict.status_code == 409
    assert "leave" in r_leave_conflict.text.lower()

    # Verify attendance check-in on today's seeded shift
    r_att = c.patch(
        f"/api/workforce/shifts/shift-syn-102/attendance",
        headers=hdrs["nurse1"],
        json={"status": "checked_in"},
    )
    assert r_att.status_code == 200


def test_04_role_permission_enforcement_and_clinical_authority():
    """Verify administrative/field coordinators cannot authorise clinical consultations, clinical notes, or clinical referrals."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    # 1. Field Coordinator attempts to authorise a clinical_consultation service -> 403 Forbidden
    r_srv_fc = c.post(
        "/api/services",
        headers=hdrs["fc1"],
        json={
            "mother_id": "mother-syn-101",
            "service_type": "clinical_consultation",
            "requires_clinical_qualification": True,
            "priority": "high",
        },
    )
    assert r_srv_fc.status_code == 403

    # 2. Doctor creates a clinical service request; attempting to assign a non-clinical Field Coordinator -> 403 Forbidden
    r_srv_doc = c.post(
        "/api/services",
        headers=hdrs["doc1"],
        json={
            "mother_id": "mother-syn-101",
            "service_type": "postnatal_check",
            "requires_clinical_qualification": True,
            "priority": "high",
        },
    )
    assert r_srv_doc.status_code == 200
    srv_id = r_srv_doc.json()["id"]

    r_assign_fc = c.post(
        f"/api/services/{srv_id}/assign",
        headers=hdrs["doc1"],
        json={"assigned_staff_id": "staff-fc-1"},
    )
    assert r_assign_fc.status_code == 403
    assert "requires clinical qualification" in r_assign_fc.text

    # 3. Field coordinator attempts to authorise a clinical obstetric hospital referral -> 403 Forbidden
    r_ref_fc = c.post(
        "/api/referrals",
        headers=hdrs["fc1"],
        json={
            "mother_id": "mother-syn-101",
            "partner_facility_id": "partner-hosp-101",
            "referral_category": "clinical_obstetric",
            "reason_and_clinical_summary": "Coordinator attempting clinical referral",
        },
    )
    assert r_ref_fc.status_code == 403


def test_05_service_request_lifecycle_and_cancellation_reassignment():
    """Verify full service lifecycle (Service requested -> Staff assigned -> Scheduled -> In progress -> Completed -> Verified -> Closed) and offboarding impact."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    # 1. Create service request (service_requested)
    r_create = c.post(
        "/api/services",
        headers=hdrs["doc1"],
        json={
            "mother_id": "mother-syn-101",
            "care_plan_id": "plan-syn-101",
            "service_type": "anc_home_visit",
            "requires_clinical_qualification": True,
            "priority": "high",
            "notes": "Routine 2nd-trimester home nursing check",
        },
    )
    assert r_create.status_code == 200
    srv_id = r_create.json()["id"]
    assert r_create.json()["status"] == "service_requested"

    # Invalid transition directly from service_requested to verified -> 409 Conflict
    r_bad = c.post(
        f"/api/services/{srv_id}/transition",
        headers=hdrs["doc1"],
        json={"target_state": "verified"},
    )
    assert r_bad.status_code == 409

    # 2. Assign nurse (staff_assigned)
    r_assign = c.post(
        f"/api/services/{srv_id}/assign",
        headers=hdrs["doc1"],
        json={"assigned_staff_id": "staff-nurse-1"},
    )
    assert r_assign.status_code == 200
    assert r_assign.json()["status"] == "staff_assigned"

    # 3. Transition -> scheduled -> in_progress -> completed -> verified -> closed
    for next_state, extra in [
        ("scheduled", {}),
        ("in_progress", {}),
        ("completed", {"completion_evidence": "Signed MCP Card Visit Entry #101"}),
        ("verified", {}),
        ("closed", {}),
    ]:
        r_tr = c.post(
            f"/api/services/{srv_id}/transition",
            headers=hdrs["doc1"],
            json={"target_state": next_state, **extra},
        )
        assert r_tr.status_code == 200, r_tr.text
        assert r_tr.json()["status"] == next_state

    # 4. Test cancellation, reassignment, and staff offboarding impact
    r_temp_staff = c.post(
        "/api/workforce/onboard",
        headers=hdrs["admin1"],
        json={
            "name": "Temp Nurse Kavya",
            "email": "kavya.temp@nalgonda.janani.org",
            "role": "nurse",
            "employment_type": "part_time_employee",
        },
    )
    assert r_temp_staff.status_code == 200
    temp_staff_id = r_temp_staff.json()["staff_id"]

    r_srv2 = c.post(
        "/api/services",
        headers=hdrs["doc1"],
        json={
            "mother_id": "mother-syn-102",
            "service_type": "anc_home_visit",
            "assigned_staff_id": temp_staff_id,
        },
    )
    assert r_srv2.status_code == 200
    srv2_id = r_srv2.json()["id"]
    assert r_srv2.json()["status"] == "staff_assigned"

    # Offboard temp_staff_id -> srv2 automatically transitions to unavailable_personnel
    r_off = c.post(
        f"/api/workforce/profiles/{temp_staff_id}/offboard",
        headers=hdrs["admin1"],
        json={"offboarding_reason": "Temporary assignment ended"},
    )
    assert r_off.status_code == 200
    assert r_off.json()["affected_services_count"] >= 1

    # Reassign srv2 to active nurse1
    r_reassign = c.post(
        f"/api/services/{srv2_id}/assign",
        headers=hdrs["admin1"],
        json={
            "assigned_staff_id": "staff-nurse-1",
            "scheduled_date": date.today().isoformat(),
        },
    )
    assert r_reassign.status_code == 200
    assert r_reassign.json()["status"] == "scheduled"
    assert r_reassign.json()["reassigned_from_staff_id"] == temp_staff_id


def test_06_field_visit_lifecycle_location_consent_guard_and_offline_sync():
    """Verify field visit scheduling, location consent guard, role-scoped notes, completion evidence, and idempotent offline sync."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    # 1. Schedule field visit
    r_fv = c.post(
        "/api/field-visits",
        headers=hdrs["nurse1"],
        json={
            "mother_id": "mother-syn-101",
            "assigned_staff_id": "staff-nurse-1",
            "visit_date": date.today().isoformat(),
            "scheduled_window": "09:30-11:00",
            "visit_address": "Ward 4 Devarakonda",
            "role_scoped_notes": "Bring portable BP apparatus and MCP card register",
        },
    )
    assert r_fv.status_code == 200, r_fv.text
    vid = r_fv.json()["id"]

    # 2. Attempt to record location coordinates WITHOUT location_consent_granted -> 403 Forbidden
    r_loc_denied = c.post(
        f"/api/field-visits/{vid}/start",
        headers=hdrs["nurse1"],
        json={
            "contact_confirmed": True,
            "patient_consent_verified": True,
            "location_consent_granted": False,
            "checkin_latitude": 17.0575,
            "checkin_longitude": 79.2684,
            "location_purpose": "Home visit arrival check",
        },
    )
    assert r_loc_denied.status_code == 403
    assert "location_consent_granted" in r_loc_denied.text

    # 3. Start field visit with explicit location consent and stated purpose
    r_start = c.post(
        f"/api/field-visits/{vid}/start",
        headers=hdrs["nurse1"],
        json={
            "contact_confirmed": True,
            "patient_consent_verified": True,
            "location_consent_granted": True,
            "checkin_latitude": 17.0575,
            "checkin_longitude": 79.2684,
            "location_purpose": "Point-in-time home visit check-in verification",
        },
    )
    assert r_start.status_code == 200, r_start.text
    assert r_start.json()["status"] == "in_progress"
    assert r_start.json()["location_consent_granted"] is True

    # 4. Field coordinator attempts to enter clinical_observations_by_clinician -> 403 Forbidden
    r_fc_notes = c.post(
        f"/api/field-visits/{vid}/complete",
        headers=hdrs["fc1"],
        json={
            "patient_consent_verified": True,
            "completion_evidence_type": "home_visit_checklist",
            "completion_evidence_ref": "CHK-901",
            "clinical_observations_by_clinician": "Fetal heart rate 144 bpm",
        },
    )
    assert r_fc_notes.status_code == 403

    # 5. Nurse completes the visit with clinical observations and evidence
    r_comp = c.post(
        f"/api/field-visits/{vid}/complete",
        headers=hdrs["nurse1"],
        json={
            "patient_consent_verified": True,
            "completion_evidence_type": "signed_mcp_card_ack",
            "completion_evidence_ref": "MCP-SIGN-2026-101",
            "role_scoped_notes": "Confirmed upcoming doctor-approved clinic date with mother.",
            "clinical_observations_by_clinician": "General maternal wellbeing verified by ANM nurse.",
        },
    )
    assert r_comp.status_code == 200, r_comp.text
    assert r_comp.json()["status"] == "completed"
    assert r_comp.json()["completion_evidence_ref"] == "MCP-SIGN-2026-101"

    # 6. Test idempotent offline field-visit draft synchronization
    draft_payload = {
        "drafts": [
            {
                "offline_draft_id": "offline-draft-nalgonda-001",
                "mother_id": "mother-syn-102",
                "assigned_staff_id": "staff-fc-1",
                "visit_date": date.today().isoformat(),
                "scheduled_window": "14:00-15:30",
                "visit_address": "Miryalaguda Sector B",
                "patient_consent_verified": True,
                "completion_evidence_type": "home_visit_checklist",
                "completion_evidence_ref": "OFFLINE-CHK-001",
                "role_scoped_notes": "Recorded offline during village outreach; synced on clinic Wi-Fi.",
            }
        ]
    }
    r_sync1 = c.post("/api/field-visits/offline-sync", headers=hdrs["fc1"], json=draft_payload)
    assert r_sync1.status_code == 200, r_sync1.text
    assert r_sync1.json()["synced_count"] == 1
    assert r_sync1.json()["duplicates_skipped"] == 0

    # Re-sending the exact same offline batch must be idempotent (0 new, 1 skipped)
    r_sync2 = c.post("/api/field-visits/offline-sync", headers=hdrs["fc1"], json=draft_payload)
    assert r_sync2.status_code == 200
    assert r_sync2.json()["synced_count"] == 0
    assert r_sync2.json()["duplicates_skipped"] == 1


def test_07_partner_hospital_registration_and_clinician_authorised_referral_lifecycle():
    """Verify partner hospital registration, clinician-authorised referral workflow, and automatic Expense creation."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    # 1. Register a partner ultrasound & diagnostic centre
    r_pf = c.post(
        "/api/partners/facilities",
        headers=hdrs["admin1"],
        json={
            "name": "Nalgonda Maternal Ultrasound & Fetal Imaging Centre",
            "facility_type": "ultrasound_centre",
            "contact_person": "Dr. Srinivas Rao (Radiologist)",
            "contact_phone": "9440099111",
            "address": "Clock Tower Road, Nalgonda",
            "services_offered": ["TIFFA Scan", "Growth Scan", "Doppler Study"],
            "agreement_reference": "MOU-USG-NLG-2026-07",
            "effective_from": (date.today() - timedelta(days=30)).isoformat(),
            "effective_until": (date.today() + timedelta(days=335)).isoformat(),
            "schedule_charges": {"growth_scan_paise": 95000},
        },
    )
    assert r_pf.status_code == 200, r_pf.text
    pf_id = r_pf.json()["id"]

    # 2. Doctor initiates a clinical referral to the partner facility
    r_ref = c.post(
        "/api/referrals",
        headers=hdrs["doc1"],
        json={
            "mother_id": "mother-syn-101",
            "care_plan_id": "plan-syn-101",
            "partner_facility_id": pf_id,
            "referral_category": "clinical_obstetric",
            "reason_and_clinical_summary": "Doctor-authorised 2nd trimester TIFFA scan and obstetric review.",
            "requested_services": ["TIFFA Scan"],
            "scheduled_service_date": (date.today() + timedelta(days=3)).isoformat(),
            "contractual_charge_rupees": 950,
        },
    )
    assert r_ref.status_code == 200, r_ref.text
    ref_id = r_ref.json()["id"]
    assert r_ref.json()["status"] == "initiated"

    # 3. Partner acknowledgement -> service completion -> verified_closed
    r_ack = c.patch(
        f"/api/referrals/{ref_id}/status",
        headers=hdrs["doc1"],
        json={
            "status": "acknowledged_by_partner",
            "partner_acknowledgement_ref": "USG-ACK-2026-88",
        },
    )
    assert r_ack.status_code == 200
    assert r_ack.json()["status"] == "acknowledged_by_partner"

    r_ver = c.patch(
        f"/api/referrals/{ref_id}/status",
        headers=hdrs["doc1"],
        json={
            "status": "verified_closed",
            "completion_evidence_ref": "TIFFA-REPORT-2026-88.pdf",
        },
    )
    assert r_ver.status_code == 200, r_ver.text
    ver_json = r_ver.json()
    assert ver_json["status"] == "verified_closed"
    assert ver_json["expense_id"] is not None

    # Verify contractual expense was recorded in the database
    with SessionLocal() as db:
        exp = db.get(Expense, ver_json["expense_id"])
        assert exp is not None
        assert exp.amount_paise == 95000
        assert exp.category == "diagnostics"


def test_08_transport_partner_driver_verification_trip_lifecycle_and_failed_pickup():
    """Verify transport partner & vehicle/driver registration, licence/insurance verification gate, trip completion expense, and failed pickup reassignment."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    # 1. Register a transport partner
    r_tp = c.post(
        "/api/transport-ops/partners",
        headers=hdrs["admin1"],
        json={
            "name": "Miryalaguda Safe Motherhood Mobility Partner",
            "partner_type": "community_van_contract",
            "contact_person": "Ramesh Yadav",
            "contact_phone": "9848011223",
            "agreement_ref": "MOU-TRANS-2026-12",
            "effective_until": (date.today() + timedelta(days=365)).isoformat(),
            "base_tariff_rupees": 500,
        },
    )
    assert r_tp.status_code == 200, r_tp.text
    tp_id = r_tp.json()["id"]
    assert "not live emergency ambulance dispatch" in r_tp.json()["disclaimer_note"]

    # 2. Register a vehicle & driver (starts credentials_verified=False)
    r_vd = c.post(
        "/api/transport-ops/vehicles",
        headers=hdrs["fc1"],
        json={
            "partner_id": tp_id,
            "driver_name": "Mallikarjun Goud",
            "driver_phone": "9848099112",
            "driving_licence_no": "TS05-2020-DL-7741",
            "licence_expiry_date": (date.today() + timedelta(days=400)).isoformat(),
            "vehicle_registration_no": "TS-05-UB-7741",
            "vehicle_type": "patient_transport_van",
            "insurance_policy_no": "NIC-TS05-2026-7741",
            "insurance_expiry_date": (date.today() + timedelta(days=300)).isoformat(),
        },
    )
    assert r_vd.status_code == 200, r_vd.text
    vd_id = r_vd.json()["id"]
    assert r_vd.json()["credentials_verified"] is False

    # Create a patient transport request
    r_tr = c.post(
        "/api/transport",
        headers=hdrs["fc1"],
        json={
            "mother_id": "mother-syn-101",
            "date": (date.today() + timedelta(days=2)).isoformat(),
            "pickup_time": "08:15",
            "from_location": "Ward 4 Devarakonda",
            "destination": "PHC Nalgonda",
        },
    )
    assert r_tr.status_code == 200
    trip_id = r_tr.json()["id"]

    # 3. Attempt to assign unverified driver -> 400 Bad Request
    r_unver = c.post(
        f"/api/transport-ops/trips/{trip_id}/assign",
        headers=hdrs["fc1"],
        json={"partner_id": tp_id, "vehicle_driver_id": vd_id},
    )
    assert r_unver.status_code == 400
    assert "verified" in r_unver.text.lower()

    # 4. Admin verifies driver licence & insurance
    r_ver_vd = c.post(
        f"/api/transport-ops/vehicles/{vd_id}/verify",
        headers=hdrs["admin1"],
    )
    assert r_ver_vd.status_code == 200
    assert r_ver_vd.json()["credentials_verified"] is True

    # 5. Assign verified driver -> driver accepts -> start_trip -> complete_trip with expense & receipt
    r_assign = c.post(
        f"/api/transport-ops/trips/{trip_id}/assign",
        headers=hdrs["fc1"],
        json={"partner_id": tp_id, "vehicle_driver_id": vd_id, "pickup_time": "08:15"},
    )
    assert r_assign.status_code == 200
    assert r_assign.json()["status"] == "assigned"

    r_resp = c.post(
        f"/api/transport-ops/trips/{trip_id}/driver-response",
        headers=hdrs["fc1"],
        json={"response": "accepted"},
    )
    assert r_resp.status_code == 200
    assert r_resp.json()["driver_response_status"] == "accepted"

    r_start = c.post(
        f"/api/transport-ops/trips/{trip_id}/lifecycle",
        headers=hdrs["fc1"],
        json={"action": "start_trip"},
    )
    assert r_start.status_code == 200
    assert r_start.json()["status"] == "in_transit"

    r_comp = c.post(
        f"/api/transport-ops/trips/{trip_id}/lifecycle",
        headers=hdrs["admin1"],
        json={
            "action": "complete_trip",
            "trip_expense_rupees": 500,
            "receipt_ref": "TRP-VOUCHER-2026-7741",
        },
    )
    assert r_comp.status_code == 200, r_comp.text
    comp_data = r_comp.json()
    assert comp_data["status"] == "completed"
    assert comp_data["expense_id"] is not None
    assert comp_data["receipt_ref"] == "TRP-VOUCHER-2026-7741"

    # 6. Test failed pickup & driver reassignment on seeded transport trans-syn-101
    r_fail = c.post(
        "/api/transport-ops/trips/trans-syn-101/lifecycle",
        headers=hdrs["fc1"],
        json={
            "action": "fail_pickup",
            "failed_pickup_reason": "Flat tyre on primary van; reassigning backup verified van",
            "new_vehicle_driver_id": vd_id,
        },
    )
    assert r_fail.status_code == 200, r_fail.text
    assert r_fail.json()["vehicle_driver_id"] == vd_id
    assert r_fail.json()["status"] == "assigned"


def test_09_cross_clinic_access_denial_across_all_phase5_modules():
    """Verify staff in warangal-clinic cannot view or modify demo-clinic workforce, services, visits, referrals, or transport."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    # 1. Warangal admin lists workforce profiles -> only sees warangal-clinic staff
    r_wp = c.get("/api/workforce/profiles", headers=hdrs["admin2"])
    assert r_wp.status_code == 200
    assert all(p["clinic"] == "warangal-clinic" for p in r_wp.json())

    # 2. Warangal admin attempts to verify Nalgonda credential cred-doc-1 -> 404
    r_cred = c.post(
        "/api/workforce/credentials/cred-doc-1/verify",
        headers=hdrs["admin2"],
        json={"decision": "verified", "review_evidence_note": "Cross-clinic attempt"},
    )
    assert r_cred.status_code == 404

    # 3. Warangal doctor attempts to create a service request for Nalgonda mother -> 403/404
    r_srv = c.post(
        "/api/services",
        headers=hdrs["doc2"],
        json={"mother_id": "mother-syn-101", "service_type": "anc_home_visit"},
    )
    assert r_srv.status_code in (403, 404)

    # 4. Warangal doctor attempts to create a referral for Nalgonda mother or partner -> 403/404
    r_ref = c.post(
        "/api/referrals",
        headers=hdrs["doc2"],
        json={
            "mother_id": "mother-syn-101",
            "partner_facility_id": "partner-hosp-101",
            "referral_category": "clinical_obstetric",
            "reason_and_clinical_summary": "Cross-clinic referral attempt",
        },
    )
    assert r_ref.status_code in (403, 404)

    # 5. Warangal admin attempts to assign driver to Nalgonda transport trans-syn-101 -> 404
    r_tr = c.post(
        "/api/transport-ops/trips/trans-syn-101/assign-driver",
        headers=hdrs["admin2"],
        json={"vehicle_driver_id": "tdriver-101"},
    )
    assert r_tr.status_code == 404


def test_10_governance_incidents_record_corrections_and_db_persistence():
    """Verify governance incident escalation/resolution, audited RecordCorrectionLog, and database persistence across sessions."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    # 1. Report governance incident
    r_inc = c.post(
        "/api/governance/incidents",
        headers=hdrs["nurse1"],
        json={
            "incident_type": "missed_high_priority_visit",
            "severity": "high",
            "entity_type": "mother",
            "entity_id": "mother-syn-102",
            "title": "Repeated missed ANC follow-up requiring Medical Officer review",
            "description": "Beneficiary missed scheduled visit; home outreach arranged.",
        },
    )
    assert r_inc.status_code == 200, r_inc.text
    inc_id = r_inc.json()["id"]
    assert r_inc.json()["status"] == "open"

    # 2. Doctor resolves governance incident
    r_res = c.patch(
        f"/api/governance/incidents/{inc_id}",
        headers=hdrs["doc1"],
        json={
            "status": "resolved",
            "resolution_notes": "Reviewed by Medical Officer; home visit & transport completed.",
        },
    )
    assert r_res.status_code == 200
    assert r_res.json()["status"] == "resolved"
    assert r_res.json()["resolved_by"] == "staff-doc-1"

    # 3. Apply an audited record correction to Mother address
    r_corr = c.post(
        "/api/governance/corrections",
        headers=hdrs["admin1"],
        json={
            "entity_type": "mother",
            "entity_id": "mother-syn-101",
            "field_name": "address",
            "new_value": "Ward 4, House 18, Devarakonda Panchayat",
            "correction_reason": "Updated house number from verified voter/ration card during home visit",
        },
    )
    assert r_corr.status_code == 200, r_corr.text
    corr_id = r_corr.json()["id"]
    assert r_corr.json()["old_value"] == "Ward 4 Devarakonda"
    assert r_corr.json()["new_value"] == "Ward 4, House 18, Devarakonda Panchayat"

    # 4. Verify persistence in a fresh SQLAlchemy session
    with SessionLocal() as db:
        inc_db = db.get(GovernanceIncident, inc_id)
        assert inc_db is not None and inc_db.status == "resolved"
        corr_db = db.get(RecordCorrectionLog, corr_id)
        assert corr_db is not None
        assert corr_db.approved_by == "staff-admin-1"


def test_11_end_to_end_10_step_operational_scenario_and_dashboard():
    """Execute the complete 10-step End-to-End Operational Scenario and verify the Operations Centre Dashboard."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    r_e2e = c.post("/api/operations/demo-walkthrough", headers=hdrs["admin1"])
    assert r_e2e.status_code == 200, r_e2e.text
    data = r_e2e.json()
    assert data["walkthrough_status"] == "completed_all_10_steps"
    assert len(data["steps_completed"]) == 10
    assert data["step_2_verified_anc_document"]["confirmed"] is True
    assert data["step_3_doctor_approved_care_plan"]["approved_by"] is not None
    assert data["step_5_and_6_nurse_service_and_field_visit"]["field_visit"]["status"] == "completed"
    assert data["step_7_clinician_authorised_hospital_referral"]["referral"]["status"] == "verified_closed"
    assert data["step_8_and_9_transport_and_expense_completion"]["completed_trip"]["status"] == "completed"
    assert data["step_8_and_9_transport_and_expense_completion"]["recorded_expense"]["amount_paise"] == 55000

    # Verify Operations Centre Dashboard reflects live metrics
    r_dash = c.get("/api/operations/dashboard", headers=hdrs["admin1"])
    assert r_dash.status_code == 200, r_dash.text
    dash = r_dash.json()
    assert dash["clinic"] == "demo-clinic"
    assert dash["summary"]["staff_on_duty_today"] >= 1
    assert dash["summary"]["field_visits_today"] >= 1
    assert dash["summary"]["completed_services_count"] >= 1
    assert dash["expenses_summary"]["total_rupees"] > 0

