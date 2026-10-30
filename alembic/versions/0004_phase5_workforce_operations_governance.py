"""Phase 5: Healthcare workforce, patient service coordination, field visits, hospital partnerships,
transport operations, and clinical/organisational governance.

Revision ID: 0004_phase5_workforce_operations_governance
Revises: 0003_phase4_followup_and_messaging
Create Date: 2026-10-29 18:00:00
"""
from __future__ import annotations

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0004_phase5_workforce_operations_governance"
down_revision: Union[str, None] = "0003_phase4_followup_and_messaging"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(inspector, table_name: str, col_name: str) -> bool:
    return any(c["name"] == col_name for c in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "transport" in existing_tables:
        tr_cols = [
            ("service_request_id", sa.Column("service_request_id", sa.String(36), nullable=True)),
            ("referral_id", sa.Column("referral_id", sa.String(36), nullable=True)),
            ("partner_id", sa.Column("partner_id", sa.String(36), nullable=True)),
            ("vehicle_driver_id", sa.Column("vehicle_driver_id", sa.String(36), nullable=True)),
            ("driver_response_status", sa.Column("driver_response_status", sa.String(40), server_default="pending")),
            ("driver_rejection_reason", sa.Column("driver_rejection_reason", sa.String(200), server_default="")),
            ("trip_started_at", sa.Column("trip_started_at", sa.DateTime(timezone=True), nullable=True)),
            ("trip_completed_at", sa.Column("trip_completed_at", sa.DateTime(timezone=True), nullable=True)),
            ("cancelled_at", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True)),
            ("cancellation_reason", sa.Column("cancellation_reason", sa.String(200), server_default="")),
            ("failed_pickup_reason", sa.Column("failed_pickup_reason", sa.String(200), server_default="")),
            ("reassigned_from_driver_id", sa.Column("reassigned_from_driver_id", sa.String(36), nullable=True)),
            ("trip_expense_paise", sa.Column("trip_expense_paise", sa.Integer(), server_default="0")),
            ("receipt_ref", sa.Column("receipt_ref", sa.String(120), server_default="")),
            ("expense_id", sa.Column("expense_id", sa.String(36), nullable=True)),
        ]
        for col_name, col_obj in tr_cols:
            if not _has_column(inspector, "transport", col_name):
                op.add_column("transport", col_obj)

    if "staff_workforce_profiles" not in existing_tables:
        op.create_table(
            "staff_workforce_profiles",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("staff_id", sa.String(36), sa.ForeignKey("staff.id"), unique=True, nullable=False),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("employment_type", sa.String(50), server_default="full_time_employee"),
            sa.Column("onboarding_status", sa.String(40), server_default="active_onboarded"),
            sa.Column("clinical_cadre", sa.String(60), server_default="general"),
            sa.Column("qualification", sa.String(160), server_default=""),
            sa.Column("registration_council", sa.String(140), server_default=""),
            sa.Column("registration_number", sa.String(80), server_default=""),
            sa.Column("credential_verification_status", sa.String(40), server_default="unverified"),
            sa.Column("credential_verified_by", sa.String(36), nullable=True),
            sa.Column("credential_verified_by_role", sa.String(40), server_default=""),
            sa.Column("credential_verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("credential_evidence_ref", sa.String(255), server_default=""),
            sa.Column("credential_expiry_date", sa.Date(), nullable=True),
            sa.Column("assigned_facility", sa.String(160), server_default="PHC Main Facility"),
            sa.Column("availability_days_json", sa.String(160), server_default='["Mon","Tue","Wed","Thu","Fri","Sat"]'),
            sa.Column("shift_preference", sa.String(40), server_default="morning"),
            sa.Column("onboarded_by", sa.String(36), server_default=""),
            sa.Column("onboarded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("offboarded_by", sa.String(36), nullable=True),
            sa.Column("offboarded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("offboarding_reason", sa.Text(), server_default=""),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_staff_workforce_profiles_staff_id", "staff_workforce_profiles", ["staff_id"], unique=True)
        op.create_index("ix_staff_workforce_profiles_clinic", "staff_workforce_profiles", ["clinic"])

    if "staff_credential_documents" not in existing_tables:
        op.create_table(
            "staff_credential_documents",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("staff_id", sa.String(36), sa.ForeignKey("staff.id"), nullable=False),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("document_type", sa.String(60), server_default="medical_council_registration"),
            sa.Column("registration_number", sa.String(80), nullable=False),
            sa.Column("issuing_authority", sa.String(160), nullable=False),
            sa.Column("issued_date", sa.Date(), nullable=True),
            sa.Column("expiry_date", sa.Date(), nullable=True),
            sa.Column("evidence_filename", sa.String(200), server_default="credential_cert.pdf"),
            sa.Column("evidence_notes", sa.Text(), server_default=""),
            sa.Column("verification_status", sa.String(40), server_default="unverified"),
            sa.Column("reviewed_by", sa.String(36), nullable=True),
            sa.Column("reviewed_by_role", sa.String(40), server_default=""),
            sa.Column("review_evidence_note", sa.Text(), server_default=""),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("uploaded_by", sa.String(36), server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_staff_credential_documents_staff_id", "staff_credential_documents", ["staff_id"])
        op.create_index("ix_staff_credential_documents_clinic", "staff_credential_documents", ["clinic"])

    if "staff_shifts" not in existing_tables:
        op.create_table(
            "staff_shifts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("staff_id", sa.String(36), sa.ForeignKey("staff.id"), nullable=False),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("facility_name", sa.String(160), server_default="PHC Main Facility"),
            sa.Column("shift_date", sa.Date(), nullable=False),
            sa.Column("start_time", sa.String(10), server_default="08:00"),
            sa.Column("end_time", sa.String(10), server_default="16:00"),
            sa.Column("shift_type", sa.String(40), server_default="morning"),
            sa.Column("status", sa.String(40), server_default="scheduled"),
            sa.Column("check_in_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("check_out_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("replacement_staff_id", sa.String(36), nullable=True),
            sa.Column("notes", sa.Text(), server_default=""),
            sa.Column("assigned_by", sa.String(36), server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_staff_shifts_staff_date", "staff_shifts", ["staff_id", "shift_date"])
        op.create_index("ix_staff_shifts_clinic_date", "staff_shifts", ["clinic", "shift_date"])

    if "staff_leave_requests" not in existing_tables:
        op.create_table(
            "staff_leave_requests",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("staff_id", sa.String(36), sa.ForeignKey("staff.id"), nullable=False),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column("leave_type", sa.String(40), server_default="casual"),
            sa.Column("reason", sa.Text(), server_default=""),
            sa.Column("status", sa.String(40), server_default="pending"),
            sa.Column("replacement_staff_id", sa.String(36), nullable=True),
            sa.Column("approved_by", sa.String(36), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_staff_leave_requests_staff_id", "staff_leave_requests", ["staff_id"])
        op.create_index("ix_staff_leave_requests_clinic", "staff_leave_requests", ["clinic"])

    if "service_requests" not in existing_tables:
        op.create_table(
            "service_requests",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("mother_id", sa.String(36), sa.ForeignKey("mothers.id"), nullable=False),
            sa.Column("care_plan_id", sa.String(36), nullable=True),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("service_type", sa.String(60), server_default="anc_home_visit"),
            sa.Column("requires_clinical_qualification", sa.Boolean(), server_default="1"),
            sa.Column("priority", sa.String(20), server_default="medium"),
            sa.Column("status", sa.String(40), server_default="service_requested"),
            sa.Column("assigned_staff_id", sa.String(36), nullable=True),
            sa.Column("assigned_staff_role", sa.String(40), server_default=""),
            sa.Column("scheduled_date", sa.Date(), nullable=True),
            sa.Column("scheduled_time", sa.String(20), server_default="10:00"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("verified_by", sa.String(36), nullable=True),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancellation_reason", sa.String(255), server_default=""),
            sa.Column("failure_reason", sa.String(255), server_default=""),
            sa.Column("reassigned_from_staff_id", sa.String(36), nullable=True),
            sa.Column("clinical_authorisation_by", sa.String(36), nullable=True),
            sa.Column("completion_evidence", sa.Text(), server_default=""),
            sa.Column("notes", sa.Text(), server_default=""),
            sa.Column("created_by", sa.String(36), server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_service_requests_clinic", "service_requests", ["clinic"])
        op.create_index("ix_service_requests_mother_id", "service_requests", ["mother_id"])
        op.create_index("ix_service_requests_status", "service_requests", ["status"])

    if "field_visits" not in existing_tables:
        op.create_table(
            "field_visits",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("service_request_id", sa.String(36), nullable=True),
            sa.Column("mother_id", sa.String(36), sa.ForeignKey("mothers.id"), nullable=False),
            sa.Column("care_plan_id", sa.String(36), nullable=True),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("assigned_staff_id", sa.String(36), sa.ForeignKey("staff.id"), nullable=False),
            sa.Column("staff_role", sa.String(40), server_default="nurse"),
            sa.Column("visit_date", sa.Date(), nullable=False),
            sa.Column("scheduled_window", sa.String(40), server_default="09:00-11:00"),
            sa.Column("visit_address", sa.String(255), server_default=""),
            sa.Column("status", sa.String(40), server_default="scheduled"),
            sa.Column("contact_confirmed", sa.Boolean(), server_default="0"),
            sa.Column("patient_consent_verified", sa.Boolean(), server_default="0"),
            sa.Column("location_consent_granted", sa.Boolean(), server_default="0"),
            sa.Column("checkin_latitude", sa.Float(), nullable=True),
            sa.Column("checkin_longitude", sa.Float(), nullable=True),
            sa.Column("location_purpose", sa.String(160), server_default=""),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("role_scoped_notes", sa.Text(), server_default=""),
            sa.Column("clinical_observations_by_clinician", sa.Text(), server_default=""),
            sa.Column("completion_evidence_type", sa.String(60), server_default=""),
            sa.Column("completion_evidence_ref", sa.String(255), server_default=""),
            sa.Column("failed_reason", sa.String(160), server_default=""),
            sa.Column("rescheduled_to_date", sa.Date(), nullable=True),
            sa.Column("offline_draft_id", sa.String(80), nullable=True),
            sa.Column("synced_from_offline", sa.Boolean(), server_default="0"),
            sa.Column("verified_by", sa.String(36), nullable=True),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.String(36), server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_field_visits_clinic_date", "field_visits", ["clinic", "visit_date"])
        op.create_index("ix_field_visits_staff_date", "field_visits", ["assigned_staff_id", "visit_date"])
        op.create_index("ix_field_visits_mother_id", "field_visits", ["mother_id"])

    if "partner_facilities" not in existing_tables:
        op.create_table(
            "partner_facilities",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("facility_type", sa.String(60), server_default="referral_hospital"),
            sa.Column("contact_person", sa.String(120), server_default=""),
            sa.Column("contact_phone", sa.String(24), server_default=""),
            sa.Column("address", sa.String(255), server_default=""),
            sa.Column("services_offered_json", sa.Text(), server_default='["High-Risk Obstetrics","Ultrasound","Complete Blood Count"]'),
            sa.Column("agreement_reference", sa.String(100), server_default=""),
            sa.Column("effective_from", sa.Date(), nullable=False),
            sa.Column("effective_until", sa.Date(), nullable=False),
            sa.Column("contract_status", sa.String(40), server_default="active"),
            sa.Column("schedule_charges_json", sa.Text(), server_default="{}"),
            sa.Column("is_verified_partner", sa.Boolean(), server_default="1"),
            sa.Column("created_by", sa.String(36), server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_partner_facilities_clinic", "partner_facilities", ["clinic"])

    if "hospital_referrals" not in existing_tables:
        op.create_table(
            "hospital_referrals",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("mother_id", sa.String(36), sa.ForeignKey("mothers.id"), nullable=False),
            sa.Column("care_plan_id", sa.String(36), nullable=True),
            sa.Column("partner_facility_id", sa.String(36), sa.ForeignKey("partner_facilities.id"), nullable=False),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("referral_category", sa.String(60), server_default="clinical_obstetric"),
            sa.Column("requires_clinician_authorisation", sa.Boolean(), server_default="1"),
            sa.Column("authorised_by_clinician_id", sa.String(36), nullable=False),
            sa.Column("authorised_by_role", sa.String(40), server_default="doctor"),
            sa.Column("reason_and_clinical_summary", sa.Text(), nullable=False),
            sa.Column("requested_services_json", sa.Text(), server_default="[]"),
            sa.Column("status", sa.String(40), server_default="initiated"),
            sa.Column("partner_acknowledgement_ref", sa.String(120), server_default=""),
            sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("scheduled_service_date", sa.Date(), nullable=True),
            sa.Column("service_completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completion_evidence_ref", sa.String(255), server_default=""),
            sa.Column("verified_by", sa.String(36), nullable=True),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("contractual_charge_paise", sa.Integer(), server_default="0"),
            sa.Column("expense_id", sa.String(36), nullable=True),
            sa.Column("cancellation_reason", sa.String(200), server_default=""),
            sa.Column("notes", sa.Text(), server_default=""),
            sa.Column("created_by", sa.String(36), server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_hospital_referrals_clinic", "hospital_referrals", ["clinic"])
        op.create_index("ix_hospital_referrals_mother_id", "hospital_referrals", ["mother_id"])
        op.create_index("ix_hospital_referrals_partner_id", "hospital_referrals", ["partner_facility_id"])

    if "transport_partners" not in existing_tables:
        op.create_table(
            "transport_partners",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("partner_type", sa.String(60), server_default="community_van_contract"),
            sa.Column("contact_person", sa.String(120), server_default=""),
            sa.Column("contact_phone", sa.String(24), server_default=""),
            sa.Column("agreement_ref", sa.String(100), server_default=""),
            sa.Column("effective_until", sa.Date(), nullable=False),
            sa.Column("base_tariff_paise", sa.Integer(), server_default="50000"),
            sa.Column("is_active", sa.Boolean(), server_default="1"),
            sa.Column(
                "disclaimer_note",
                sa.String(255),
                server_default="Scheduled maternal transport coordination only (not live emergency ambulance dispatch).",
            ),
            sa.Column("created_by", sa.String(36), server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_transport_partners_clinic", "transport_partners", ["clinic"])

    if "transport_vehicles_drivers" not in existing_tables:
        op.create_table(
            "transport_vehicles_drivers",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("partner_id", sa.String(36), sa.ForeignKey("transport_partners.id"), nullable=False),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("driver_name", sa.String(120), nullable=False),
            sa.Column("driver_phone", sa.String(24), nullable=False),
            sa.Column("driving_licence_no", sa.String(80), nullable=False),
            sa.Column("licence_expiry_date", sa.Date(), nullable=False),
            sa.Column("vehicle_registration_no", sa.String(60), nullable=False),
            sa.Column("vehicle_type", sa.String(60), server_default="patient_transport_van"),
            sa.Column("insurance_policy_no", sa.String(80), nullable=False),
            sa.Column("insurance_expiry_date", sa.Date(), nullable=False),
            sa.Column("credentials_verified", sa.Boolean(), server_default="0"),
            sa.Column("verified_by", sa.String(36), nullable=True),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("availability_status", sa.String(40), server_default="available"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_transport_vehicles_drivers_clinic", "transport_vehicles_drivers", ["clinic"])
        op.create_index("ix_transport_vehicles_drivers_partner", "transport_vehicles_drivers", ["partner_id"])

    if "governance_incidents" not in existing_tables:
        op.create_table(
            "governance_incidents",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("incident_type", sa.String(60), server_default="protocol_deviation"),
            sa.Column("severity", sa.String(20), server_default="medium"),
            sa.Column("entity_type", sa.String(60), server_default=""),
            sa.Column("entity_id", sa.String(60), server_default=""),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("status", sa.String(40), server_default="open"),
            sa.Column("reported_by", sa.String(36), nullable=False),
            sa.Column("assigned_reviewer_id", sa.String(36), nullable=True),
            sa.Column("resolution_notes", sa.Text(), server_default=""),
            sa.Column("resolved_by", sa.String(36), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_governance_incidents_clinic", "governance_incidents", ["clinic"])
        op.create_index("ix_governance_incidents_status", "governance_incidents", ["status"])

    if "record_correction_logs" not in existing_tables:
        op.create_table(
            "record_correction_logs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("entity_type", sa.String(60), nullable=False),
            sa.Column("entity_id", sa.String(60), nullable=False),
            sa.Column("field_name", sa.String(80), nullable=False),
            sa.Column("old_value", sa.Text(), nullable=True),
            sa.Column("new_value", sa.Text(), nullable=False),
            sa.Column("correction_reason", sa.Text(), nullable=False),
            sa.Column("requested_by", sa.String(36), nullable=False),
            sa.Column("approved_by", sa.String(36), nullable=False),
            sa.Column("approved_by_role", sa.String(40), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_record_correction_logs_clinic", "record_correction_logs", ["clinic"])
        op.create_index("ix_record_correction_logs_entity", "record_correction_logs", ["entity_type", "entity_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for tbl in [
        "record_correction_logs",
        "governance_incidents",
        "transport_vehicles_drivers",
        "transport_partners",
        "hospital_referrals",
        "partner_facilities",
        "field_visits",
        "service_requests",
        "staff_leave_requests",
        "staff_shifts",
        "staff_credential_documents",
        "staff_workforce_profiles",
    ]:
        if tbl in existing_tables:
            op.drop_table(tbl)

