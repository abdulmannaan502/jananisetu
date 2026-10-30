"""Phase 5 FastAPI Routes: Healthcare Workforce, Patient Service Coordination, Field Visits,
Hospital & Diagnostic Partnerships, Transport Operations, Operations Centre Dashboard & Governance.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from typing import Any, Callable, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.anc_fixtures import generate_fixture_image_bytes
from app.followup_engine import (
    process_outbox_and_due_jobs,
    schedule_reminders_for_care_plan,
)
from app.models import (
    CarePlan,
    Document,
    Event,
    Expense,
    ExtractedField,
    FieldVisit,
    GovernanceIncident,
    HospitalReferral,
    Mother,
    PartnerFacility,
    RecordCorrectionLog,
    ServiceRequest,
    Staff,
    StaffCredentialDocument,
    StaffLeaveRequest,
    StaffShift,
    StaffWorkforceProfile,
    Transport,
    TransportPartner,
    TransportVehicleDriver,
    now,
)
from app.security import hash_password, normalize_role, validate_password_strength

# ---------------------------------------------------------------------------
# Operational Service Coordination State Machine
# Service requested -> Staff assigned -> Scheduled -> In progress -> Completed -> Verified -> Closed
# ---------------------------------------------------------------------------
SERVICE_STATES = (
    "service_requested",
    "staff_assigned",
    "scheduled",
    "in_progress",
    "completed",
    "verified",
    "closed",
    # Alternative operational states
    "cancelled",
    "no_show",
    "reassignment_required",
    "unavailable_personnel",
    "failed_visit",
)

ALLOWED_SERVICE_TRANSITIONS: dict[str, set[str]] = {
    "service_requested": {
        "staff_assigned",
        "scheduled",
        "unavailable_personnel",
        "cancelled",
    },
    "staff_assigned": {
        "scheduled",
        "in_progress",
        "reassignment_required",
        "unavailable_personnel",
        "cancelled",
    },
    "scheduled": {
        "in_progress",
        "no_show",
        "failed_visit",
        "reassignment_required",
        "unavailable_personnel",
        "cancelled",
    },
    "in_progress": {
        "completed",
        "failed_visit",
        "reassignment_required",
        "cancelled",
    },
    "completed": {
        "verified",
        "closed",
    },
    "verified": {
        "closed",
    },
    "no_show": {
        "scheduled",
        "reassignment_required",
        "closed",
        "cancelled",
    },
    "failed_visit": {
        "scheduled",
        "reassignment_required",
        "closed",
        "cancelled",
    },
    "reassignment_required": {
        "staff_assigned",
        "scheduled",
        "unavailable_personnel",
        "cancelled",
    },
    "unavailable_personnel": {
        "staff_assigned",
        "reassignment_required",
        "cancelled",
    },
    "cancelled": set(),
    "closed": set(),
}


# ---------------------------------------------------------------------------
# Pydantic Request Schemas for Phase 5
# ---------------------------------------------------------------------------
class WorkforceOnboardIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=160)
    password: str = Field(default="Janani@2026", min_length=8, max_length=128)
    phone: str = Field(default="", max_length=24)
    role: Literal["admin", "doctor", "nurse", "field_coordinator", "asha"]
    employment_type: Literal[
        "full_time_employee",
        "part_time_employee",
        "contract_clinician",
        "nhm_deputed",
        "community_honorarium",
    ] = "full_time_employee"
    clinical_cadre: str = Field(default="general", max_length=60)
    qualification: str = Field(default="", max_length=160)
    registration_council: str = Field(default="", max_length=140)
    registration_number: str = Field(default="", max_length=80)
    credential_expiry_date: Optional[date] = None
    assigned_facility: str = Field(default="PHC Main Facility", max_length=160)
    availability_days: list[str] = Field(
        default_factory=lambda: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    )
    shift_preference: Literal["morning", "afternoon", "night", "field_outreach"] = "morning"


class WorkforceProfileUpdateIn(BaseModel):
    employment_type: Optional[
        Literal[
            "full_time_employee",
            "part_time_employee",
            "contract_clinician",
            "nhm_deputed",
            "community_honorarium",
        ]
    ] = None
    onboarding_status: Optional[
        Literal[
            "pending_onboarding",
            "active_onboarded",
            "on_leave",
            "suspended",
            "offboarded",
        ]
    ] = None
    qualification: Optional[str] = Field(default=None, max_length=160)
    registration_council: Optional[str] = Field(default=None, max_length=140)
    registration_number: Optional[str] = Field(default=None, max_length=80)
    credential_expiry_date: Optional[date] = None
    assigned_facility: Optional[str] = Field(default=None, max_length=160)
    availability_days: Optional[list[str]] = None
    shift_preference: Optional[Literal["morning", "afternoon", "night", "field_outreach"]] = None


class OffboardStaffIn(BaseModel):
    offboarding_reason: str = Field(default="", max_length=500)
    reason: str = Field(default="", max_length=500)


class CredentialDocIn(BaseModel):
    document_type: Literal[
        "medical_council_registration",
        "nursing_license",
        "degree_certificate",
        "id_proof",
    ] = "medical_council_registration"
    registration_number: str = Field(min_length=3, max_length=80)
    issuing_authority: str = Field(min_length=2, max_length=160)
    issued_date: Optional[date] = None
    expiry_date: Optional[date] = None
    evidence_filename: str = Field(default="credential_certificate.pdf", max_length=200)
    evidence_notes: str = Field(default="", max_length=1000)


class CredentialVerifyIn(BaseModel):
    decision: Literal["verified", "rejected"]
    review_evidence_note: str = Field(min_length=4, max_length=1000)


class ShiftAssignIn(BaseModel):
    staff_id: str
    facility_name: str = Field(default="PHC Main Facility", max_length=160)
    shift_date: date
    start_time: str = Field(default="08:00", pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(default="16:00", pattern=r"^\d{2}:\d{2}$")
    shift_type: Literal["morning", "afternoon", "night", "field_outreach"] = "morning"
    notes: str = Field(default="", max_length=500)


class ShiftAttendanceIn(BaseModel):
    status: Literal[
        "scheduled",
        "checked_in",
        "completed",
        "absent",
        "leave_covered",
        "cancelled",
    ]
    replacement_staff_id: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=500)


class LeaveRequestIn(BaseModel):
    staff_id: str
    start_date: date
    end_date: date
    leave_type: Literal["casual", "medical", "maternity", "training"] = "casual"
    reason: str = Field(default="", max_length=500)
    replacement_staff_id: Optional[str] = None


class LeaveDecisionIn(BaseModel):
    status: Literal["approved", "rejected", "cancelled"]
    replacement_staff_id: Optional[str] = None


class ServiceRequestIn(BaseModel):
    mother_id: str
    care_plan_id: Optional[str] = None
    service_type: Literal[
        "anc_home_visit",
        "postnatal_check",
        "nutrition_counselling",
        "lab_sample_collection",
        "clinical_consultation",
        "transport_escort",
    ] = "anc_home_visit"
    requires_clinical_qualification: bool = True
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    assigned_staff_id: Optional[str] = None
    scheduled_date: Optional[date] = None
    scheduled_time: str = Field(default="10:00", max_length=20)
    notes: str = Field(default="", max_length=1000)


class ServiceAssignIn(BaseModel):
    assigned_staff_id: str
    scheduled_date: Optional[date] = None
    scheduled_time: Optional[str] = Field(default=None, max_length=20)


class ServiceTransitionIn(BaseModel):
    target_state: Optional[
        Literal[
            "service_requested",
            "staff_assigned",
            "scheduled",
            "in_progress",
            "completed",
            "verified",
            "closed",
            "cancelled",
            "no_show",
            "reassignment_required",
            "unavailable_personnel",
            "failed_visit",
        ]
    ] = None
    status: Optional[
        Literal[
            "service_requested",
            "staff_assigned",
            "scheduled",
            "in_progress",
            "completed",
            "verified",
            "closed",
            "cancelled",
            "no_show",
            "reassignment_required",
            "unavailable_personnel",
            "failed_visit",
        ]
    ] = None
    reassigned_staff_id: Optional[str] = None
    cancellation_reason: str = Field(default="", max_length=255)
    failure_reason: str = Field(default="", max_length=255)
    completion_evidence: str = Field(default="", max_length=1000)
    notes: str = Field(default="", max_length=1000)


class FieldVisitCreateIn(BaseModel):
    mother_id: str
    service_request_id: Optional[str] = None
    care_plan_id: Optional[str] = None
    assigned_staff_id: str
    visit_date: date
    scheduled_window: str = Field(default="09:00-11:00", max_length=40)
    visit_address: str = Field(default="", max_length=255)
    role_scoped_notes: str = Field(default="", max_length=1000)


class FieldVisitStartIn(BaseModel):
    contact_confirmed: bool = True
    patient_consent_verified: bool = True
    location_consent_granted: bool = False
    checkin_latitude: Optional[float] = None
    checkin_longitude: Optional[float] = None
    location_purpose: str = Field(default="", max_length=160)


class FieldVisitCompleteIn(BaseModel):
    patient_consent_verified: bool = True
    completion_evidence_type: str = Field(default="signed_mcp_card_ack", max_length=60)
    completion_evidence_ref: str = Field(min_length=2, max_length=255)
    role_scoped_notes: str = Field(default="", max_length=1500)
    clinical_observations_by_clinician: str = Field(default="", max_length=1500)


class FieldVisitFailRescheduleIn(BaseModel):
    failed_reason: Literal[
        "patient_not_at_home",
        "address_unreachable",
        "weather_road_block",
        "patient_declined",
        "staff_unavailable",
    ]
    rescheduled_to_date: Optional[date] = None
    notes: str = Field(default="", max_length=500)


class FieldVisitPatchIn(BaseModel):
    status: Optional[str] = None
    contact_confirmed: Optional[bool] = None
    patient_consent_verified: Optional[bool] = None
    location_consent_granted: Optional[bool] = None
    checkin_latitude: Optional[float] = None
    checkin_longitude: Optional[float] = None
    location_purpose: Optional[str] = None
    role_scoped_notes: Optional[str] = None
    clinical_observations_by_clinician: Optional[str] = None
    completion_evidence_type: Optional[str] = None
    completion_evidence_ref: Optional[str] = None
    failed_reason: Optional[str] = None
    rescheduled_to_date: Optional[date] = None


class OfflineVisitDraftItem(BaseModel):
    offline_draft_id: str = Field(min_length=3, max_length=80)
    mother_id: str
    assigned_staff_id: str
    visit_date: date
    scheduled_window: str = Field(default="09:00-11:00", max_length=40)
    visit_address: str = Field(default="", max_length=255)
    contact_confirmed: bool = True
    patient_consent_verified: bool = True
    location_consent_granted: bool = False
    checkin_latitude: Optional[float] = None
    checkin_longitude: Optional[float] = None
    location_purpose: str = Field(default="", max_length=160)
    completion_evidence_type: str = Field(default="home_visit_checklist", max_length=60)
    completion_evidence_ref: str = Field(default="OFFLINE-SYNC-ACK", max_length=255)
    role_scoped_notes: str = Field(default="", max_length=1500)
    clinical_observations_by_clinician: str = Field(default="", max_length=1500)


class OfflineSyncBatchIn(BaseModel):
    drafts: list[OfflineVisitDraftItem]


class PartnerFacilityIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    facility_type: Literal[
        "referral_hospital",
        "diagnostic_lab",
        "ultrasound_centre",
        "blood_bank",
        "chc_fr_unit",
    ] = "referral_hospital"
    contact_person: str = Field(default="", max_length=120)
    contact_phone: str = Field(default="", max_length=24)
    address: str = Field(default="", max_length=255)
    services_offered: list[str] = Field(
        default_factory=lambda: ["High-Risk Obstetrics", "Ultrasound", "Complete Blood Count"]
    )
    agreement_reference: str = Field(min_length=2, max_length=100)
    effective_from: date
    effective_until: date
    schedule_charges: dict[str, int] = Field(default_factory=dict)


class HospitalReferralIn(BaseModel):
    mother_id: str
    care_plan_id: Optional[str] = None
    partner_facility_id: str
    referral_category: Literal[
        "clinical_obstetric",
        "routine_ultrasound",
        "diagnostic_lab",
        "administrative_transfer",
    ] = "clinical_obstetric"
    reason_and_clinical_summary: str = Field(min_length=3, max_length=1500)
    requested_services: list[str] = Field(default_factory=list)
    scheduled_service_date: Optional[date] = None
    contractual_charge_rupees: int = Field(default=0, ge=0, le=500000)
    notes: str = Field(default="", max_length=1000)


class ReferralStatusUpdateIn(BaseModel):
    status: Literal[
        "sent_to_partner",
        "acknowledged_by_partner",
        "appointment_booked",
        "service_completed",
        "verified_closed",
        "cancelled",
    ]
    partner_acknowledgement_ref: str = Field(default="", max_length=120)
    scheduled_service_date: Optional[date] = None
    completion_evidence_ref: str = Field(default="", max_length=255)
    contractual_charge_rupees: Optional[int] = Field(default=None, ge=0, le=500000)
    cancellation_reason: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=1000)


class TransportPartnerIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    partner_type: Literal[
        "community_van_contract",
        "102_janani_express_liaison",
        "local_empaneled_taxi",
    ] = "community_van_contract"
    contact_person: str = Field(default="", max_length=120)
    contact_phone: str = Field(default="", max_length=24)
    agreement_ref: str = Field(min_length=2, max_length=100)
    effective_until: date
    base_tariff_rupees: int = Field(default=500, ge=0, le=100000)


class VehicleDriverIn(BaseModel):
    partner_id: str
    driver_name: str = Field(min_length=2, max_length=120)
    driver_phone: str = Field(min_length=8, max_length=24)
    driving_licence_no: str = Field(min_length=4, max_length=80)
    licence_expiry_date: date
    vehicle_registration_no: str = Field(min_length=4, max_length=60)
    vehicle_type: Literal[
        "patient_transport_van",
        "empaneled_sedan",
        "basic_support_ambulance",
    ] = "patient_transport_van"
    insurance_policy_no: str = Field(min_length=4, max_length=80)
    insurance_expiry_date: date


class TripAssignIn(BaseModel):
    partner_id: Optional[str] = None
    vehicle_driver_id: str
    pickup_time: Optional[str] = Field(default=None, max_length=20)
    fare_rupees: Optional[int] = Field(default=None, ge=0, le=100000)


class DriverResponseIn(BaseModel):
    response: Optional[Literal["accepted", "rejected"]] = None
    decision: Optional[Literal["accepted", "rejected"]] = None
    rejection_reason: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=200)


class TripLifecycleIn(BaseModel):
    action: Optional[
        Literal["start_trip", "complete_trip", "fail_pickup", "cancel_trip", "reassign_driver"]
    ] = None
    status: Optional[str] = None
    trip_expense_rupees: int = Field(default=0, ge=0, le=100000)
    actual_fare_rupees: int = Field(default=0, ge=0, le=100000)
    receipt_ref: str = Field(default="", max_length=120)
    failed_pickup_reason: str = Field(default="", max_length=200)
    cancellation_reason: str = Field(default="", max_length=200)
    new_vehicle_driver_id: Optional[str] = None
    vehicle_notes: str = Field(default="", max_length=500)


class GovernanceIncidentIn(BaseModel):
    incident_type: Literal[
        "missed_high_priority_visit",
        "credential_expiry_alert",
        "partner_contract_expiry",
        "failed_pickup_escalation",
        "data_correction_request",
        "protocol_deviation",
    ] = "protocol_deviation"
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    entity_type: str = Field(default="", max_length=60)
    entity_id: str = Field(default="", max_length=60)
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=5, max_length=2000)
    assigned_reviewer_id: Optional[str] = None


class GovernanceIncidentUpdateIn(BaseModel):
    status: Literal["open", "under_review", "escalated", "resolved"]
    assigned_reviewer_id: Optional[str] = None
    resolution_notes: str = Field(default="", max_length=2000)


class RecordCorrectionIn(BaseModel):
    entity_type: Literal["mother", "field_visit", "service_request", "transport"]
    entity_id: str
    field_name: str = Field(min_length=2, max_length=80)
    new_value: str = Field(min_length=1, max_length=1000)
    correction_reason: str = Field(min_length=5, max_length=1000)


def _ensure_workforce_profile(db: Session, staff: Staff) -> StaffWorkforceProfile:
    prof = db.scalar(
        select(StaffWorkforceProfile).where(StaffWorkforceProfile.staff_id == staff.id)
    )
    if prof:
        return prof

    nr = normalize_role(staff.role)
    cadre_map = {
        "doctor": "medical_officer_mbbs",
        "nurse": "anm_staff_nurse",
        "field_coordinator": "asha_field_coordinator",
        "admin": "clinic_administrator",
    }
    qual_map = {
        "doctor": "MBBS, DGO",
        "nurse": "B.Sc Nursing / ANM",
        "field_coordinator": "NHM ASHA Coordinator",
        "admin": "Hospital & Clinic Operations",
    }
    prof = StaffWorkforceProfile(
        staff_id=staff.id,
        clinic=staff.clinic,
        employment_type="full_time_employee",
        onboarding_status="active_onboarded" if staff.is_active else "offboarded",
        clinical_cadre=cadre_map.get(nr, "general"),
        qualification=qual_map.get(nr, ""),
        registration_council=(
            "Telangana State Medical Council"
            if nr == "doctor"
            else "Telangana Nursing Council"
            if nr == "nurse"
            else ""
        ),
        registration_number="",
        credential_verification_status="unverified",
        assigned_facility=f"PHC {staff.clinic.replace('-', ' ').title()}",
    )
    db.add(prof)
    try:
        db.flush()
    except Exception:
        db.rollback()
        existing = db.scalar(
            select(StaffWorkforceProfile).where(StaffWorkforceProfile.staff_id == staff.id)
        )
        if existing:
            return existing
        raise
    return prof


def _times_overlap(s1: str, e1: str, s2: str, e2: str) -> bool:
    """Return True if two HH:MM intervals overlap on the same date."""
    return max(s1, s2) < min(e1, e2)


def register_phase5_routes(
    app: FastAPI,
    dbsession: Callable,
    who: Callable,
    permitted: Callable,
    audit: Callable,
    row: Callable,
    mother_for: Callable,
) -> None:
    """Register all Phase 5 Workforce, Service, Field Visit, Partner, Transport & Governance endpoints."""

    # =========================================================================
    # 1. HEALTHCARE WORKFORCE MANAGEMENT
    # =========================================================================
    @app.get("/api/workforce/profiles")
    def list_workforce_profiles(
        role: Optional[str] = Query(default=None),
        onboarding_status: Optional[str] = Query(default=None),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        staff_rows = list(
            db.scalars(
                select(Staff).where(Staff.clinic == s.clinic).order_by(Staff.role, Staff.name)
            )
        )
        out: list[dict[str, Any]] = []
        for st in staff_rows:
            if role and normalize_role(st.role) != normalize_role(role):
                continue
            prof = _ensure_workforce_profile(db, st)
            if onboarding_status and prof.onboarding_status != onboarding_status:
                continue
            creds = [
                row(c)
                for c in db.scalars(
                    select(StaffCredentialDocument)
                    .where(
                        StaffCredentialDocument.staff_id == st.id,
                        StaffCredentialDocument.clinic == s.clinic,
                    )
                    .order_by(StaffCredentialDocument.created_at.desc())
                )
            ]
            d = row(prof)
            d["staff"] = row(st)
            d["staff_name"] = st.name
            d["clinical_role"] = normalize_role(st.role)
            d["credentials"] = creds
            try:
                d["availability_days"] = json.loads(prof.availability_days_json or "[]")
            except Exception:
                d["availability_days"] = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
            out.append(d)
        db.commit()
        return out

    @app.get("/api/workforce/credentials")
    def list_clinic_credentials(
        staff_id: Optional[str] = Query(default=None),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        stmt = select(StaffCredentialDocument).where(StaffCredentialDocument.clinic == s.clinic)
        if staff_id:
            stmt = stmt.where(StaffCredentialDocument.staff_id == staff_id)
        stmt = stmt.order_by(StaffCredentialDocument.created_at.desc())
        return [row(c) for c in db.scalars(stmt)]

    @app.post("/api/workforce/onboard")
    def onboard_workforce_staff(
        p: WorkforceOnboardIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin")
        validate_password_strength(p.password)
        email_norm = p.email.strip().lower()
        dup = db.scalar(select(Staff).where(func.lower(Staff.email) == email_norm))
        if dup:
            raise HTTPException(409, "A staff member with this email already exists")

        new_staff = Staff(
            name=p.name.strip(),
            email=email_norm,
            role=p.role,
            clinic=s.clinic,
            phone=p.phone.strip(),
            password_hash=hash_password(p.password),
            is_active=True,
            token_version=1,
        )
        db.add(new_staff)
        db.flush()

        # Self-entered or initial onboarding registration numbers are NEVER automatically verified!
        init_cred_status = "unverified"
        prof = StaffWorkforceProfile(
            staff_id=new_staff.id,
            clinic=s.clinic,
            employment_type=p.employment_type,
            onboarding_status="active_onboarded",
            clinical_cadre=p.clinical_cadre.strip() or normalize_role(p.role),
            qualification=p.qualification.strip(),
            registration_council=p.registration_council.strip(),
            registration_number=p.registration_number.strip(),
            credential_verification_status=init_cred_status,
            credential_expiry_date=p.credential_expiry_date,
            assigned_facility=p.assigned_facility.strip(),
            availability_days_json=json.dumps(p.availability_days),
            shift_preference=p.shift_preference,
            onboarded_by=s.id,
            onboarded_at=now(),
        )
        db.add(prof)
        db.flush()

        created_cred_doc: Optional[StaffCredentialDocument] = None
        if p.registration_number.strip():
            created_cred_doc = StaffCredentialDocument(
                staff_id=new_staff.id,
                clinic=s.clinic,
                document_type=(
                    "medical_council_registration"
                    if normalize_role(p.role) == "doctor"
                    else "nursing_license"
                    if normalize_role(p.role) == "nurse"
                    else "id_proof"
                ),
                registration_number=p.registration_number.strip(),
                issuing_authority=p.registration_council.strip() or "State Council",
                expiry_date=p.credential_expiry_date,
                verification_status="unverified",
                uploaded_by=s.id,
            )
            db.add(created_cred_doc)
            db.flush()

        audit(
            db,
            s,
            "onboard_staff",
            "staff_workforce_profile",
            prof.id,
            f"staff={new_staff.id}; role={new_staff.role}; employment={p.employment_type}; cred_status={init_cred_status}",
        )
        db.commit()
        res = row(prof)
        res["staff"] = row(new_staff)
        res["credentials"] = [row(created_cred_doc)] if created_cred_doc else []
        return res

    @app.patch("/api/workforce/profiles/{staff_id}")
    def update_workforce_profile(
        staff_id: str,
        p: WorkforceProfileUpdateIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor", "nurse")
        target = db.get(Staff, staff_id)
        if not target or target.clinic != s.clinic:
            raise HTTPException(404, "Staff member not found in your clinic")
        if normalize_role(s.role) != "admin" and s.id != staff_id:
            raise HTTPException(403, "Only clinic administrators may edit another staff member's workforce profile")

        prof = _ensure_workforce_profile(db, target)
        updates = p.model_dump(exclude_unset=True)
        if "availability_days" in updates and updates["availability_days"] is not None:
            prof.availability_days_json = json.dumps(updates.pop("availability_days"))

        # If a staff member self-edits their registration number, reset verification status to pending_review
        if "registration_number" in updates and updates["registration_number"] != prof.registration_number:
            prof.credential_verification_status = "pending_review"
            prof.credential_verified_by = None
            prof.credential_verified_at = None

        for k, v in updates.items():
            setattr(prof, k, v)
        prof.updated_at = now()

        audit(
            db,
            s,
            "update_workforce_profile",
            "staff_workforce_profile",
            prof.id,
            f"staff={staff_id}",
        )
        db.commit()
        res = row(prof)
        res["staff"] = row(target)
        return res

    @app.post("/api/workforce/profiles/{staff_id}/offboard")
    def offboard_staff_member(
        staff_id: str,
        p: OffboardStaffIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin")
        target = db.get(Staff, staff_id)
        if not target or target.clinic != s.clinic:
            raise HTTPException(404, "Staff member not found in your clinic")
        if target.id == s.id:
            raise HTTPException(400, "Cannot offboard your own active administrator account")

        prof = _ensure_workforce_profile(db, target)
        ts = now()
        reason_str = (p.offboarding_reason or p.reason or "Offboarded by administrator").strip()
        prof.onboarding_status = "offboarded"
        prof.offboarded_by = s.id
        prof.offboarded_at = ts
        prof.offboarding_reason = reason_str
        prof.updated_at = ts

        target.is_active = False
        target.token_version = (target.token_version or 1) + 1

        # Flag any active service requests assigned to this staff member for reassignment
        affected_services = list(
            db.scalars(
                select(ServiceRequest).where(
                    ServiceRequest.clinic == s.clinic,
                    ServiceRequest.assigned_staff_id == staff_id,
                    ServiceRequest.status.in_(("staff_assigned", "scheduled")),
                )
            )
        )
        for srv in affected_services:
            srv.status = "unavailable_personnel"
            srv.reassigned_from_staff_id = staff_id
            srv.updated_at = ts

        audit(
            db,
            s,
            "offboard_staff",
            "staff",
            target.id,
            f"reason={p.offboarding_reason}; affected_services={len(affected_services)}",
        )
        db.commit()
        res = row(prof)
        res["staff"] = row(target)
        res["affected_services_count"] = len(affected_services)
        return res

    @app.post("/api/workforce/profiles/{staff_id}/credentials")
    def upload_staff_credential_document(
        staff_id: str,
        p: CredentialDocIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor", "nurse")
        target = db.get(Staff, staff_id)
        if not target or target.clinic != s.clinic:
            raise HTTPException(404, "Staff member not found in your clinic")
        if normalize_role(s.role) != "admin" and s.id != staff_id:
            raise HTTPException(403, "Cannot upload credentials for another staff member unless admin")

        prof = _ensure_workforce_profile(db, target)
        # Always starts unverified — never treat self-uploaded credentials as verified!
        doc = StaffCredentialDocument(
            staff_id=target.id,
            clinic=s.clinic,
            document_type=p.document_type,
            registration_number=p.registration_number.strip(),
            issuing_authority=p.issuing_authority.strip(),
            issued_date=p.issued_date,
            expiry_date=p.expiry_date,
            evidence_filename=p.evidence_filename.strip(),
            evidence_notes=p.evidence_notes.strip(),
            verification_status="unverified",
            uploaded_by=s.id,
        )
        db.add(doc)
        prof.registration_number = p.registration_number.strip()
        prof.registration_council = p.issuing_authority.strip()
        if p.expiry_date:
            prof.credential_expiry_date = p.expiry_date
        if prof.credential_verification_status != "verified":
            prof.credential_verification_status = "pending_review"
        db.flush()

        audit(
            db,
            s,
            "submit_staff_credential",
            "staff_credential_document",
            doc.id,
            f"staff={target.id}; reg={doc.registration_number}; status=unverified",
        )
        db.commit()
        return row(doc)

    @app.post("/api/workforce/credentials/{cred_id}/verify")
    def verify_staff_credential_document(
        cred_id: str,
        p: CredentialVerifyIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        # Only an authorised administrator or senior doctor may verify professional credentials
        permitted(s, "admin", "doctor")
        cred = db.get(StaffCredentialDocument, cred_id)
        if not cred or cred.clinic != s.clinic:
            raise HTTPException(404, "Credential document not found in your clinic")

        # Strict governance rule: Never allow self-verification of professional credentials!
        if cred.staff_id == s.id:
            raise HTTPException(
                403,
                "Self-verification of professional credentials is prohibited. An independent authorised reviewer is required.",
            )

        target = db.get(Staff, cred.staff_id)
        if not target:
            raise HTTPException(404, "Target staff member not found")
        prof = _ensure_workforce_profile(db, target)

        ts = now()
        cred.verification_status = p.decision
        cred.reviewed_by = s.id
        cred.reviewed_by_role = normalize_role(s.role)
        cred.review_evidence_note = p.review_evidence_note.strip()
        cred.reviewed_at = ts

        prof.credential_verification_status = p.decision
        prof.credential_verified_by = s.id
        prof.credential_verified_by_role = normalize_role(s.role)
        prof.credential_verified_at = ts
        prof.credential_evidence_ref = p.review_evidence_note.strip()
        if cred.expiry_date:
            prof.credential_expiry_date = cred.expiry_date
        prof.updated_at = ts

        audit(
            db,
            s,
            f"credential_{p.decision}",
            "staff_credential_document",
            cred.id,
            f"staff={target.id}; reviewer={s.id}; evidence={p.review_evidence_note[:120]}",
        )
        db.commit()
        out = row(cred)
        out["profile_verification_status"] = prof.credential_verification_status
        return out

    # =========================================================================
    # 1B. SHIFTS, ATTENDANCE, LEAVES & WORKLOAD ANALYTICS
    # =========================================================================
    @app.get("/api/workforce/shifts")
    def list_staff_shifts(
        shift_date: Optional[date] = Query(default=None),
        staff_id: Optional[str] = Query(default=None),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        stmt = select(StaffShift).where(StaffShift.clinic == s.clinic)
        if shift_date:
            stmt = stmt.where(StaffShift.shift_date == shift_date)
        if staff_id:
            stmt = stmt.where(StaffShift.staff_id == staff_id)
        stmt = stmt.order_by(StaffShift.shift_date.desc(), StaffShift.start_time.asc())

        staff_map = {
            st.id: st for st in db.scalars(select(Staff).where(Staff.clinic == s.clinic))
        }
        out: list[dict[str, Any]] = []
        for sh in db.scalars(stmt):
            d = row(sh)
            st = staff_map.get(sh.staff_id)
            rep = staff_map.get(sh.replacement_staff_id) if sh.replacement_staff_id else None
            d["staff_name"] = st.name if st else sh.staff_id
            d["staff_role"] = normalize_role(st.role) if st else ""
            d["replacement_staff_name"] = rep.name if rep else None
            out.append(d)
        return out

    @app.post("/api/workforce/shifts")
    def assign_staff_shift(
        p: ShiftAssignIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor", "nurse")
        target = db.get(Staff, p.staff_id)
        if not target or target.clinic != s.clinic:
            raise HTTPException(404, "Staff member not found in your clinic")
        if not target.is_active:
            raise HTTPException(400, "Cannot assign shift to an inactive/offboarded staff member")
        if p.start_time >= p.end_time:
            raise HTTPException(422, "Shift start_time must be earlier than end_time")

        # Check approved leave conflict
        active_leave = db.scalar(
            select(StaffLeaveRequest).where(
                StaffLeaveRequest.clinic == s.clinic,
                StaffLeaveRequest.staff_id == p.staff_id,
                StaffLeaveRequest.status == "approved",
                StaffLeaveRequest.start_date <= p.shift_date,
                StaffLeaveRequest.end_date >= p.shift_date,
            )
        )
        if active_leave:
            raise HTTPException(
                409,
                f"Shift conflict: {target.name} has approved {active_leave.leave_type} leave on {p.shift_date}",
            )

        # Check overlapping shift conflict on the same date
        existing_shifts = list(
            db.scalars(
                select(StaffShift).where(
                    StaffShift.clinic == s.clinic,
                    StaffShift.staff_id == p.staff_id,
                    StaffShift.shift_date == p.shift_date,
                    StaffShift.status.in_(("scheduled", "checked_in")),
                )
            )
        )
        for ex in existing_shifts:
            if _times_overlap(p.start_time, p.end_time, ex.start_time, ex.end_time):
                raise HTTPException(
                    409,
                    f"Shift conflict: {target.name} is already assigned to shift {ex.id} ({ex.start_time}-{ex.end_time}) on {p.shift_date}",
                )

        sh = StaffShift(
            staff_id=p.staff_id,
            clinic=s.clinic,
            facility_name=p.facility_name.strip(),
            shift_date=p.shift_date,
            start_time=p.start_time,
            end_time=p.end_time,
            shift_type=p.shift_type,
            status="scheduled",
            notes=p.notes.strip(),
            assigned_by=s.id,
        )
        db.add(sh)
        db.flush()
        audit(
            db,
            s,
            "assign_shift",
            "staff_shift",
            sh.id,
            f"staff={p.staff_id}; date={p.shift_date}; {p.start_time}-{p.end_time}",
        )
        db.commit()
        d = row(sh)
        d["staff_name"] = target.name
        d["staff_role"] = normalize_role(target.role)
        return d

    @app.patch("/api/workforce/shifts/{shift_id}/attendance")
    def update_shift_attendance(
        shift_id: str,
        p: ShiftAttendanceIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        sh = db.get(StaffShift, shift_id)
        if not sh or sh.clinic != s.clinic:
            raise HTTPException(404, "Shift not found in your clinic")

        ts = now()
        sh.status = p.status
        if p.status == "checked_in" and not sh.check_in_at:
            sh.check_in_at = ts
        elif p.status == "completed" and not sh.check_out_at:
            sh.check_out_at = ts
        if p.replacement_staff_id is not None:
            if p.replacement_staff_id:
                rep = db.get(Staff, p.replacement_staff_id)
                if not rep or rep.clinic != s.clinic:
                    raise HTTPException(400, "Replacement staff not found in your clinic")
            sh.replacement_staff_id = p.replacement_staff_id
        if p.notes is not None:
            sh.notes = p.notes.strip()

        audit(
            db,
            s,
            "shift_attendance",
            "staff_shift",
            sh.id,
            f"status={p.status}; replacement={sh.replacement_staff_id}",
        )
        db.commit()
        return row(sh)

    @app.get("/api/workforce/leaves")
    def list_staff_leaves(
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        staff_map = {
            st.id: st.name for st in db.scalars(select(Staff).where(Staff.clinic == s.clinic))
        }
        out: list[dict[str, Any]] = []
        for lv in db.scalars(
            select(StaffLeaveRequest)
            .where(StaffLeaveRequest.clinic == s.clinic)
            .order_by(StaffLeaveRequest.start_date.desc())
        ):
            d = row(lv)
            d["staff_name"] = staff_map.get(lv.staff_id, lv.staff_id)
            d["replacement_staff_name"] = (
                staff_map.get(lv.replacement_staff_id) if lv.replacement_staff_id else None
            )
            out.append(d)
        return out

    @app.post("/api/workforce/leaves")
    def create_leave_request(
        p: LeaveRequestIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        target = db.get(Staff, p.staff_id)
        if not target or target.clinic != s.clinic:
            raise HTTPException(404, "Staff member not found in your clinic")
        if p.end_date < p.start_date:
            raise HTTPException(422, "Leave end_date cannot be earlier than start_date")
        if p.replacement_staff_id:
            rep = db.get(Staff, p.replacement_staff_id)
            if not rep or rep.clinic != s.clinic:
                raise HTTPException(400, "Replacement staff member must belong to your clinic")

        lv = StaffLeaveRequest(
            staff_id=p.staff_id,
            clinic=s.clinic,
            start_date=p.start_date,
            end_date=p.end_date,
            leave_type=p.leave_type,
            reason=p.reason.strip(),
            status="pending",
            replacement_staff_id=p.replacement_staff_id,
        )
        db.add(lv)
        db.flush()
        audit(
            db,
            s,
            "request_leave",
            "staff_leave_request",
            lv.id,
            f"staff={p.staff_id}; {p.start_date}..{p.end_date}",
        )
        db.commit()
        return row(lv)

    @app.patch("/api/workforce/leaves/{leave_id}")
    @app.patch("/api/workforce/leaves/{leave_id}/decision")
    def decide_leave_request(
        leave_id: str,
        p: LeaveDecisionIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor")
        lv = db.get(StaffLeaveRequest, leave_id)
        if not lv or lv.clinic != s.clinic:
            raise HTTPException(404, "Leave request not found in your clinic")

        lv.status = p.status
        if p.replacement_staff_id is not None:
            if p.replacement_staff_id:
                rep = db.get(Staff, p.replacement_staff_id)
                if not rep or rep.clinic != s.clinic:
                    raise HTTPException(400, "Replacement staff not found in your clinic")
            lv.replacement_staff_id = p.replacement_staff_id
        lv.approved_by = s.id
        lv.approved_at = now()

        covered_shifts = 0
        if p.status == "approved":
            overlapping_shifts = list(
                db.scalars(
                    select(StaffShift).where(
                        StaffShift.clinic == s.clinic,
                        StaffShift.staff_id == lv.staff_id,
                        StaffShift.shift_date >= lv.start_date,
                        StaffShift.shift_date <= lv.end_date,
                        StaffShift.status == "scheduled",
                    )
                )
            )
            for sh in overlapping_shifts:
                sh.status = "leave_covered" if lv.replacement_staff_id else "cancelled"
                sh.replacement_staff_id = lv.replacement_staff_id
                covered_shifts += 1

        audit(
            db,
            s,
            f"leave_{p.status}",
            "staff_leave_request",
            lv.id,
            f"replacement={lv.replacement_staff_id}; covered_shifts={covered_shifts}",
        )
        db.commit()
        out = row(lv)
        out["covered_shifts"] = covered_shifts
        return out

    # =========================================================================
    # 2. PATIENT SERVICE COORDINATION LIFECYCLE
    # =========================================================================
    @app.get("/api/services")
    def list_service_requests(
        status: Optional[str] = Query(default=None),
        mother_id: Optional[str] = Query(default=None),
        assigned_staff_id: Optional[str] = Query(default=None),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        stmt = select(ServiceRequest).where(ServiceRequest.clinic == s.clinic)
        if status:
            stmt = stmt.where(ServiceRequest.status == status)
        if mother_id:
            mother_for(db, s, mother_id)
            stmt = stmt.where(ServiceRequest.mother_id == mother_id)
        if assigned_staff_id:
            stmt = stmt.where(ServiceRequest.assigned_staff_id == assigned_staff_id)
        stmt = stmt.order_by(ServiceRequest.created_at.desc())

        mothers_map = {
            m.id: m.name for m in db.scalars(select(Mother).where(Mother.clinic == s.clinic))
        }
        staff_map = {
            st.id: st.name for st in db.scalars(select(Staff).where(Staff.clinic == s.clinic))
        }
        out: list[dict[str, Any]] = []
        for srv in db.scalars(stmt):
            d = row(srv)
            d["mother_name"] = mothers_map.get(srv.mother_id, srv.mother_id)
            d["assigned_staff_name"] = (
                staff_map.get(srv.assigned_staff_id) if srv.assigned_staff_id else None
            )
            d["allowed_transitions"] = sorted(
                list(ALLOWED_SERVICE_TRANSITIONS.get(srv.status, set()))
            )
            out.append(d)
        return out

    @app.post("/api/services")
    def create_service_request(
        p: ServiceRequestIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor", "nurse", "field_coordinator")
        m = mother_for(db, s, p.mother_id)
        caller_role = normalize_role(s.role)

        # Healthcare authority boundary: Administrative coordinators cannot authorise clinical consultations
        if p.service_type == "clinical_consultation" and caller_role in ("admin", "field_coordinator"):
            raise HTTPException(
                403,
                "Administrative coordinators are not permitted to authorise clinical consultations or treatment decisions. Requires a licensed doctor or nurse.",
            )

        if p.care_plan_id:
            cp = db.get(CarePlan, p.care_plan_id)
            if not cp or cp.clinic != s.clinic or cp.mother_id != m.id:
                raise HTTPException(404, "Linked care plan not found for this mother")

        requires_clinical = p.requires_clinical_qualification or p.service_type in (
            "clinical_consultation",
            "postnatal_check",
            "lab_sample_collection",
        )
        assigned_staff_id: Optional[str] = None
        assigned_staff_role: str = ""
        init_status = "service_requested"
        if p.assigned_staff_id:
            assignee = db.get(Staff, p.assigned_staff_id)
            if not assignee or assignee.clinic != s.clinic or not assignee.is_active:
                raise HTTPException(400, "Assigned staff member not found or inactive in your clinic")
            assignee_role = normalize_role(assignee.role)
            if requires_clinical and assignee_role not in ("doctor", "nurse"):
                raise HTTPException(
                    403,
                    f"Service '{p.service_type}' requires clinical qualification (doctor or nurse); cannot assign role '{assignee.role}'.",
                )
            assigned_staff_id = assignee.id
            assigned_staff_role = assignee_role
            init_status = "staff_assigned"

        srv = ServiceRequest(
            mother_id=m.id,
            care_plan_id=p.care_plan_id,
            clinic=s.clinic,
            service_type=p.service_type,
            requires_clinical_qualification=requires_clinical,
            priority=p.priority,
            status=init_status,
            assigned_staff_id=assigned_staff_id,
            assigned_staff_role=assigned_staff_role,
            scheduled_date=p.scheduled_date,
            scheduled_time=p.scheduled_time,
            clinical_authorisation_by=s.id if caller_role == "doctor" else None,
            notes=p.notes.strip(),
            created_by=s.id,
        )
        db.add(srv)
        db.flush()
        audit(
            db,
            s,
            "create_service_request",
            "service_request",
            srv.id,
            f"type={srv.service_type}; mother={m.id}; clinical_req={requires_clinical}",
        )
        db.commit()
        d = row(srv)
        d["mother_name"] = m.name
        d["allowed_transitions"] = sorted(
            list(ALLOWED_SERVICE_TRANSITIONS.get(srv.status, set()))
        )
        return d

    @app.post("/api/services/{srv_id}/assign")
    def assign_service_request_staff(
        srv_id: str,
        p: ServiceAssignIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor", "nurse")
        srv = db.get(ServiceRequest, srv_id)
        if not srv or srv.clinic != s.clinic:
            raise HTTPException(404, "Service request not found in your clinic")
        assignee = db.get(Staff, p.assigned_staff_id)
        if not assignee or assignee.clinic != s.clinic:
            raise HTTPException(404, "Assigned staff member not found in your clinic")
        if not assignee.is_active:
            raise HTTPException(400, "Cannot assign service to an inactive/offboarded staff member")

        assignee_role = normalize_role(assignee.role)
        # Qualification & clinical boundary check
        if srv.requires_clinical_qualification and assignee_role not in ("doctor", "nurse"):
            raise HTTPException(
                403,
                f"Service '{srv.service_type}' requires clinical qualification (doctor or nurse); cannot assign role '{assignee.role}'.",
            )

        if srv.assigned_staff_id and srv.assigned_staff_id != assignee.id:
            srv.reassigned_from_staff_id = srv.assigned_staff_id

        srv.assigned_staff_id = assignee.id
        srv.assigned_staff_role = assignee_role
        if p.scheduled_date:
            srv.scheduled_date = p.scheduled_date
        if p.scheduled_time:
            srv.scheduled_time = p.scheduled_time
        srv.status = "scheduled" if srv.scheduled_date else "staff_assigned"
        srv.updated_at = now()

        audit(
            db,
            s,
            "assign_service_staff",
            "service_request",
            srv.id,
            f"assigned_to={assignee.id} ({assignee_role}); status={srv.status}",
        )
        db.commit()
        d = row(srv)
        d["assigned_staff_name"] = assignee.name
        d["allowed_transitions"] = sorted(
            list(ALLOWED_SERVICE_TRANSITIONS.get(srv.status, set()))
        )
        return d

    @app.post("/api/services/{srv_id}/transition")
    @app.patch("/api/services/{srv_id}/transition")
    def transition_service_request(
        srv_id: str,
        p: ServiceTransitionIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        srv = db.get(ServiceRequest, srv_id)
        if not srv or srv.clinic != s.clinic:
            raise HTTPException(404, "Service request not found in your clinic")

        current = srv.status
        target = p.target_state or p.status
        if not target:
            raise HTTPException(422, "target_state or status is required")
        if current != target:
            allowed = ALLOWED_SERVICE_TRANSITIONS.get(current, set())
            if target not in allowed:
                raise HTTPException(
                    409,
                    f"Invalid service transition from '{current}' to '{target}'. Allowed: {sorted(list(allowed))}",
                )

        caller_role = normalize_role(s.role)
        if target == "verified" and srv.requires_clinical_qualification and caller_role not in ("doctor", "nurse", "admin"):
            raise HTTPException(403, "Only clinical or supervisory staff may verify service completion")

        if target == "cancelled" and not p.cancellation_reason.strip():
            raise HTTPException(422, "cancellation_reason is required when cancelling a service request")

        ts = now()
        srv.status = target
        srv.updated_at = ts
        if target == "in_progress":
            srv.started_at = srv.started_at or ts
        elif target == "completed":
            srv.completed_at = srv.completed_at or ts
            if p.completion_evidence:
                srv.completion_evidence = p.completion_evidence.strip()
        elif target == "verified":
            srv.verified_by = s.id
            srv.verified_at = ts
        elif target == "closed":
            srv.closed_at = ts
        elif target == "cancelled":
            srv.cancellation_reason = p.cancellation_reason.strip()
        elif target in ("failed_visit", "no_show"):
            srv.failure_reason = p.failure_reason.strip() or target

        if p.reassigned_staff_id:
            new_st = db.get(Staff, p.reassigned_staff_id)
            if not new_st or new_st.clinic != s.clinic or not new_st.is_active:
                raise HTTPException(400, "Invalid replacement staff member in your clinic")
            srv.reassigned_from_staff_id = srv.assigned_staff_id
            srv.assigned_staff_id = new_st.id
            srv.assigned_staff_role = normalize_role(new_st.role)

        if p.notes:
            srv.notes = f"{srv.notes}\n{p.notes.strip()}".strip()

        audit(
            db,
            s,
            "service_state_transition",
            "service_request",
            srv.id,
            f"{current} -> {target}",
        )
        db.commit()
        d = row(srv)
        d["allowed_transitions"] = sorted(
            list(ALLOWED_SERVICE_TRANSITIONS.get(srv.status, set()))
        )
        return d

    # =========================================================================
    # 3. FIELD VISIT MANAGEMENT & OFFLINE-CAPABLE DRAFT SYNC
    # =========================================================================
    @app.get("/api/field-visits")
    def list_field_visits(
        visit_date: Optional[date] = Query(default=None),
        assigned_staff_id: Optional[str] = Query(default=None),
        status: Optional[str] = Query(default=None),
        mother_id: Optional[str] = Query(default=None),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        stmt = select(FieldVisit).where(FieldVisit.clinic == s.clinic)
        if visit_date:
            stmt = stmt.where(FieldVisit.visit_date == visit_date)
        if assigned_staff_id:
            stmt = stmt.where(FieldVisit.assigned_staff_id == assigned_staff_id)
        if status:
            stmt = stmt.where(FieldVisit.status == status)
        if mother_id:
            mother_for(db, s, mother_id)
            stmt = stmt.where(FieldVisit.mother_id == mother_id)
        stmt = stmt.order_by(FieldVisit.visit_date.desc(), FieldVisit.created_at.desc())

        mothers_map = {
            m.id: m for m in db.scalars(select(Mother).where(Mother.clinic == s.clinic))
        }
        staff_map = {
            st.id: st for st in db.scalars(select(Staff).where(Staff.clinic == s.clinic))
        }
        out: list[dict[str, Any]] = []
        for fv in db.scalars(stmt):
            d = row(fv)
            m = mothers_map.get(fv.mother_id)
            st = staff_map.get(fv.assigned_staff_id)
            d["mother_name"] = m.name if m else fv.mother_id
            d["mother_phone"] = m.phone if m else ""
            d["assigned_staff_name"] = st.name if st else fv.assigned_staff_id
            out.append(d)
        return out

    @app.post("/api/field-visits")
    def create_field_visit(
        p: FieldVisitCreateIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor", "nurse", "field_coordinator")
        m = mother_for(db, s, p.mother_id)
        assignee = db.get(Staff, p.assigned_staff_id)
        if not assignee or assignee.clinic != s.clinic or not assignee.is_active:
            raise HTTPException(400, "Assigned staff member not found or inactive in your clinic")

        fv = FieldVisit(
            service_request_id=p.service_request_id,
            mother_id=m.id,
            care_plan_id=p.care_plan_id,
            clinic=s.clinic,
            assigned_staff_id=assignee.id,
            staff_role=normalize_role(assignee.role),
            visit_date=p.visit_date,
            scheduled_window=p.scheduled_window.strip(),
            visit_address=p.visit_address.strip() or m.address,
            status="scheduled",
            role_scoped_notes=p.role_scoped_notes.strip(),
            created_by=s.id,
        )
        db.add(fv)
        if p.service_request_id:
            srv = db.get(ServiceRequest, p.service_request_id)
            if srv and srv.clinic == s.clinic:
                srv.assigned_staff_id = assignee.id
                srv.assigned_staff_role = normalize_role(assignee.role)
                srv.scheduled_date = p.visit_date
                if srv.status in ("service_requested", "staff_assigned", "reassignment_required"):
                    srv.status = "scheduled"
        db.flush()
        audit(
            db,
            s,
            "schedule_field_visit",
            "field_visit",
            fv.id,
            f"mother={m.id}; staff={assignee.id}; date={p.visit_date}",
        )
        db.commit()
        d = row(fv)
        d["mother_name"] = m.name
        d["assigned_staff_name"] = assignee.name
        return d

    @app.post("/api/field-visits/{vid}/start")
    def start_field_visit(
        vid: str,
        p: FieldVisitStartIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        fv = db.get(FieldVisit, vid)
        if not fv or fv.clinic != s.clinic:
            raise HTTPException(404, "Field visit not found in your clinic")
        mother_for(db, s, fv.mother_id)

        if not p.patient_consent_verified:
            raise HTTPException(400, "Patient consent verification is required before starting a field visit")

        # Location collection privacy guard: strictly optional, purpose-limited, and requires explicit consent
        if p.checkin_latitude is not None or p.checkin_longitude is not None:
            if not p.location_consent_granted:
                raise HTTPException(
                    403,
                    "Location coordinates cannot be recorded without explicit location_consent_granted=true.",
                )
            if not p.location_purpose.strip():
                raise HTTPException(
                    422,
                    "location_purpose is required when recording optional point-in-time check-in coordinates.",
                )
            fv.location_consent_granted = True
            fv.checkin_latitude = p.checkin_latitude
            fv.checkin_longitude = p.checkin_longitude
            fv.location_purpose = p.location_purpose.strip()

        fv.contact_confirmed = p.contact_confirmed
        fv.patient_consent_verified = True
        fv.status = "in_progress"
        fv.started_at = now()

        if fv.service_request_id:
            srv = db.get(ServiceRequest, fv.service_request_id)
            if srv and srv.clinic == s.clinic:
                srv.status = "in_progress"
                srv.started_at = srv.started_at or fv.started_at

        audit(
            db,
            s,
            "start_field_visit",
            "field_visit",
            fv.id,
            f"consent_verified=True; location_consented={fv.location_consent_granted}",
        )
        db.commit()
        return row(fv)

    @app.post("/api/field-visits/{vid}/complete")
    def complete_field_visit(
        vid: str,
        p: FieldVisitCompleteIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        fv = db.get(FieldVisit, vid)
        if not fv or fv.clinic != s.clinic:
            raise HTTPException(404, "Field visit not found in your clinic")
        mother_for(db, s, fv.mother_id)

        caller_role = normalize_role(s.role)
        # Role-scoped notes enforcement: Field coordinators cannot author clinical observations
        if p.clinical_observations_by_clinician.strip() and caller_role not in ("doctor", "nurse"):
            raise HTTPException(
                403,
                "Field coordinators and administrative staff cannot record clinical observations. Only licensed doctors or nurses may enter clinical notes.",
            )

        ts = now()
        fv.patient_consent_verified = p.patient_consent_verified
        fv.status = "completed"
        fv.completed_at = ts
        fv.completion_evidence_type = p.completion_evidence_type
        fv.completion_evidence_ref = p.completion_evidence_ref.strip()
        if p.role_scoped_notes.strip():
            fv.role_scoped_notes = p.role_scoped_notes.strip()
        if p.clinical_observations_by_clinician.strip():
            fv.clinical_observations_by_clinician = p.clinical_observations_by_clinician.strip()

        if fv.service_request_id:
            srv = db.get(ServiceRequest, fv.service_request_id)
            if srv and srv.clinic == s.clinic:
                srv.status = "completed"
                srv.completed_at = ts
                srv.completion_evidence = f"{p.completion_evidence_type}:{p.completion_evidence_ref}"

        audit(
            db,
            s,
            "complete_field_visit",
            "field_visit",
            fv.id,
            f"evidence={p.completion_evidence_type}:{p.completion_evidence_ref}",
        )
        db.commit()
        return row(fv)

    @app.post("/api/field-visits/{vid}/fail-or-reschedule")
    def fail_or_reschedule_field_visit(
        vid: str,
        p: FieldVisitFailRescheduleIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        fv = db.get(FieldVisit, vid)
        if not fv or fv.clinic != s.clinic:
            raise HTTPException(404, "Field visit not found in your clinic")
        mother_for(db, s, fv.mother_id)

        fv.failed_reason = p.failed_reason
        if p.rescheduled_to_date:
            fv.status = "rescheduled"
            fv.rescheduled_to_date = p.rescheduled_to_date
            fv.visit_date = p.rescheduled_to_date
        else:
            fv.status = "failed_visit"

        if p.notes.strip():
            fv.role_scoped_notes = f"{fv.role_scoped_notes}\n[Failed/Rescheduled: {p.notes.strip()}]".strip()

        if fv.service_request_id:
            srv = db.get(ServiceRequest, fv.service_request_id)
            if srv and srv.clinic == s.clinic:
                srv.status = "scheduled" if p.rescheduled_to_date else "failed_visit"
                srv.failure_reason = p.failed_reason

        audit(
            db,
            s,
            "field_visit_failed_or_rescheduled",
            "field_visit",
            fv.id,
            f"reason={p.failed_reason}; rescheduled_to={p.rescheduled_to_date}",
        )
        db.commit()
        return row(fv)

    @app.patch("/api/field-visits/{vid}")
    def patch_field_visit(
        vid: str,
        p: FieldVisitPatchIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        fv = db.get(FieldVisit, vid)
        if not fv or fv.clinic != s.clinic:
            raise HTTPException(404, "Field visit not found in your clinic")
        mother_for(db, s, fv.mother_id)

        caller_role = normalize_role(s.role)
        if p.clinical_observations_by_clinician and p.clinical_observations_by_clinician.strip():
            if caller_role not in ("doctor", "nurse"):
                raise HTTPException(
                    403,
                    "Field coordinators and administrative staff cannot record clinical observations.",
                )
            fv.clinical_observations_by_clinician = p.clinical_observations_by_clinician.strip()

        if p.checkin_latitude is not None or p.checkin_longitude is not None:
            loc_consented = bool(p.location_consent_granted or fv.location_consent_granted)
            if not loc_consented:
                raise HTTPException(
                    403,
                    "Location coordinates cannot be recorded without explicit location_consent_granted=true.",
                )
            purpose = (p.location_purpose or fv.location_purpose or "").strip()
            if not purpose:
                raise HTTPException(
                    422,
                    "location_purpose is required when recording optional point-in-time check-in coordinates.",
                )
            fv.location_consent_granted = True
            fv.checkin_latitude = p.checkin_latitude
            fv.checkin_longitude = p.checkin_longitude
            fv.location_purpose = purpose

        if p.contact_confirmed is not None:
            fv.contact_confirmed = p.contact_confirmed
        if p.patient_consent_verified is not None:
            fv.patient_consent_verified = p.patient_consent_verified
        if p.role_scoped_notes is not None:
            fv.role_scoped_notes = p.role_scoped_notes.strip()
        if p.completion_evidence_type is not None:
            fv.completion_evidence_type = p.completion_evidence_type.strip()
        if p.completion_evidence_ref is not None:
            fv.completion_evidence_ref = p.completion_evidence_ref.strip()
        if p.failed_reason is not None:
            fv.failed_reason = p.failed_reason.strip()
        if p.rescheduled_to_date is not None:
            fv.rescheduled_to_date = p.rescheduled_to_date
            fv.visit_date = p.rescheduled_to_date

        ts = now()
        if p.status:
            if p.status in ("in_progress", "completed") and not fv.patient_consent_verified:
                raise HTTPException(
                    400, "Patient consent verification is required before starting or completing a field visit"
                )
            fv.status = p.status
            if p.status == "in_progress":
                fv.started_at = fv.started_at or ts
            elif p.status == "completed":
                fv.completed_at = fv.completed_at or ts

        audit(
            db,
            s,
            "patch_field_visit",
            "field_visit",
            fv.id,
            f"status={fv.status}",
        )
        db.commit()
        return row(fv)

    @app.post("/api/field-visits/offline-sync")
    def sync_offline_field_visit_drafts(
        p: OfflineSyncBatchIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        """Controlled idempotent synchronization for offline field-worker visit drafts."""
        synced: list[dict[str, Any]] = []
        duplicates_skipped = 0
        ts = now()

        for draft in p.drafts:
            existing = db.scalar(
                select(FieldVisit).where(
                    FieldVisit.clinic == s.clinic,
                    FieldVisit.offline_draft_id == draft.offline_draft_id,
                )
            )
            if existing:
                duplicates_skipped += 1
                synced.append(row(existing))
                continue

            m = mother_for(db, s, draft.mother_id)
            assignee = db.get(Staff, draft.assigned_staff_id)
            if not assignee or assignee.clinic != s.clinic:
                raise HTTPException(400, f"Staff {draft.assigned_staff_id} not found in clinic")

            fv = FieldVisit(
                mother_id=m.id,
                clinic=s.clinic,
                assigned_staff_id=assignee.id,
                staff_role=normalize_role(assignee.role),
                visit_date=draft.visit_date,
                scheduled_window=draft.scheduled_window,
                visit_address=draft.visit_address or m.address,
                status="completed",
                contact_confirmed=True,
                patient_consent_verified=draft.patient_consent_verified,
                started_at=ts,
                completed_at=ts,
                role_scoped_notes=draft.role_scoped_notes.strip(),
                completion_evidence_type=draft.completion_evidence_type,
                completion_evidence_ref=draft.completion_evidence_ref,
                offline_draft_id=draft.offline_draft_id,
                synced_from_offline=True,
                created_by=s.id,
            )
            db.add(fv)
            db.flush()
            synced.append(row(fv))

        audit(
            db,
            s,
            "offline_field_visits_sync",
            "field_visit",
            s.clinic,
            f"synced={len(synced) - duplicates_skipped}; duplicates_skipped={duplicates_skipped}",
        )
        db.commit()
        return {
            "synced_count": len(synced) - duplicates_skipped,
            "duplicates_skipped": duplicates_skipped,
            "visits": synced,
        }

    # =========================================================================
    # 4. HOSPITAL & DIAGNOSTIC PARTNERSHIPS AND REFERRALS
    # =========================================================================
    @app.get("/api/partners/facilities")
    def list_partner_facilities(
        facility_type: Optional[str] = Query(default=None),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        stmt = select(PartnerFacility).where(PartnerFacility.clinic == s.clinic)
        if facility_type:
            stmt = stmt.where(PartnerFacility.facility_type == facility_type)
        stmt = stmt.order_by(PartnerFacility.name.asc())

        today = date.today()
        out: list[dict[str, Any]] = []
        for pf in db.scalars(stmt):
            d = row(pf)
            try:
                d["services_offered"] = json.loads(pf.services_offered_json or "[]")
            except Exception:
                d["services_offered"] = []
            try:
                d["schedule_charges"] = json.loads(pf.schedule_charges_json or "{}")
            except Exception:
                d["schedule_charges"] = {}
            d["days_until_expiry"] = (pf.effective_until - today).days if pf.effective_until else 0
            d["contract_expired"] = bool(pf.effective_until and pf.effective_until < today)
            out.append(d)
        return out

    @app.post("/api/partners/facilities")
    def register_partner_facility(
        p: PartnerFacilityIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor")
        if p.effective_until < p.effective_from:
            raise HTTPException(422, "effective_until must be on or after effective_from")

        today = date.today()
        c_status = (
            "expired"
            if p.effective_until < today
            else "expiring_soon"
            if (p.effective_until - today).days <= 30
            else "active"
        )
        pf = PartnerFacility(
            clinic=s.clinic,
            name=p.name.strip(),
            facility_type=p.facility_type,
            contact_person=p.contact_person.strip(),
            contact_phone=p.contact_phone.strip(),
            address=p.address.strip(),
            services_offered_json=json.dumps(p.services_offered),
            agreement_reference=p.agreement_reference.strip(),
            effective_from=p.effective_from,
            effective_until=p.effective_until,
            contract_status=c_status,
            schedule_charges_json=json.dumps(p.schedule_charges),
            is_verified_partner=True,
            created_by=s.id,
        )
        db.add(pf)
        db.flush()
        audit(
            db,
            s,
            "register_partner_facility",
            "partner_facility",
            pf.id,
            f"name={pf.name}; type={pf.facility_type}; ref={pf.agreement_reference}",
        )
        db.commit()
        d = row(pf)
        d["services_offered"] = p.services_offered
        d["schedule_charges"] = p.schedule_charges
        return d

    @app.get("/api/referrals")
    def list_hospital_referrals(
        status: Optional[str] = Query(default=None),
        mother_id: Optional[str] = Query(default=None),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        stmt = select(HospitalReferral).where(HospitalReferral.clinic == s.clinic)
        if status:
            stmt = stmt.where(HospitalReferral.status == status)
        if mother_id:
            mother_for(db, s, mother_id)
            stmt = stmt.where(HospitalReferral.mother_id == mother_id)
        stmt = stmt.order_by(HospitalReferral.created_at.desc())

        mothers_map = {
            m.id: m.name for m in db.scalars(select(Mother).where(Mother.clinic == s.clinic))
        }
        partners_map = {
            pf.id: pf.name
            for pf in db.scalars(select(PartnerFacility).where(PartnerFacility.clinic == s.clinic))
        }
        out: list[dict[str, Any]] = []
        for ref in db.scalars(stmt):
            d = row(ref)
            d["mother_name"] = mothers_map.get(ref.mother_id, ref.mother_id)
            d["partner_facility_name"] = partners_map.get(
                ref.partner_facility_id, ref.partner_facility_id
            )
            d["contractual_charge_rupees"] = round((ref.contractual_charge_paise or 0) / 100, 2)
            try:
                d["requested_services"] = json.loads(ref.requested_services_json or "[]")
            except Exception:
                d["requested_services"] = []
            out.append(d)
        return out

    @app.post("/api/referrals")
    def create_hospital_referral(
        p: HospitalReferralIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        # Healthcare restriction: Only a licensed clinician (doctor, or nurse for routine diagnostic protocol)
        # may authorise referrals when clinical judgement is required. Never use AI to select destinations!
        caller_role = normalize_role(s.role)
        if p.referral_category == "clinical_obstetric" and caller_role != "doctor":
            raise HTTPException(
                403,
                "Clinical obstetric referrals require clinical judgement and must be authorised by a licensed doctor.",
            )
        if p.referral_category in ("routine_ultrasound", "diagnostic_lab") and caller_role not in ("doctor", "nurse"):
            raise HTTPException(
                403,
                "Diagnostic and ultrasound referrals must be authorised by a licensed doctor or nurse.",
            )

        m = mother_for(db, s, p.mother_id)
        pf = db.get(PartnerFacility, p.partner_facility_id)
        if not pf or pf.clinic != s.clinic:
            raise HTTPException(404, "Partner facility not found in your clinic")
        if pf.effective_until and pf.effective_until < date.today():
            raise HTTPException(400, f"Partner facility '{pf.name}' partnership agreement has expired")

        ref = HospitalReferral(
            mother_id=m.id,
            care_plan_id=p.care_plan_id,
            partner_facility_id=pf.id,
            clinic=s.clinic,
            referral_category=p.referral_category,
            requires_clinician_authorisation=p.referral_category != "administrative_transfer",
            authorised_by_clinician_id=s.id,
            authorised_by_role=caller_role,
            reason_and_clinical_summary=p.reason_and_clinical_summary.strip(),
            requested_services_json=json.dumps(p.requested_services),
            status="initiated",
            scheduled_service_date=p.scheduled_service_date,
            contractual_charge_paise=p.contractual_charge_rupees * 100,
            notes=p.notes.strip(),
            created_by=s.id,
        )
        db.add(ref)
        db.flush()
        audit(
            db,
            s,
            "create_hospital_referral",
            "hospital_referral",
            ref.id,
            f"mother={m.id}; partner={pf.name}; category={p.referral_category}",
        )
        db.commit()
        d = row(ref)
        d["mother_name"] = m.name
        d["partner_facility_name"] = pf.name
        d["contractual_charge_rupees"] = round((ref.contractual_charge_paise or 0) / 100, 2)
        return d

    @app.patch("/api/referrals/{ref_id}/status")
    @app.patch("/api/referrals/{ref_id}/transition")
    def update_hospital_referral_status(
        ref_id: str,
        p: ReferralStatusUpdateIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor", "nurse")
        ref = db.get(HospitalReferral, ref_id)
        if not ref or ref.clinic != s.clinic:
            raise HTTPException(404, "Referral not found in your clinic")
        m = mother_for(db, s, ref.mother_id)
        pf = db.get(PartnerFacility, ref.partner_facility_id)

        ts = now()
        ref.status = p.status
        if p.partner_acknowledgement_ref:
            ref.partner_acknowledgement_ref = p.partner_acknowledgement_ref.strip()
            ref.acknowledged_at = ref.acknowledged_at or ts
        if p.scheduled_service_date:
            ref.scheduled_service_date = p.scheduled_service_date
        if p.contractual_charge_rupees is not None:
            ref.contractual_charge_paise = p.contractual_charge_rupees * 100

        if p.status in ("service_completed", "verified_closed"):
            if not p.completion_evidence_ref.strip() and not ref.completion_evidence_ref:
                raise HTTPException(
                    422,
                    "completion_evidence_ref is required when marking a partner referral service as completed/verified",
                )
            if p.completion_evidence_ref.strip():
                ref.completion_evidence_ref = p.completion_evidence_ref.strip()
            ref.service_completed_at = ref.service_completed_at or ts
            if p.status == "verified_closed":
                ref.verified_by = s.id
                ref.verified_at = ts

            # Record contractual diagnostic/hospital charge in Expenses if applicable and not yet recorded
            if ref.contractual_charge_paise > 0 and not ref.expense_id:
                exp = Expense(
                    clinic=s.clinic,
                    category="diagnostics",
                    amount_paise=ref.contractual_charge_paise,
                    description=f"Partner referral service ({pf.name if pf else ref.partner_facility_id}) for {m.name}",
                    receipt_ref=ref.completion_evidence_ref or ref.id,
                    approved=normalize_role(s.role) == "admin",
                    created_by=s.id,
                    approved_by=s.id if normalize_role(s.role) == "admin" else "",
                )
                db.add(exp)
                db.flush()
                ref.expense_id = exp.id

        elif p.status == "cancelled":
            ref.cancellation_reason = p.cancellation_reason.strip() or "Cancelled by staff"

        if p.notes:
            ref.notes = f"{ref.notes}\n{p.notes.strip()}".strip()

        audit(
            db,
            s,
            "referral_status_change",
            "hospital_referral",
            ref.id,
            f"status={p.status}; ack={ref.partner_acknowledgement_ref}",
        )
        db.commit()
        d = row(ref)
        d["contractual_charge_rupees"] = round((ref.contractual_charge_paise or 0) / 100, 2)
        return d

    # =========================================================================
    # 5. EXTENDED TRANSPORT PARTNERS, VEHICLES, DRIVERS & TRIP LIFECYCLE
    # =========================================================================
    @app.get("/api/transport-ops/partners")
    def list_transport_partners(
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        partners = list(
            db.scalars(
                select(TransportPartner)
                .where(TransportPartner.clinic == s.clinic)
                .order_by(TransportPartner.name.asc())
            )
        )
        vehicles_by_partner: dict[str, list[dict[str, Any]]] = {}
        for vd in db.scalars(
            select(TransportVehicleDriver).where(TransportVehicleDriver.clinic == s.clinic)
        ):
            vehicles_by_partner.setdefault(vd.partner_id, []).append(row(vd))

        out: list[dict[str, Any]] = []
        for tp in partners:
            d = row(tp)
            d["base_tariff_rupees"] = round((tp.base_tariff_paise or 0) / 100, 2)
            d["vehicles"] = vehicles_by_partner.get(tp.id, [])
            out.append(d)
        return out

    @app.post("/api/transport-ops/partners")
    def register_transport_partner(
        p: TransportPartnerIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor", "nurse")
        tp = TransportPartner(
            clinic=s.clinic,
            name=p.name.strip(),
            partner_type=p.partner_type,
            contact_person=p.contact_person.strip(),
            contact_phone=p.contact_phone.strip(),
            agreement_ref=p.agreement_ref.strip(),
            effective_until=p.effective_until,
            base_tariff_paise=p.base_tariff_rupees * 100,
            is_active=True,
            disclaimer_note="Scheduled maternal transport coordination only (not live emergency ambulance dispatch).",
            created_by=s.id,
        )
        db.add(tp)
        db.flush()
        audit(
            db,
            s,
            "register_transport_partner",
            "transport_partner",
            tp.id,
            f"name={tp.name}; ref={tp.agreement_ref}",
        )
        db.commit()
        d = row(tp)
        d["base_tariff_rupees"] = p.base_tariff_rupees
        d["vehicles"] = []
        return d

    @app.get("/api/transport-ops/vehicles")
    def list_transport_vehicles(
        partner_id: Optional[str] = Query(default=None),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        stmt = select(TransportVehicleDriver).where(TransportVehicleDriver.clinic == s.clinic)
        if partner_id:
            stmt = stmt.where(TransportVehicleDriver.partner_id == partner_id)
        stmt = stmt.order_by(TransportVehicleDriver.driver_name.asc())
        return [row(v) for v in db.scalars(stmt)]

    @app.post("/api/transport-ops/vehicles")
    def register_transport_vehicle_driver(
        p: VehicleDriverIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor", "nurse", "field_coordinator")
        tp = db.get(TransportPartner, p.partner_id)
        if not tp or tp.clinic != s.clinic:
            raise HTTPException(404, "Transport partner not found in your clinic")

        vd = TransportVehicleDriver(
            partner_id=tp.id,
            clinic=s.clinic,
            driver_name=p.driver_name.strip(),
            driver_phone=p.driver_phone.strip(),
            driving_licence_no=p.driving_licence_no.strip(),
            licence_expiry_date=p.licence_expiry_date,
            vehicle_registration_no=p.vehicle_registration_no.strip(),
            vehicle_type=p.vehicle_type,
            insurance_policy_no=p.insurance_policy_no.strip(),
            insurance_expiry_date=p.insurance_expiry_date,
            credentials_verified=False,
            availability_status="available",
        )
        db.add(vd)
        db.flush()
        audit(
            db,
            s,
            "register_vehicle_driver",
            "transport_vehicle_driver",
            vd.id,
            f"vehicle={vd.vehicle_registration_no}; driver={vd.driver_name}",
        )
        db.commit()
        return row(vd)

    @app.post("/api/transport-ops/vehicles/{vid}/verify")
    def verify_vehicle_driver_documents(
        vid: str,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor")
        vd = db.get(TransportVehicleDriver, vid)
        if not vd or vd.clinic != s.clinic:
            raise HTTPException(404, "Vehicle/driver record not found in your clinic")
        today = date.today()
        if vd.licence_expiry_date < today or vd.insurance_expiry_date < today:
            raise HTTPException(
                400,
                "Cannot verify vehicle/driver with an expired driving licence or expired vehicle insurance policy",
            )
        vd.credentials_verified = True
        vd.verified_by = s.id
        vd.verified_at = now()
        audit(
            db,
            s,
            "verify_vehicle_driver",
            "transport_vehicle_driver",
            vd.id,
            f"licence={vd.driving_licence_no}; insurance={vd.insurance_policy_no}",
        )
        db.commit()
        return row(vd)

    @app.post("/api/transport-ops/trips/{tid}/assign")
    @app.post("/api/transport-ops/trips/{tid}/assign-driver")
    def assign_trip_partner_and_driver(
        tid: str,
        p: TripAssignIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor", "nurse", "field_coordinator")
        tr = db.get(Transport, tid)
        if not tr or tr.clinic != s.clinic:
            raise HTTPException(404, "Transport request not found in your clinic")
        mother_for(db, s, tr.mother_id)

        vd = db.get(TransportVehicleDriver, p.vehicle_driver_id)
        if not vd or vd.clinic != s.clinic:
            raise HTTPException(404, "Vehicle/driver not found in your clinic")
        target_partner_id = p.partner_id or vd.partner_id
        tp = db.get(TransportPartner, target_partner_id)
        if not tp or tp.clinic != s.clinic or not tp.is_active:
            raise HTTPException(404, "Active transport partner not found in your clinic")
        if vd.partner_id != tp.id:
            raise HTTPException(404, "Vehicle/driver does not belong to this transport partner")
        if not vd.credentials_verified:
            raise HTTPException(
                400,
                "Driver licence and vehicle insurance must be verified before trip assignment",
            )
        today = date.today()
        if vd.licence_expiry_date < today or vd.insurance_expiry_date < today:
            raise HTTPException(400, "Vehicle insurance or driver licence has expired")

        if tr.vehicle_driver_id and tr.vehicle_driver_id != vd.id:
            tr.reassigned_from_driver_id = tr.vehicle_driver_id

        tr.partner_id = tp.id
        tr.partner = tp.name
        tr.vehicle_driver_id = vd.id
        tr.status = "assigned"
        tr.driver_response_status = "pending"
        if p.pickup_time:
            tr.pickup_time = p.pickup_time
        if p.fare_rupees is not None:
            tr.trip_expense_paise = p.fare_rupees * 100
        tr.vehicle_notes = f"{vd.vehicle_registration_no} ({vd.driver_name} · {vd.driver_phone})"

        audit(
            db,
            s,
            "assign_transport_driver",
            "transport",
            tr.id,
            f"partner={tp.name}; vehicle={vd.vehicle_registration_no}",
        )
        db.commit()
        return row(tr)

    @app.post("/api/transport-ops/trips/{tid}/driver-response")
    def record_driver_trip_response(
        tid: str,
        p: DriverResponseIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        tr = db.get(Transport, tid)
        if not tr or tr.clinic != s.clinic:
            raise HTTPException(404, "Transport request not found in your clinic")
        mother_for(db, s, tr.mother_id)

        resp_val = p.response or p.decision
        if not resp_val:
            raise HTTPException(422, "response or decision ('accepted' | 'rejected') is required")
        tr.driver_response_status = resp_val
        if resp_val == "rejected":
            tr.driver_rejection_reason = (p.rejection_reason or p.notes or "Driver unavailable").strip()
            tr.status = "requested"
            tr.reassigned_from_driver_id = tr.vehicle_driver_id
            tr.vehicle_driver_id = None
        audit(
            db,
            s,
            "driver_trip_response",
            "transport",
            tr.id,
            f"response={resp_val}; reason={tr.driver_rejection_reason}",
        )
        db.commit()
        return row(tr)

    @app.post("/api/transport-ops/trips/{tid}/lifecycle")
    @app.patch("/api/transport-ops/trips/{tid}/lifecycle")
    def update_trip_lifecycle(
        tid: str,
        p: TripLifecycleIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor", "nurse", "field_coordinator")
        tr = db.get(Transport, tid)
        if not tr or tr.clinic != s.clinic:
            raise HTTPException(404, "Transport trip not found in your clinic")
        m = mother_for(db, s, tr.mother_id)
        ts = now()

        action = p.action
        if not action and p.status:
            status_map = {
                "in_transit": "start_trip",
                "completed": "complete_trip",
                "failed_pickup": "fail_pickup",
                "cancelled": "cancel_trip",
                "reassigned": "reassign_driver",
            }
            action = status_map.get(p.status, p.status)  # type: ignore[assignment]
        if not action:
            raise HTTPException(422, "action or status is required")

        fare_rupees = p.trip_expense_rupees or p.actual_fare_rupees

        if action == "start_trip":
            tr.status = "in_transit"
            tr.driver_response_status = "accepted"
            tr.trip_started_at = ts
            if tr.vehicle_driver_id:
                vd = db.get(TransportVehicleDriver, tr.vehicle_driver_id)
                if vd:
                    vd.availability_status = "on_trip"
        elif action == "complete_trip":
            tr.status = "completed"
            tr.trip_completed_at = ts
            if tr.vehicle_driver_id:
                vd = db.get(TransportVehicleDriver, tr.vehicle_driver_id)
                if vd:
                    vd.availability_status = "available"
            if fare_rupees > 0:
                tr.trip_expense_paise = fare_rupees * 100
                tr.receipt_ref = p.receipt_ref.strip() or f"TRP-RCPT-{tr.id[:6]}"
                if not tr.expense_id:
                    exp = Expense(
                        clinic=s.clinic,
                        category="transport",
                        amount_paise=tr.trip_expense_paise,
                        description=f"Maternal transport trip ({tr.from_location} -> {tr.destination}) for {m.name}",
                        receipt_ref=tr.receipt_ref,
                        approved=normalize_role(s.role) == "admin",
                        created_by=s.id,
                        approved_by=s.id if normalize_role(s.role) == "admin" else "",
                    )
                    db.add(exp)
                    db.flush()
                    tr.expense_id = exp.id
        elif action == "fail_pickup":
            tr.failed_pickup_reason = p.failed_pickup_reason.strip() or "Failed pickup"
            if p.new_vehicle_driver_id:
                new_vd = db.get(TransportVehicleDriver, p.new_vehicle_driver_id)
                if not new_vd or new_vd.clinic != s.clinic or not new_vd.credentials_verified:
                    raise HTTPException(400, "Invalid or unverified replacement driver in your clinic")
                tr.reassigned_from_driver_id = tr.vehicle_driver_id
                tr.vehicle_driver_id = new_vd.id
                tr.partner_id = new_vd.partner_id
                tr.status = "assigned"
                tr.driver_response_status = "accepted"
                tr.vehicle_notes = f"Reassigned to {new_vd.vehicle_registration_no} ({new_vd.driver_name})"
            else:
                tr.status = "requested"
        elif action == "reassign_driver":
            if not p.new_vehicle_driver_id:
                raise HTTPException(422, "new_vehicle_driver_id is required for reassign_driver")
            new_vd = db.get(TransportVehicleDriver, p.new_vehicle_driver_id)
            if not new_vd or new_vd.clinic != s.clinic or not new_vd.credentials_verified:
                raise HTTPException(400, "Invalid or unverified replacement driver in your clinic")
            tr.reassigned_from_driver_id = tr.vehicle_driver_id
            tr.vehicle_driver_id = new_vd.id
            tr.partner_id = new_vd.partner_id
            tr.status = "assigned"
            tr.driver_response_status = "pending"
            tr.vehicle_notes = f"Reassigned to {new_vd.vehicle_registration_no} ({new_vd.driver_name})"
        elif action == "cancel_trip":
            if not p.cancellation_reason.strip():
                raise HTTPException(422, "cancellation_reason is required when cancelling a trip")
            tr.status = "cancelled"
            tr.cancelled_at = ts
            tr.cancellation_reason = p.cancellation_reason.strip()

        if p.vehicle_notes.strip():
            tr.vehicle_notes = p.vehicle_notes.strip()

        audit(
            db,
            s,
            f"transport_{action}",
            "transport",
            tr.id,
            f"status={tr.status}; expense_paise={tr.trip_expense_paise}",
        )
        db.commit()
        d = row(tr)
        d["trip_expense_rupees"] = round((tr.trip_expense_paise or 0) / 100, 2)
        return d

    # =========================================================================
    # 6. OPERATIONS CENTRE DASHBOARD & CLINICAL/ORGANISATIONAL GOVERNANCE
    # =========================================================================
    @app.get("/api/operations/dashboard")
    def get_operations_centre_dashboard(
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        today = date.today()
        soon_cutoff = today + timedelta(days=30)

        staff_rows = list(db.scalars(select(Staff).where(Staff.clinic == s.clinic)))
        staff_map = {st.id: st for st in staff_rows}
        profiles = {st.id: _ensure_workforce_profile(db, st) for st in staff_rows}

        # 1. Staff currently assigned to shifts today
        shifts_today = list(
            db.scalars(
                select(StaffShift).where(
                    StaffShift.clinic == s.clinic,
                    StaffShift.shift_date == today,
                    StaffShift.status.in_(("scheduled", "checked_in", "completed")),
                )
            )
        )
        # 2. Today's scheduled field visits
        visits_all = list(db.scalars(select(FieldVisit).where(FieldVisit.clinic == s.clinic)))
        visits_today = [v for v in visits_all if v.visit_date == today]

        # 3. Service requests
        services_all = list(
            db.scalars(select(ServiceRequest).where(ServiceRequest.clinic == s.clinic))
        )
        unassigned_services = [
            srv
            for srv in services_all
            if not srv.assigned_staff_id
            or srv.status in ("service_requested", "reassignment_required", "unavailable_personnel")
        ]

        # 4. Hospital referrals
        referrals_all = list(
            db.scalars(select(HospitalReferral).where(HospitalReferral.clinic == s.clinic))
        )
        pending_referrals = [
            r
            for r in referrals_all
            if r.status in ("initiated", "sent_to_partner", "acknowledged_by_partner", "appointment_booked")
        ]

        # 5. Transport requests
        transports_all = list(
            db.scalars(select(Transport).where(Transport.clinic == s.clinic))
        )
        pending_transports = [
            t for t in transports_all if t.status in ("requested", "assigned", "in_transit")
        ]

        # 6. Completed and failed counts
        completed_services_count = sum(
            1 for srv in services_all if srv.status in ("completed", "verified", "closed")
        )
        failed_services_count = sum(
            1 for srv in services_all if srv.status in ("failed_visit", "no_show", "cancelled")
        )
        completed_visits_count = sum(1 for v in visits_all if v.status == "completed")
        failed_visits_count = sum(1 for v in visits_all if v.status == "failed_visit")
        completed_trips_count = sum(1 for t in transports_all if t.status == "completed")
        failed_trips_count = sum(
            1 for t in transports_all if bool(t.failed_pickup_reason) or t.status == "cancelled"
        )

        # 7. Staff workload & staffing gaps
        workload_list: list[dict[str, Any]] = []
        active_by_role = {"doctor": 0, "nurse": 0, "field_coordinator": 0, "admin": 0}
        for st in staff_rows:
            nr = normalize_role(st.role)
            if st.is_active:
                active_by_role[nr] = active_by_role.get(nr, 0) + 1
            prof = profiles[st.id]
            st_visits = [v for v in visits_all if v.assigned_staff_id == st.id]
            st_services = [srv for srv in services_all if srv.assigned_staff_id == st.id]
            st_shifts = [sh for sh in shifts_today if sh.staff_id == st.id]
            active_srv_cnt = sum(
                1
                for srv in st_services
                if srv.status in ("staff_assigned", "scheduled", "in_progress")
            )
            visits_today_cnt = sum(1 for v in st_visits if v.visit_date == today)
            workload_list.append(
                {
                    "staff_id": st.id,
                    "name": st.name,
                    "staff_name": st.name,
                    "role": nr,
                    "clinical_role": nr,
                    "is_active": st.is_active,
                    "employment_type": prof.employment_type,
                    "onboarding_status": prof.onboarding_status,
                    "credential_verification_status": prof.credential_verification_status,
                    "assigned_facility": prof.assigned_facility,
                    "shifts_today": len(st_shifts),
                    "visits_today": visits_today_cnt,
                    "total_field_visits": len(st_visits),
                    "completed_field_visits": sum(1 for v in st_visits if v.status == "completed"),
                    "active_service_requests": active_srv_cnt,
                    "active_services": active_srv_cnt,
                    "open_tasks": 0,
                }
            )

        staffing_gaps: list[str] = []
        if active_by_role["doctor"] == 0:
            staffing_gaps.append("No active Medical Officer (Doctor) onboarded in clinic")
        if active_by_role["nurse"] == 0:
            staffing_gaps.append("No active ANM / Staff Nurse onboarded in clinic")
        if active_by_role["field_coordinator"] == 0:
            staffing_gaps.append("No active Field Coordinator onboarded in clinic")
        if len(unassigned_services) > 0:
            staffing_gaps.append(
                f"{len(unassigned_services)} service request(s) awaiting staff assignment"
            )

        # 8. Governance alerts: expiring credentials & partner contracts
        expiring_credentials: list[dict[str, Any]] = []
        for st_id, prof in profiles.items():
            if prof.credential_expiry_date and prof.credential_expiry_date <= soon_cutoff:
                st_obj = staff_map.get(st_id)
                expiring_credentials.append(
                    {
                        "staff_id": st_id,
                        "staff_name": st_obj.name if st_obj else st_id,
                        "expiry_date": prof.credential_expiry_date.isoformat(),
                        "expired": prof.credential_expiry_date < today,
                    }
                )

        partners_all = list(
            db.scalars(select(PartnerFacility).where(PartnerFacility.clinic == s.clinic))
        )
        expiring_contracts: list[dict[str, Any]] = []
        for pf in partners_all:
            if pf.effective_until and pf.effective_until <= soon_cutoff:
                expiring_contracts.append(
                    {
                        "partner_id": pf.id,
                        "partner_name": pf.name,
                        "effective_until": pf.effective_until.isoformat(),
                        "expired": pf.effective_until < today,
                    }
                )

        # 9. Operational expense summary
        expenses_all = list(db.scalars(select(Expense).where(Expense.clinic == s.clinic)))
        total_paise = sum(e.amount_paise for e in expenses_all)
        approved_paise = sum(e.amount_paise for e in expenses_all if e.approved)
        by_category_rupees: dict[str, float] = {}
        for e in expenses_all:
            by_category_rupees[e.category] = round(
                by_category_rupees.get(e.category, 0.0) + (e.amount_paise / 100.0), 2
            )

        open_incidents = (
            db.scalar(
                select(func.count(GovernanceIncident.id)).where(
                    GovernanceIncident.clinic == s.clinic,
                    GovernanceIncident.status != "resolved",
                )
            )
            or 0
        )

        unverified_creds_count = sum(
            1 for p_obj in profiles.values() if p_obj.credential_verification_status != "verified"
        )

        db.commit()
        return {
            "clinic": s.clinic,
            "as_of_date": today.isoformat(),
            "summary": {
                "staff_on_duty_today": len(shifts_today),
                "field_visits_today": len(visits_today),
                "unassigned_service_requests": len(unassigned_services),
                "pending_hospital_referrals": len(pending_referrals),
                "pending_transport_pickups": len(pending_transports),
                "completed_services_count": completed_services_count,
                "failed_or_missed_services_count": failed_services_count + failed_visits_count,
            },
            "shifts_today_count": len(shifts_today),
            "shifts_today": [
                {
                    **row(sh),
                    "staff_name": staff_map[sh.staff_id].name
                    if sh.staff_id in staff_map
                    else sh.staff_id,
                }
                for sh in shifts_today
            ],
            "field_visits_today_count": len(visits_today),
            "field_visits_today": [row(v) for v in visits_today],
            "unassigned_service_requests_count": len(unassigned_services),
            "unassigned_service_requests": [row(srv) for srv in unassigned_services],
            "pending_hospital_referrals_count": len(pending_referrals),
            "pending_hospital_referrals": [row(r) for r in pending_referrals],
            "pending_transport_requests_count": len(pending_transports),
            "pending_transport_requests": [row(t) for t in pending_transports],
            "service_metrics": {
                "completed_services_count": completed_services_count,
                "failed_services_count": failed_services_count,
                "completed_visits_count": completed_visits_count,
                "failed_visits_count": failed_visits_count,
                "completed_trips_count": completed_trips_count,
                "failed_trips_count": failed_trips_count,
            },
            "staff_workload": workload_list,
            "staffing_gaps": staffing_gaps,
            "governance_alerts": {
                "unverified_staff_credentials_count": unverified_creds_count,
                "expiring_or_expired_credentials_count": len(expiring_credentials),
                "expiring_partner_agreements_count": len(expiring_contracts),
                "open_governance_incidents_count": open_incidents,
                "expiring_credentials": expiring_credentials,
                "expiring_partner_contracts": expiring_contracts,
                "open_incidents_count": open_incidents,
            },
            "expenses_summary": {
                "total_rupees": round(total_paise / 100.0, 2),
                "approved_rupees": round(approved_paise / 100.0, 2),
                "pending_rupees": round((total_paise - approved_paise) / 100.0, 2),
                "by_category_rupees": by_category_rupees,
            },
        }

    # =========================================================================
    # 7. GOVERNANCE INCIDENTS & RECORD CORRECTION AUDIT LOGS
    # =========================================================================
    @app.get("/api/governance/incidents")
    def list_governance_incidents(
        status: Optional[str] = Query(default=None),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        stmt = select(GovernanceIncident).where(GovernanceIncident.clinic == s.clinic)
        if status:
            stmt = stmt.where(GovernanceIncident.status == status)
        stmt = stmt.order_by(GovernanceIncident.created_at.desc())
        return [row(inc) for inc in db.scalars(stmt)]

    @app.post("/api/governance/incidents")
    def report_governance_incident(
        p: GovernanceIncidentIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        inc = GovernanceIncident(
            clinic=s.clinic,
            incident_type=p.incident_type,
            severity=p.severity,
            entity_type=p.entity_type.strip(),
            entity_id=p.entity_id.strip(),
            title=p.title.strip(),
            description=p.description.strip(),
            status="open",
            reported_by=s.id,
            assigned_reviewer_id=p.assigned_reviewer_id,
        )
        db.add(inc)
        db.flush()
        audit(
            db,
            s,
            "report_governance_incident",
            "governance_incident",
            inc.id,
            f"type={p.incident_type}; severity={p.severity}; title={p.title}",
        )
        db.commit()
        return row(inc)

    @app.patch("/api/governance/incidents/{inc_id}")
    def update_governance_incident(
        inc_id: str,
        p: GovernanceIncidentUpdateIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor")
        inc = db.get(GovernanceIncident, inc_id)
        if not inc or inc.clinic != s.clinic:
            raise HTTPException(404, "Governance incident not found in your clinic")
        inc.status = p.status
        if p.assigned_reviewer_id is not None:
            inc.assigned_reviewer_id = p.assigned_reviewer_id
        if p.resolution_notes.strip():
            inc.resolution_notes = p.resolution_notes.strip()
        if p.status == "resolved":
            inc.resolved_by = s.id
            inc.resolved_at = now()
        audit(
            db,
            s,
            "update_governance_incident",
            "governance_incident",
            inc.id,
            f"status={p.status}",
        )
        db.commit()
        return row(inc)

    @app.get("/api/governance/corrections")
    def list_record_corrections(
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        permitted(s, "admin", "doctor", "nurse")
        return [
            row(rc)
            for rc in db.scalars(
                select(RecordCorrectionLog)
                .where(RecordCorrectionLog.clinic == s.clinic)
                .order_by(RecordCorrectionLog.created_at.desc())
            )
        ]

    @app.post("/api/governance/corrections")
    def apply_audited_record_correction(
        p: RecordCorrectionIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor")
        old_val: Optional[str] = None
        if p.entity_type == "mother":
            m = mother_for(db, s, p.entity_id)
            if p.field_name not in ("name", "phone", "address", "patient_identifier", "notes"):
                raise HTTPException(400, f"Field '{p.field_name}' cannot be corrected via this endpoint")
            old_val = str(getattr(m, p.field_name) or "")
            setattr(m, p.field_name, p.new_value.strip())
        elif p.entity_type == "field_visit":
            fv = db.get(FieldVisit, p.entity_id)
            if not fv or fv.clinic != s.clinic:
                raise HTTPException(404, "Field visit not found in your clinic")
            if p.field_name not in ("role_scoped_notes", "visit_address", "scheduled_window"):
                raise HTTPException(400, f"Field '{p.field_name}' cannot be corrected")
            old_val = str(getattr(fv, p.field_name) or "")
            setattr(fv, p.field_name, p.new_value.strip())
        elif p.entity_type == "service_request":
            srv = db.get(ServiceRequest, p.entity_id)
            if not srv or srv.clinic != s.clinic:
                raise HTTPException(404, "Service request not found in your clinic")
            if p.field_name not in ("notes", "scheduled_time"):
                raise HTTPException(400, f"Field '{p.field_name}' cannot be corrected")
            old_val = str(getattr(srv, p.field_name) or "")
            setattr(srv, p.field_name, p.new_value.strip())
        else:
            tr = db.get(Transport, p.entity_id)
            if not tr or tr.clinic != s.clinic:
                raise HTTPException(404, "Transport record not found in your clinic")
            if p.field_name not in ("from_location", "destination", "pickup_time", "vehicle_notes"):
                raise HTTPException(400, f"Field '{p.field_name}' cannot be corrected")
            old_val = str(getattr(tr, p.field_name) or "")
            setattr(tr, p.field_name, p.new_value.strip())

        rc = RecordCorrectionLog(
            clinic=s.clinic,
            entity_type=p.entity_type,
            entity_id=p.entity_id,
            field_name=p.field_name,
            old_value=old_val,
            new_value=p.new_value.strip(),
            correction_reason=p.correction_reason.strip(),
            requested_by=s.id,
            approved_by=s.id,
            approved_by_role=normalize_role(s.role),
        )
        db.add(rc)
        db.flush()
        audit(
            db,
            s,
            "record_correction",
            p.entity_type,
            p.entity_id,
            f"field={p.field_name}; old={old_val} -> new={p.new_value}; reason={p.correction_reason}",
        )
        db.commit()
        return row(rc)

    # =========================================================================
    # 8. END-TO-END 10-STEP DEMONSTRATION SCENARIO RUNNER (SECTION 11)
    # =========================================================================
    @app.post("/api/operations/demo-walkthrough")
    def run_end_to_end_phase5_walkthrough(
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        """Execute all 10 steps of the Phase 5 End-to-End Scenario against real persisted records."""
        permitted(s, "admin", "doctor")
        from app.main import _ingest_document_and_run_ocr

        clinic = s.clinic
        today = date.today()
        visit_dt = today + timedelta(days=5)

        # Ensure we have a verified doctor and a verified nurse in this clinic
        doc_staff = db.scalar(
            select(Staff).where(Staff.clinic == clinic, Staff.role == "doctor", Staff.is_active.is_(True))
        )
        if not doc_staff:
            doc_staff = Staff(
                name="Dr. Madhavi Latha (MO OBGYN)",
                email=f"mo.walkthrough@{clinic}.org",
                role="doctor",
                clinic=clinic,
                phone="9848022001",
                password_hash=hash_password("Janani@2026"),
                is_active=True,
            )
            db.add(doc_staff)
            db.flush()
        doc_prof = _ensure_workforce_profile(db, doc_staff)
        doc_prof.credential_verification_status = "verified"
        doc_prof.registration_number = "TSMC-OBG-44102"
        doc_prof.credential_verified_by = s.id
        doc_prof.credential_verified_at = now()

        nurse_staff = db.scalar(
            select(Staff).where(Staff.clinic == clinic, Staff.role == "nurse", Staff.is_active.is_(True))
        )
        if not nurse_staff:
            nurse_staff = Staff(
                name="Sujatha Devi (Registered ANM Nurse)",
                email=f"anm.walkthrough@{clinic}.org",
                role="nurse",
                clinic=clinic,
                phone="9848022002",
                password_hash=hash_password("Janani@2026"),
                is_active=True,
            )
            db.add(nurse_staff)
            db.flush()
        nurse_prof = _ensure_workforce_profile(db, nurse_staff)
        nurse_prof.credential_verification_status = "verified"
        nurse_prof.registration_number = "TSNC-ANM-99201"
        nurse_prof.credential_verified_by = s.id
        nurse_prof.credential_verified_at = now()

        # Step 1: Register a maternal-care patient
        mother = Mother(
            name="Kalyani Goud (E2E Walkthrough)",
            phone="9848055101",
            patient_identifier="ANC-2026-E2E-501",
            age=25,
            lmp=date(2026, 4, 15),
            edd=date(2027, 1, 20),
            address="Ward 7 Miryalaguda Cluster",
            language="te",
            consent=True,
            consent_updated_at=now(),
            notes="Registered during 10-step E2E Phase 5 operational walkthrough.",
            clinic=clinic,
            registered_by=s.id,
        )
        db.add(mother)
        db.flush()

        # Step 2: Upload and human-verify an ANC card
        raw_png = generate_fixture_image_bytes("printed_clear")
        doc_payload = _ingest_document_and_run_ocr(
            db=db,
            s=s,
            m=mother,
            filename="e2e_anc_card.png",
            content_type="image/png",
            contents=raw_png,
        )
        doc_obj = db.get(Document, doc_payload["id"])
        for ef in db.scalars(select(ExtractedField).where(ExtractedField.document_id == doc_obj.id)):
            cand = ef.normalized_value or ef.extracted_value
            if cand:
                ef.verification_status = "accepted"
                ef.final_value = cand
                ef.verified_by = nurse_staff.id
                ef.verified_at = now()
        doc_obj.confirmed = True
        doc_obj.review_status = "confirmed"
        doc_obj.confirmed_by = nurse_staff.id
        doc_obj.confirmed_at = now()
        db.flush()

        # Step 3: Create a doctor-approved appointment (CarePlan)
        plan = CarePlan(
            mother_id=mother.id,
            clinic=clinic,
            visit_date=visit_dt,
            visit_type="anc_checkup",
            appointment_status="scheduled",
            followup_state="scheduled",
            note="Doctor-authorised 3rd trimester ANC checkup & ultrasound review.",
            version=1,
            approved_by=doc_staff.id,
            active=True,
        )
        db.add(plan)
        db.flush()

        # Step 4: Schedule and dispatch a simulated reminder
        sched_jobs = schedule_reminders_for_care_plan(
            db, plan, mother, actor_id=doc_staff.id, actor_role="doctor"
        )
        worker_res = process_outbox_and_due_jobs(db, clinic=clinic, force_due=True)

        # Step 5: Assign a registered nurse to a follow-up service request & field visit
        srv = ServiceRequest(
            mother_id=mother.id,
            care_plan_id=plan.id,
            clinic=clinic,
            service_type="anc_home_visit",
            requires_clinical_qualification=True,
            priority="high",
            status="scheduled",
            assigned_staff_id=nurse_staff.id,
            assigned_staff_role="nurse",
            scheduled_date=today,
            scheduled_time="10:30",
            clinical_authorisation_by=doc_staff.id,
            notes="Pre-visit home check and MCP card readiness verification.",
            created_by=doc_staff.id,
        )
        db.add(srv)
        db.flush()

        # Step 6: Schedule the field visit, start it, and record completion with evidence
        fv = FieldVisit(
            service_request_id=srv.id,
            mother_id=mother.id,
            care_plan_id=plan.id,
            clinic=clinic,
            assigned_staff_id=nurse_staff.id,
            staff_role="nurse",
            visit_date=today,
            scheduled_window="10:00-11:30",
            visit_address=mother.address,
            status="completed",
            contact_confirmed=True,
            patient_consent_verified=True,
            location_consent_granted=True,
            checkin_latitude=17.0576,
            checkin_longitude=79.2684,
            location_purpose="Home visit attendance verification",
            started_at=now(),
            completed_at=now(),
            role_scoped_notes="Mother counselled on upcoming ANC visit and transport pickup.",
            clinical_observations_by_clinician="General wellbeing verified by ANM nurse; referred for scheduled obstetric ultrasound.",
            completion_evidence_type="signed_mcp_card_ack",
            completion_evidence_ref="MCP-ACK-2026-501",
            verified_by=doc_staff.id,
            verified_at=now(),
            created_by=nurse_staff.id,
        )
        db.add(fv)
        srv.status = "verified"
        srv.started_at = fv.started_at
        srv.completed_at = fv.completed_at
        srv.verified_by = doc_staff.id
        srv.verified_at = now()
        srv.completion_evidence = "signed_mcp_card_ack:MCP-ACK-2026-501"
        db.flush()

        # Step 7: Create a clinician-authorised referral to a partner hospital
        partner_hosp = PartnerFacility(
            clinic=clinic,
            name="District Area Maternal & Diagnostic Hospital",
            facility_type="referral_hospital",
            contact_person="Dr. R. Srinivas (Medical Superintendent)",
            contact_phone="9848077001",
            address="District Headquarters Road",
            services_offered_json=json.dumps(["High-Risk Obstetrics", "Anomaly Ultrasound", "Blood Bank"]),
            agreement_reference="MOU-DMHO-2026-108",
            effective_from=today - timedelta(days=90),
            effective_until=today + timedelta(days=275),
            contract_status="active",
            schedule_charges_json=json.dumps({"obstetric_ultrasound_paise": 45000}),
            is_verified_partner=True,
            created_by=s.id,
        )
        db.add(partner_hosp)
        db.flush()

        referral = HospitalReferral(
            mother_id=mother.id,
            care_plan_id=plan.id,
            partner_facility_id=partner_hosp.id,
            clinic=clinic,
            referral_category="clinical_obstetric",
            requires_clinician_authorisation=True,
            authorised_by_clinician_id=doc_staff.id,
            authorised_by_role="doctor",
            reason_and_clinical_summary="3rd-trimester growth scan and obstetric specialist consultation.",
            requested_services_json=json.dumps(["Obstetric Ultrasound", "Specialist Review"]),
            status="verified_closed",
            partner_acknowledgement_ref="HOSP-ACK-2026-771",
            acknowledged_at=now(),
            scheduled_service_date=visit_dt,
            service_completed_at=now(),
            completion_evidence_ref="USG-REPORT-VERIFIED-771",
            verified_by=doc_staff.id,
            verified_at=now(),
            contractual_charge_paise=45000,
            created_by=doc_staff.id,
        )
        db.add(referral)
        db.flush()

        # Step 8 & 9: Arrange a transport request through a verified transport partner and complete trip + service
        tp = TransportPartner(
            clinic=clinic,
            name="Janani Suraksha Community Transport Partner",
            partner_type="community_van_contract",
            contact_person="Venkatesh Goud",
            contact_phone="9848088001",
            agreement_ref="TP-AGR-2026-09",
            effective_until=today + timedelta(days=300),
            base_tariff_paise=55000,
            is_active=True,
            created_by=s.id,
        )
        db.add(tp)
        db.flush()

        vd = TransportVehicleDriver(
            partner_id=tp.id,
            clinic=clinic,
            driver_name="Narasimha Rao",
            driver_phone="9848088002",
            driving_licence_no="TS05-DL-2018-99281",
            licence_expiry_date=today + timedelta(days=400),
            vehicle_registration_no="TS-05-UA-4412",
            vehicle_type="patient_transport_van",
            insurance_policy_no="INS-ORIENT-2026-8812",
            insurance_expiry_date=today + timedelta(days=250),
            credentials_verified=True,
            verified_by=s.id,
            verified_at=now(),
            availability_status="available",
        )
        db.add(vd)
        db.flush()

        trip_exp = Expense(
            clinic=clinic,
            category="transport",
            amount_paise=55000,
            description=f"Completed maternal transport trip for {mother.name} to {partner_hosp.name}",
            receipt_ref="TRP-E2E-RCPT-501",
            approved=True,
            created_by=s.id,
            approved_by=s.id,
        )
        db.add(trip_exp)
        db.flush()

        trip = Transport(
            mother_id=mother.id,
            clinic=clinic,
            date=visit_dt,
            pickup_time="08:30",
            from_location=mother.address,
            destination=partner_hosp.name,
            status="completed",
            partner=tp.name,
            partner_id=tp.id,
            vehicle_driver_id=vd.id,
            service_request_id=srv.id,
            referral_id=referral.id,
            driver_response_status="accepted",
            trip_started_at=now(),
            trip_completed_at=now(),
            trip_expense_paise=55000,
            receipt_ref="TRP-E2E-RCPT-501",
            expense_id=trip_exp.id,
            vehicle_notes=f"{vd.vehicle_registration_no} ({vd.driver_name})",
            requested_by=nurse_staff.id,
        )
        db.add(trip)
        srv.status = "closed"
        srv.closed_at = now()
        db.flush()

        audit(
            db,
            s,
            "run_e2e_phase5_walkthrough",
            "mother",
            mother.id,
            f"plan={plan.id}; visit={fv.id}; referral={referral.id}; trip={trip.id}",
        )
        db.commit()

        # Step 10: Generate auditable operational summary
        ops_summary = get_operations_centre_dashboard(db=db, s=s)
        steps_completed = [
            {
                "step": 1,
                "name": "Register Maternal Patient",
                "entity_id": mother.id,
                "detail": f"{mother.name} (Consent={mother.consent})",
            },
            {
                "step": 2,
                "name": "Upload & Human-Verify ANC Card",
                "entity_id": doc_obj.id,
                "detail": f"Confirmed by {nurse_staff.name} ({doc_obj.ocr_engine})",
            },
            {
                "step": 3,
                "name": "Doctor-Approved Care Plan",
                "entity_id": plan.id,
                "detail": f"Visit date {plan.visit_date} approved by {doc_staff.name}",
            },
            {
                "step": 4,
                "name": "Schedule & Dispatch Reminder",
                "entity_id": plan.id,
                "detail": f"{len(sched_jobs)} jobs scheduled & dispatched via outbox",
            },
            {
                "step": 5,
                "name": "Assign Registered Nurse to Service",
                "entity_id": srv.id,
                "detail": f"Assigned to {nurse_staff.name} (Reg {nurse_prof.registration_number})",
            },
            {
                "step": 6,
                "name": "Schedule & Complete Field Visit",
                "entity_id": fv.id,
                "detail": f"Evidence: {fv.completion_evidence_ref}",
            },
            {
                "step": 7,
                "name": "Clinician-Authorised Partner Referral",
                "entity_id": referral.id,
                "detail": f"Referred to {partner_hosp.name}",
            },
            {
                "step": 8,
                "name": "Arrange Verified Partner Transport",
                "entity_id": trip.id,
                "detail": f"Driver {vd.driver_name} ({vd.vehicle_registration_no})",
            },
            {
                "step": 9,
                "name": "Complete Trip & Record Expense",
                "entity_id": trip_exp.id,
                "detail": f"Receipt {trip.receipt_ref} (₹550)",
            },
            {
                "step": 10,
                "name": "Auditable Operations Summary",
                "entity_id": clinic,
                "detail": f"Completed services: {ops_summary['service_metrics']['completed_services_count']}",
            },
        ]
        return {
            "walkthrough_status": "completed_all_10_steps",
            "clinic": clinic,
            "steps_completed": steps_completed,
            "step_1_mother": row(mother),
            "step_2_verified_anc_document": {
                "id": doc_obj.id,
                "confirmed": doc_obj.confirmed,
                "confirmed_by": doc_obj.confirmed_by,
                "ocr_engine": doc_obj.ocr_engine,
            },
            "step_3_doctor_approved_care_plan": row(plan),
            "step_4_reminders_scheduled_and_dispatched": {
                "scheduled_jobs": len(sched_jobs),
                "worker_result": worker_res,
            },
            "step_5_and_6_nurse_service_and_field_visit": {
                "service_request": row(srv),
                "field_visit": row(fv),
            },
            "step_7_clinician_authorised_hospital_referral": {
                "partner_facility": row(partner_hosp),
                "referral": row(referral),
            },
            "step_8_and_9_transport_and_expense_completion": {
                "transport_partner": row(tp),
                "vehicle_driver": row(vd),
                "completed_trip": row(trip),
                "recorded_expense": row(trip_exp),
            },
            "step_10_operations_summary": ops_summary,
        }
