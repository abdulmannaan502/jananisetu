"""Database engine, session management, transactional schema migration helper, and synthetic seed data."""
from __future__ import annotations

from datetime import date, timedelta
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models import (
    Base,
    BudgetCategoryLine,
    CarePlan,
    ContractMilestone,
    Event,
    Expense,
    ExpensePolicyRule,
    FieldVisit,
    FundingOrganisation,
    HospitalReferral,
    Mother,
    PartnerFacility,
    PayrollStatutoryConfig,
    ProgrammeBudget,
    ProgrammeContract,
    ServiceRequest,
    Staff,
    StaffCompensationAgreement,
    StaffCredentialDocument,
    StaffShift,
    StaffWorkforceProfile,
    Task,
    Transport,
    TransportPartner,
    TransportVehicleDriver,
    now,
)
from app.security import hash_password

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.db_url.startswith("sqlite") else {}
engine = create_engine(settings.db_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def ensure_schema_and_migrate_legacy(target_engine=engine) -> None:
    """Create missing tables and safely add Phase 2/3 columns within a transaction for non-prod databases."""
    Base.metadata.create_all(target_engine)
    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names())

    alterations: dict[str, list[tuple[str, str]]] = {
        "staff": [
            ("email", "VARCHAR(160)"),
            ("password_hash", "VARCHAR(255) DEFAULT ''"),
            ("phone", "VARCHAR(24) DEFAULT ''"),
            ("is_active", "BOOLEAN DEFAULT TRUE"),
            ("token_version", "INTEGER DEFAULT 1"),
            ("created_at", "TIMESTAMP"),
        ],
        "mothers": [
            ("patient_identifier", "VARCHAR(80) DEFAULT ''"),
            ("age", "INTEGER"),
            ("edd", "DATE"),
            ("lmp", "DATE"),
            ("address", "VARCHAR(300) DEFAULT ''"),
            ("consent_updated_at", "TIMESTAMP"),
            ("notes", "TEXT DEFAULT ''"),
            ("registered_by", "VARCHAR(36) DEFAULT ''"),
        ],
        "care_plans": [
            ("clinic", "VARCHAR(80) DEFAULT 'demo-clinic'"),
            ("visit_type", "VARCHAR(50) DEFAULT 'anc_checkup'"),
            ("appointment_status", "VARCHAR(40) DEFAULT 'scheduled'"),
            ("follow_up_notes", "TEXT DEFAULT ''"),
            ("followup_state", "VARCHAR(50) DEFAULT 'scheduled'"),
            ("ack_deadline_at", "TIMESTAMP"),
            ("acknowledged_at", "TIMESTAMP"),
            ("visit_confirmed_at", "TIMESTAMP"),
            ("closed_at", "TIMESTAMP"),
            ("superseded_by_plan_id", "VARCHAR(36)"),
        ],
        "tasks": [
            ("care_plan_id", "VARCHAR(36)"),
            ("clinic", "VARCHAR(80) DEFAULT 'demo-clinic'"),
            ("priority", "VARCHAR(20) DEFAULT 'medium'"),
            ("due_date", "DATE"),
            ("completion_notes", "TEXT DEFAULT ''"),
            ("completed_at", "TIMESTAMP"),
            ("escalated_to", "VARCHAR(36)"),
            ("escalated_at", "TIMESTAMP"),
            ("escalation_reason", "TEXT DEFAULT ''"),
            ("created_by", "VARCHAR(36) DEFAULT ''"),
        ],
        "messages": [
            ("care_plan_id", "VARCHAR(36)"),
            ("reminder_job_id", "VARCHAR(36)"),
            ("clinic", "VARCHAR(80) DEFAULT 'demo-clinic'"),
            ("recipient_type", "VARCHAR(20) DEFAULT 'mother'"),
            ("recipient_phone_masked", "VARCHAR(30) DEFAULT ''"),
            ("template_name", "VARCHAR(80) DEFAULT ''"),
            ("delivery_status_rank", "INTEGER DEFAULT 0"),
            ("provider_message_id", "VARCHAR(120)"),
            ("idempotency_key", "VARCHAR(120)"),
            ("delivered_at", "TIMESTAMP"),
            ("acknowledged_at", "TIMESTAMP"),
            ("failure_code", "VARCHAR(60) DEFAULT ''"),
            ("failure_reason", "TEXT DEFAULT ''"),
            ("flagged_for_clinical_review", "BOOLEAN DEFAULT FALSE"),
            ("clinical_review_status", "VARCHAR(40) DEFAULT 'not_required'"),
            ("clinical_review_note", "TEXT DEFAULT ''"),
            ("reviewed_by", "VARCHAR(36)"),
            ("reviewed_at", "TIMESTAMP"),
        ],
        "transport": [
            ("clinic", "VARCHAR(80) DEFAULT 'demo-clinic'"),
            ("pickup_time", "VARCHAR(20) DEFAULT '09:00'"),
            ("vehicle_notes", "TEXT DEFAULT ''"),
            ("requested_by", "VARCHAR(36) DEFAULT ''"),
            ("created_at", "TIMESTAMP"),
            ("service_request_id", "VARCHAR(36)"),
            ("referral_id", "VARCHAR(36)"),
            ("partner_id", "VARCHAR(36)"),
            ("vehicle_driver_id", "VARCHAR(36)"),
            ("driver_response_status", "VARCHAR(40) DEFAULT 'pending'"),
            ("driver_rejection_reason", "VARCHAR(200) DEFAULT ''"),
            ("trip_started_at", "TIMESTAMP"),
            ("trip_completed_at", "TIMESTAMP"),
            ("cancelled_at", "TIMESTAMP"),
            ("cancellation_reason", "VARCHAR(200) DEFAULT ''"),
            ("failed_pickup_reason", "VARCHAR(200) DEFAULT ''"),
            ("reassigned_from_driver_id", "VARCHAR(36)"),
            ("trip_expense_paise", "INTEGER DEFAULT 0"),
            ("receipt_ref", "VARCHAR(120) DEFAULT ''"),
            ("expense_id", "VARCHAR(36)"),
        ],
        "expenses": [
            ("clinic", "VARCHAR(80) DEFAULT 'demo-clinic'"),
            ("receipt_ref", "VARCHAR(120) DEFAULT ''"),
            ("created_by", "VARCHAR(36) DEFAULT ''"),
            ("approved_by", "VARCHAR(36) DEFAULT ''"),
            ("created_at", "TIMESTAMP"),
            ("contract_id", "VARCHAR(36)"),
            ("budget_id", "VARCHAR(36)"),
            ("expense_claim_id", "VARCHAR(36)"),
            ("payroll_run_id", "VARCHAR(36)"),
            ("funding_claim_id", "VARCHAR(36)"),
            ("reimbursement_status", "VARCHAR(40) DEFAULT 'unclaimed'"),
            ("payment_ref", "VARCHAR(120) DEFAULT ''"),
        ],
        "documents": [
            ("clinic", "VARCHAR(80) DEFAULT 'demo-clinic'"),
            ("version_number", "INTEGER DEFAULT 1"),
            ("supersedes_document_id", "VARCHAR(36)"),
            ("stored_path", "VARCHAR(255) DEFAULT ''"),
            ("preview_path", "VARCHAR(255) DEFAULT ''"),
            ("content_type", "VARCHAR(60) DEFAULT 'image/png'"),
            ("file_size_bytes", "INTEGER DEFAULT 0"),
            ("sha256_hash", "VARCHAR(64) DEFAULT ''"),
            ("image_width", "INTEGER DEFAULT 0"),
            ("image_height", "INTEGER DEFAULT 0"),
            ("page_count", "INTEGER DEFAULT 1"),
            ("ocr_status", "VARCHAR(40) DEFAULT 'completed'"),
            ("ocr_engine", "VARCHAR(60) DEFAULT 'tesseract-5'"),
            ("ocr_error", "TEXT DEFAULT ''"),
            ("structured_fields", "TEXT DEFAULT '{}'"),
            ("review_status", "VARCHAR(40) DEFAULT 'pending_review'"),
            ("uploaded_by", "VARCHAR(36) DEFAULT ''"),
            ("confirmed_by", "VARCHAR(36) DEFAULT ''"),
            ("confirmed_at", "TIMESTAMP"),
            ("created_at", "TIMESTAMP"),
        ],
        "events": [
            ("clinic", "VARCHAR(80) DEFAULT 'demo-clinic'"),
            ("actor_role", "VARCHAR(40) DEFAULT ''"),
        ],
    }

    with target_engine.begin() as conn:
        for table_name, cols in alterations.items():
            if table_name not in existing_tables:
                continue
            existing_col_names = {c["name"] for c in inspector.get_columns(table_name)}
            for col_name, col_def in cols:
                if col_name not in existing_col_names:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"))


def seed_default_accounts_if_empty(db: Session) -> None:
    """Seed synthetic demonstration staff and patients for two clinics if default demo accounts do not exist."""
    if db.get(Staff, "staff-admin-1") is not None:
        _seed_phase5_if_empty(db)
        _seed_phase6_if_empty(db)
        return

    default_pw_hash = hash_password("Janani@2026")
    admin1 = Staff(
        id="staff-admin-1",
        name="Ananya Reddy (Clinic Admin)",
        email="admin@nalgonda.janani.org",
        role="admin",
        clinic="demo-clinic",
        phone="9000000001",
        password_hash=default_pw_hash,
        is_active=True,
    )
    doc1 = Staff(
        id="staff-doc-1",
        name="Dr. Kavitha Rao (MO)",
        email="doctor@nalgonda.janani.org",
        role="doctor",
        clinic="demo-clinic",
        phone="9000000002",
        password_hash=default_pw_hash,
        is_active=True,
    )
    nurse1 = Staff(
        id="staff-nurse-1",
        name="Lakshmi Devi (ANM Nurse)",
        email="nurse@nalgonda.janani.org",
        role="nurse",
        clinic="demo-clinic",
        phone="9000000003",
        password_hash=default_pw_hash,
        is_active=True,
    )
    fc1 = Staff(
        id="staff-fc-1",
        name="Padma Kumari (Field Coordinator)",
        email="coordinator@nalgonda.janani.org",
        role="field_coordinator",
        clinic="demo-clinic",
        phone="9000000004",
        password_hash=default_pw_hash,
        is_active=True,
    )

    admin2 = Staff(
        id="staff-admin-2",
        name="Rajeshwar Rao (Warangal Admin)",
        email="admin@warangal.janani.org",
        role="admin",
        clinic="warangal-clinic",
        phone="9000000011",
        password_hash=default_pw_hash,
        is_active=True,
    )
    doc2 = Staff(
        id="staff-doc-2",
        name="Dr. Sunitha Verma",
        email="doctor@warangal.janani.org",
        role="doctor",
        clinic="warangal-clinic",
        phone="9000000012",
        password_hash=default_pw_hash,
        is_active=True,
    )

    db.add_all([admin1, doc1, nurse1, fc1, admin2, doc2])
    db.flush()

    today = date.today()
    m1 = Mother(
        id="mother-syn-101",
        name="Sravani Goud",
        phone="9800000101",
        patient_identifier="ANC-2026-1042",
        age=24,
        lmp=date(2026, 5, 22),
        edd=date(2027, 2, 26),
        address="Ward 4 Devarakonda",
        language="te",
        consent=True,
        notes="Registered for 2nd trimester administrative follow-up.",
        clinic="demo-clinic",
        registered_by=nurse1.id,
    )
    m2 = Mother(
        id="mother-syn-102",
        name="Meena Begum",
        phone="9800000102",
        patient_identifier="ANC-2026-1088",
        age=27,
        lmp=today - timedelta(days=210),
        edd=today + timedelta(days=70),
        address="Miryalaguda Sector B",
        language="hi",
        consent=True,
        notes="Requires transport coordination for upcoming ANC visit.",
        clinic="demo-clinic",
        registered_by=nurse1.id,
    )
    m3 = Mother(
        id="mother-syn-201",
        name="Bhavani K (Synthetic - Warangal)",
        phone="9800000201",
        patient_identifier="ANC-WGL-2001",
        age=22,
        lmp=today - timedelta(days=120),
        edd=today + timedelta(days=160),
        address="Hanamkonda Cluster",
        language="en",
        consent=True,
        notes="Warangal clinic synthetic record.",
        clinic="warangal-clinic",
        registered_by=admin2.id,
    )
    db.add_all([m1, m2, m3])
    db.flush()

    cp1 = CarePlan(
        id="plan-syn-101",
        mother_id=m1.id,
        clinic="demo-clinic",
        visit_date=today + timedelta(days=5),
        visit_type="anc_checkup",
        appointment_status="scheduled",
        note="Routine ANC visit #3 scheduled by Medical Officer. Bring MCP card.",
        version=1,
        approved_by=doc1.id,
        active=True,
    )
    cp2 = CarePlan(
        id="plan-syn-102",
        mother_id=m2.id,
        clinic="demo-clinic",
        visit_date=today - timedelta(days=2),
        visit_type="follow_up",
        appointment_status="missed",
        note="Scheduled administrative check-in; follow up on transport availability.",
        version=1,
        approved_by=doc1.id,
        active=True,
    )
    db.add_all([cp1, cp2])

    t1 = Task(
        id="task-syn-101",
        mother_id=m2.id,
        clinic="demo-clinic",
        category="missed_visit",
        priority="high",
        due_date=today + timedelta(days=1),
        status="open",
        assigned_to=fc1.id,
        detail="Coordinate home visit to reschedule missed ANC check-in and confirm transport.",
        created_by=nurse1.id,
    )
    t2 = Task(
        id="task-syn-102",
        mother_id=m1.id,
        clinic="demo-clinic",
        category="contact_attempt",
        priority="medium",
        due_date=today + timedelta(days=3),
        status="in_progress",
        assigned_to=fc1.id,
        detail="Confirm reminder receipt for upcoming ANC visit.",
        created_by=nurse1.id,
    )
    db.add_all([t1, t2])

    tr1 = Transport(
        id="trans-syn-101",
        mother_id=m2.id,
        clinic="demo-clinic",
        date=today + timedelta(days=3),
        pickup_time="08:30",
        from_location="Miryalaguda Sector B",
        destination="PHC Nalgonda",
        status="assigned",
        partner="102 Janani Express Partner (Demo)",
        vehicle_notes="Community transport van #TS-05-102",
        requested_by=fc1.id,
    )
    db.add(tr1)

    exp1 = Expense(
        id="exp-syn-101",
        clinic="demo-clinic",
        category="transport",
        amount_paise=85000,
        description="Community transport voucher batch for Miryalaguda sector",
        receipt_ref="VCH-2026-001",
        approved=True,
        created_by=admin1.id,
        approved_by=admin1.id,
    )
    exp2 = Expense(
        id="exp-syn-102",
        clinic="demo-clinic",
        category="travel",
        amount_paise=45000,
        description="Field coordinator village outreach travel allowance",
        receipt_ref="TRV-2026-014",
        approved=False,
        created_by=admin1.id,
    )
    db.add_all([exp1, exp2])

    ev1 = Event(
        clinic="demo-clinic",
        actor=doc1.id,
        actor_role="doctor",
        action="approve_care_plan",
        entity="care_plan",
        entity_id=cp1.id,
        detail="version 1; synthetic demo seed",
    )
    db.add(ev1)

    # Phase 5 Seed Data: Workforce Profiles, Verified Credentials, Shifts, Partner Hospital, Transport Fleet
    ts = now()
    wp_doc = StaffWorkforceProfile(
        id="wp-doc-1",
        staff_id=doc1.id,
        clinic="demo-clinic",
        employment_type="full_time_employee",
        onboarding_status="active_onboarded",
        clinical_cadre="medical_officer_obgyn",
        qualification="MBBS, DGO (Obstetrics & Gynaecology)",
        registration_council="Telangana State Medical Council",
        registration_number="TSMC-OBG-2026-4412",
        credential_verification_status="verified",
        credential_verified_by=admin1.id,
        credential_verified_by_role="admin",
        credential_verified_at=ts,
        credential_evidence_ref="TSMC Registry Certificate #4412",
        credential_expiry_date=today + timedelta(days=365),
        assigned_facility="PHC Nalgonda Central",
        onboarded_by=admin1.id,
    )
    wp_nurse = StaffWorkforceProfile(
        id="wp-nurse-1",
        staff_id=nurse1.id,
        clinic="demo-clinic",
        employment_type="nhm_deputed",
        onboarding_status="active_onboarded",
        clinical_cadre="anm_staff_nurse",
        qualification="ANM / GNM Registered Nurse Midwife",
        registration_council="Telangana Nurses & Midwives Council",
        registration_number="TSNMC-ANM-2026-8819",
        credential_verification_status="verified",
        credential_verified_by=admin1.id,
        credential_verified_by_role="admin",
        credential_verified_at=ts,
        credential_evidence_ref="ANM Council Certificate & NHM Deputation Order",
        credential_expiry_date=today + timedelta(days=180),
        assigned_facility="PHC Nalgonda Sub-Centre B",
        onboarded_by=admin1.id,
    )
    wp_fc = StaffWorkforceProfile(
        id="wp-fc-1",
        staff_id=fc1.id,
        clinic="demo-clinic",
        employment_type="community_honorarium",
        onboarding_status="active_onboarded",
        clinical_cadre="asha_field_coordinator",
        qualification="Non-Clinical Community Care Coordinator",
        registration_council="NHM Community Coordination Cell",
        registration_number="NHM-CC-2026-109",
        credential_verification_status="verified",
        credential_verified_by=admin1.id,
        credential_verified_by_role="admin",
        credential_verified_at=ts,
        credential_evidence_ref="Verified District Field Coordinator ID",
        credential_expiry_date=today + timedelta(days=240),
        assigned_facility="PHC Nalgonda Field Unit",
        onboarded_by=admin1.id,
    )
    db.add_all([wp_doc, wp_nurse, wp_fc])

    cred_doc1 = StaffCredentialDocument(
        id="cred-doc-1",
        staff_id=doc1.id,
        clinic="demo-clinic",
        document_type="medical_council_registration",
        registration_number="TSMC-OBG-2026-4412",
        issuing_authority="Telangana State Medical Council",
        issued_date=today - timedelta(days=730),
        expiry_date=today + timedelta(days=365),
        evidence_filename="TSMC-CERT-2024-4412.pdf",
        evidence_notes="Official State Medical Council Certificate",
        verification_status="verified",
        reviewed_by=admin1.id,
        reviewed_by_role="admin",
        review_evidence_note="Verified against official state medical council register.",
        reviewed_at=ts,
        uploaded_by=doc1.id,
    )
    cred_nurse1 = StaffCredentialDocument(
        id="cred-nurse-1",
        staff_id=nurse1.id,
        clinic="demo-clinic",
        document_type="nursing_license",
        registration_number="TSNMC-ANM-2026-8819",
        issuing_authority="Telangana Nurses & Midwives Council",
        issued_date=today - timedelta(days=500),
        expiry_date=today + timedelta(days=180),
        evidence_filename="TSNMC-ANM-8819.pdf",
        evidence_notes="Original Nursing Council Certificate",
        verification_status="verified",
        reviewed_by=admin1.id,
        reviewed_by_role="admin",
        review_evidence_note="Verified original certificate in clinic HR file.",
        reviewed_at=ts,
        uploaded_by=nurse1.id,
    )
    db.add_all([cred_doc1, cred_nurse1])

    shift1 = StaffShift(
        id="shift-syn-101",
        staff_id=doc1.id,
        clinic="demo-clinic",
        facility_name="PHC Nalgonda OPD",
        shift_date=today,
        start_time="09:00",
        end_time="17:00",
        shift_type="morning",
        status="checked_in",
        check_in_at=ts,
        notes="Morning ANC OPD clinic duty",
        assigned_by=admin1.id,
    )
    shift2 = StaffShift(
        id="shift-syn-102",
        staff_id=nurse1.id,
        clinic="demo-clinic",
        facility_name="Miryalaguda Sector B",
        shift_date=today,
        start_time="09:00",
        end_time="17:00",
        shift_type="field_outreach",
        status="scheduled",
        notes="Scheduled maternal home visits and blood pressure checkups",
        assigned_by=admin1.id,
    )
    db.add_all([shift1, shift2])

    pf1 = PartnerFacility(
        id="partner-hosp-101",
        clinic="demo-clinic",
        name="Nalgonda District Maternal & Diagnostic Centre",
        facility_type="referral_hospital",
        contact_person="Dr. Ramesh Babu (Nodal Officer)",
        contact_phone="9440001122",
        address="Collectorate Road, Nalgonda",
        services_offered_json='["obstetric_ultrasound", "blood_panel", "high_risk_obstetric_review", "inpatient_maternity"]',
        agreement_reference="MOU-JANANI-NLG-2026-01",
        effective_from=today - timedelta(days=180),
        effective_until=today + timedelta(days=185),
        contract_status="active",
        schedule_charges_json='{"obstetric_ultrasound_paise": 80000, "high_risk_obstetric_review_paise": 120000}',
        is_verified_partner=True,
        created_by=admin1.id,
    )
    db.add(pf1)

    tp1 = TransportPartner(
        id="tpartner-101",
        clinic="demo-clinic",
        name="Devarakonda Rural Maternal Mobility Cooperative",
        partner_type="community_van_contract",
        contact_person="Venkatesh Goud",
        contact_phone="9848002233",
        agreement_ref="TRANS-MOU-2026-04",
        effective_until=today + timedelta(days=300),
        base_tariff_paise=45000,
        is_active=True,
        disclaimer_note="Non-emergency scheduled maternal clinic transport only. Dial 108 / 102 for obstetric emergencies.",
        created_by=admin1.id,
    )
    db.add(tp1)
    db.flush()

    tv1 = TransportVehicleDriver(
        id="tdriver-101",
        partner_id=tp1.id,
        clinic="demo-clinic",
        driver_name="Srinivasulu Yadav",
        driver_phone="9848009988",
        driving_licence_no="TS05-20190048821",
        licence_expiry_date=today + timedelta(days=500),
        vehicle_registration_no="TS-05-UC-4499",
        vehicle_type="patient_transport_van",
        insurance_policy_no="UIIC-TS05-2026-88412",
        insurance_expiry_date=today + timedelta(days=210),
        credentials_verified=True,
        verified_by=admin1.id,
        verified_at=ts,
        availability_status="available",
    )
    db.add(tv1)
    db.flush()
    _seed_phase6_if_empty(db)
    db.commit()


def _seed_phase5_if_empty(db: Session) -> None:
    """Ensure Phase 5 default synthetic transport partner and drivers exist."""
    if db.get(TransportPartner, "tpartner-101") is not None:
        return
    admin1 = db.get(Staff, "staff-admin-1")
    doc1 = db.get(Staff, "staff-doc-1")
    nurse1 = db.get(Staff, "staff-nurse-1")
    fc1 = db.get(Staff, "staff-fc-1")
    if not (admin1 and doc1 and nurse1 and fc1):
        return
    today = date.today()
    ts = now()

    if db.scalars(select(StaffWorkforceProfile).where(StaffWorkforceProfile.staff_id == doc1.id)).first() is None:
        wp_doc = StaffWorkforceProfile(
            id="wp-doc-1",
            staff_id=doc1.id,
            clinic="demo-clinic",
            employment_type="full_time_employee",
            onboarding_status="active_onboarded",
            clinical_cadre="medical_officer_obgyn",
            qualification="MBBS, DGO (Obstetrics & Gynaecology)",
            registration_council="Telangana State Medical Council",
            registration_number="TSMC-OBG-2026-4412",
            credential_verification_status="verified",
            credential_verified_by=admin1.id,
            credential_verified_by_role="admin",
            credential_verified_at=ts,
            credential_evidence_ref="TSMC Registry Certificate #4412",
            credential_expiry_date=today + timedelta(days=365),
            assigned_facility="PHC Nalgonda Central",
            onboarded_by=admin1.id,
        )
        db.add(wp_doc)

    if db.scalars(select(StaffWorkforceProfile).where(StaffWorkforceProfile.staff_id == nurse1.id)).first() is None:
        wp_nurse = StaffWorkforceProfile(
            id="wp-nurse-1",
            staff_id=nurse1.id,
            clinic="demo-clinic",
            employment_type="nhm_deputed",
            onboarding_status="active_onboarded",
            clinical_cadre="anm_staff_nurse",
            qualification="ANM / GNM Registered Nurse Midwife",
            registration_council="Telangana Nurses & Midwives Council",
            registration_number="TSNMC-ANM-2026-8819",
            credential_verification_status="verified",
            credential_verified_by=admin1.id,
            credential_verified_by_role="admin",
            credential_verified_at=ts,
            credential_evidence_ref="ANM Council Certificate & NHM Deputation Order",
            credential_expiry_date=today + timedelta(days=180),
            assigned_facility="PHC Nalgonda Sub-Centre B",
            onboarded_by=admin1.id,
        )
        db.add(wp_nurse)

    if db.get(PartnerFacility, "partner-hosp-101") is None:
        pf1 = PartnerFacility(
            id="partner-hosp-101",
            clinic="demo-clinic",
            name="Nalgonda District Maternal & Diagnostic Centre",
            facility_type="referral_hospital",
            contact_person="Dr. Ramesh Babu (Nodal Officer)",
            contact_phone="9440001122",
            address="Collectorate Road, Nalgonda",
            services_offered_json='["obstetric_ultrasound", "blood_panel", "high_risk_obstetric_review", "inpatient_maternity"]',
            agreement_reference="MOU-JANANI-NLG-2026-01",
            effective_from=today - timedelta(days=180),
            effective_until=today + timedelta(days=185),
            contract_status="active",
            schedule_charges_json='{"obstetric_ultrasound_paise": 80000, "high_risk_obstetric_review_paise": 120000}',
            is_verified_partner=True,
            created_by=admin1.id,
        )
        db.add(pf1)

    tp1 = TransportPartner(
        id="tpartner-101",
        clinic="demo-clinic",
        name="Devarakonda Rural Maternal Mobility Cooperative",
        partner_type="community_van_contract",
        contact_person="Venkatesh Goud",
        contact_phone="9848002233",
        agreement_ref="TRANS-MOU-2026-04",
        effective_until=today + timedelta(days=300),
        base_tariff_paise=45000,
        is_active=True,
        disclaimer_note="Non-emergency scheduled maternal clinic transport only. Dial 108 / 102 for obstetric emergencies.",
        created_by=admin1.id,
    )
    db.add(tp1)
    db.flush()

    tv1 = TransportVehicleDriver(
        id="tdriver-101",
        partner_id=tp1.id,
        clinic="demo-clinic",
        driver_name="Srinivasulu Yadav",
        driver_phone="9848009988",
        driving_licence_no="TS05-20190048821",
        licence_expiry_date=today + timedelta(days=500),
        vehicle_registration_no="TS-05-UC-4499",
        vehicle_type="patient_transport_van",
        insurance_policy_no="UIIC-TS05-2026-88412",
        insurance_expiry_date=today + timedelta(days=210),
        credentials_verified=True,
        verified_by=admin1.id,
        verified_at=ts,
        availability_status="available",
    )
    db.add(tv1)
    db.flush()
    db.commit()


def _seed_phase6_if_empty(db: Session) -> None:
    """Ensure Phase 6 default synthetic funder, contract, budget, statutory config, and agreements exist."""
    if db.get(FundingOrganisation, "funder-nhm-101") is not None:
        return
    admin1 = db.get(Staff, "staff-admin-1")
    doc1 = db.get(Staff, "staff-doc-1")
    nurse1 = db.get(Staff, "staff-nurse-1")
    fc1 = db.get(Staff, "staff-fc-1")
    if not (admin1 and doc1 and nurse1 and fc1):
        return
    today = date.today()
    ts = now()
    exp1 = db.get(Expense, "exp-syn-101")
    exp2 = db.get(Expense, "exp-syn-102")

    # Phase 6 Seed Data: Funder, Simulated-Approved Programme Contract, Budget, Payroll Config & Agreements
    funder1 = FundingOrganisation(
        id="funder-nhm-101",
        clinic="demo-clinic",
        name="District Maternal Health Mission Directorate (Synthetic Demo Funder)",
        funder_type="nhm_authority",
        registration_or_grant_code="SYN-NHM-TS-NLG-2026",
        nodal_officer_name="Sri K. Venkatramana (Synthetic Nodal Officer)",
        nodal_officer_designation="Joint Director - Maternal Health Programmes",
        contact_email="nodal.synthetic@nhm-demo.example.org",
        contact_phone="9440099100",
        address="District Health Complex, Nalgonda (Synthetic Demo)",
        is_active=True,
        created_by=admin1.id,
    )
    db.add(funder1)
    db.flush()

    contract1 = ProgrammeContract(
        id="contract-syn-101",
        clinic="demo-clinic",
        funder_id=funder1.id,
        programme_name="Janani Suraksha & Rural ANC Continuity Programme (Synthetic Demo)",
        contract_reference="SYN-MOU-NHM-2026-101",
        sanction_order_ref="SYN-SANCTION-DEMO-2026-01 (SIMULATED)",
        state="active",
        is_simulated_approval=True,
        approval_disclaimer=(
            "SIMULATED / DEMO APPROVAL ONLY — Synthetic test contract for JananiSetu Phase 6 evaluation. "
            "Does not represent an official government sanction order."
        ),
        funder_signatory_name="Sri K. Venkatramana (Synthetic Demo)",
        funder_signatory_designation="Joint Director (Synthetic)",
        recipient_signatory_name=admin1.name,
        signed_agreement_filename="SYN-MOU-NHM-2026-101-SIGNED.pdf",
        signed_agreement_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        effective_from=today - timedelta(days=60),
        effective_until=today + timedelta(days=305),
        funding_ceiling_paise=250000000,  # Rs 25,00,000.00 (25 Lakhs in paise)
        funding_received_paise=100000000,  # Rs 10,00,000.00 Tranche 1 received
        funder_share_bps=9000,  # 90.00% funder reimbursement share
        reimbursement_basis="actual_verified_cost",
        allow_private_transport_reimbursement=False,
        objectives_json='["4+ timely ANC checkups","Safe rural clinic transport","High-risk obstetric referral coordination"]',
        delivery_obligations_json='["Monthly verified service-to-funding evidence package","Zero unverified expenditure claims"]',
        allowed_categories_json='["salary","travel","transport","clinical_services","diagnostics","technology","administration"]',
        disallowed_categories_json='["private_unapproved_transport","entertainment","unverified_cash"]',
        participating_clinics_json='["demo-clinic"]',
        clinic_allocations_json='{"demo-clinic": 250000000}',
        version_number=1,
        submitted_by=admin1.id,
        submitted_at=ts,
        approved_by=doc1.id,
        approved_at=ts,
        approval_evidence_ref="SYN-SANCTION-DEMO-2026-01",
        created_by=admin1.id,
    )
    db.add(contract1)
    db.flush()

    mile1 = ContractMilestone(
        id="mile-syn-101",
        contract_id=contract1.id,
        clinic="demo-clinic",
        milestone_name="Tranche 1: Mobilisation & Q1 Maternal Outreach",
        due_date=today - timedelta(days=30),
        deliverable_obligation="Onboard clinical workforce and initiate ANC follow-up cohort",
        tranche_amount_paise=100000000,
        status="received",
        received_amount_paise=100000000,
        payment_reference="UTR-SYN-NHM-2026-001",
        received_at=ts,
        verified_by=admin1.id,
    )
    mile2 = ContractMilestone(
        id="mile-syn-102",
        contract_id=contract1.id,
        clinic="demo-clinic",
        milestone_name="Tranche 2: Mid-Term Verified ANC & Transport Utilisation",
        due_date=today + timedelta(days=60),
        deliverable_obligation="Submit verified service-to-funding evidence package for 100+ ANC visits",
        tranche_amount_paise=150000000,
        status="pending",
        received_amount_paise=0,
    )
    db.add_all([mile1, mile2])

    budget1 = ProgrammeBudget(
        id="budget-syn-101",
        contract_id=contract1.id,
        clinic="demo-clinic",
        budget_scope="clinic_level",
        target_clinic="demo-clinic",
        fiscal_year="2026-27",
        period_start=today - timedelta(days=60),
        period_end=today + timedelta(days=305),
        total_allocated_paise=250000000,
        status="approved",
        version_number=1,
        created_by=admin1.id,
        approved_by=doc1.id,
        approved_at=ts,
    )
    db.add(budget1)
    db.flush()

    cat_allocations = [
        ("bcat-syn-sal", "salary", 120000000, 0, 0, 0, 0, 0),
        ("bcat-syn-trv", "travel", 20000000, 0, 45000, 0, 0, 0),
        ("bcat-syn-trn", "transport", 35000000, 0, 85000, 85000, 85000, 0),
        ("bcat-syn-cln", "clinical_services", 35000000, 0, 0, 0, 0, 0),
        ("bcat-syn-dgn", "diagnostics", 20000000, 0, 0, 0, 0, 0),
        ("bcat-syn-tec", "technology", 10000000, 0, 0, 0, 0, 0),
        ("bcat-syn-adm", "administration", 10000000, 0, 0, 0, 0, 0),
    ]
    for cid, cat, alloc, comm, inc, appr, paid, reimb in cat_allocations:
        db.add(
            BudgetCategoryLine(
                id=cid,
                budget_id=budget1.id,
                contract_id=contract1.id,
                clinic="demo-clinic",
                category=cat,
                allocated_paise=alloc,
                committed_paise=comm,
                incurred_paise=inc,
                approved_paise=appr,
                paid_paise=paid,
                reimbursed_paise=reimb,
            )
        )

    if exp1:
        exp1.contract_id = contract1.id
        exp1.budget_id = budget1.id
        exp1.reimbursement_status = "approved_pending_claim"
    if exp2:
        exp2.contract_id = contract1.id
        exp2.budget_id = budget1.id

    stat_cfg = PayrollStatutoryConfig(
        id="stat-cfg-101",
        clinic="demo-clinic",
        version_number=1,
        config_name="FY 2026-27 Telangana PHC Explicit Statutory Schedule (Validated)",
        effective_from=date(2026, 4, 1),
        pf_employee_bps=1200,  # 12.00% on capped PF wage ceiling
        pf_employer_bps=1200,
        pf_wage_ceiling_paise=1500000,  # Rs 15,000.00 ceiling
        esi_employee_bps=75,  # 0.75% when gross <= Rs 21,000.00
        esi_employer_bps=325,  # 3.25%
        esi_wage_ceiling_paise=2100000,  # Rs 21,000.00 ceiling
        professional_tax_paise=20000,  # Rs 200.00 explicit PT slab
        tds_default_bps=500,  # 5.00% explicit withholding configured for demo
        validated_by_professional_name="CA M. Narasimha Rao (Synthetic Payroll Auditor)",
        validated_by_credentials="ICAI Membership #SYN-088412",
        validation_notes="Explicitly configured statutory schedule for demo-clinic; never uses unvalidated universal rates.",
        is_active=True,
        created_by=admin1.id,
    )
    db.add(stat_cfg)

    comp_doc = StaffCompensationAgreement(
        id="comp-doc-1",
        staff_id=doc1.id,
        clinic="demo-clinic",
        contract_id=contract1.id,
        budget_id=budget1.id,
        employment_type="full_time_employee",
        pay_structure="monthly_fixed",
        base_monthly_paise=8500000,  # Rs 85,000.00
        per_shift_rate_paise=0,
        per_visit_rate_paise=0,
        field_allowance_paise=500000,  # Rs 5,000.00rural specialist allowance
        expected_monthly_days=26,
        attendance_adjustment_permitted=True,
        statutory_deductions_enabled=True,
        effective_from=date(2026, 4, 1),
        status="active",
        version_number=1,
        approved_by=admin1.id,
        created_by=admin1.id,
    )
    comp_nurse = StaffCompensationAgreement(
        id="comp-nurse-1",
        staff_id=nurse1.id,
        clinic="demo-clinic",
        contract_id=contract1.id,
        budget_id=budget1.id,
        employment_type="nhm_deputed",
        pay_structure="retainer_plus_visit",
        base_monthly_paise=3200000,  # Rs 32,000.00
        per_shift_rate_paise=0,
        per_visit_rate_paise=30000,  # Rs 300.00 per verified field visit
        field_allowance_paise=200000,  # Rs 2,000.00
        expected_monthly_days=26,
        attendance_adjustment_permitted=True,
        statutory_deductions_enabled=True,
        effective_from=date(2026, 4, 1),
        status="active",
        version_number=1,
        approved_by=admin1.id,
        created_by=admin1.id,
    )
    comp_fc = StaffCompensationAgreement(
        id="comp-fc-1",
        staff_id=fc1.id,
        clinic="demo-clinic",
        contract_id=contract1.id,
        budget_id=budget1.id,
        employment_type="community_honorarium",
        pay_structure="retainer_plus_visit",
        base_monthly_paise=1800000,  # Rs 18,000.00 honorarium retainer
        per_shift_rate_paise=0,
        per_visit_rate_paise=20000,  # Rs 200.00 per verified outreach visit
        field_allowance_paise=150000,  # Rs 1,500.00
        expected_monthly_days=26,
        attendance_adjustment_permitted=False,  # Agreement does NOT permit attendance deduction on base honorarium
        statutory_deductions_enabled=True,
        effective_from=date(2026, 4, 1),
        status="active",
        version_number=1,
        approved_by=admin1.id,
        created_by=admin1.id,
    )
    db.add_all([comp_doc, comp_nurse, comp_fc])

    pol1 = ExpensePolicyRule(
        id="policy-syn-101",
        clinic="demo-clinic",
        contract_id=contract1.id,
        policy_name="NHM Rural Outreach Two-Wheeler Mileage & Empaneled Van Policy",
        claim_type="staff_travel_claim",
        rate_basis="per_km_mileage",
        per_km_rate_paise=1200,  # Rs 12.00 / km
        fixed_allowance_paise=15000,  # Rs 150.00 daily subsistence option
        max_single_claim_paise=500000,  # Rs 5,000.00 max per claim
        requires_receipt_above_paise=10000,
        allow_private_transport=False,
        effective_from=date(2026, 4, 1),
        is_active=True,
        approved_by=admin1.id,
    )
    db.add(pol1)
    db.commit()
