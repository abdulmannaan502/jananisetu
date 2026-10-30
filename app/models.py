"""SQLAlchemy 2.0 ORM models with strict clinic multi-tenancy, token revocation, and Phase 3 ANC digitisation."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(timezone.utc)


def uid() -> str:
    return str(uuid.uuid4())[:12]


class Base(DeclarativeBase):
    pass


class Staff(Base):
    __tablename__ = "staff"
    __table_args__ = (
        Index("ix_staff_clinic", "clinic"),
        Index("ix_staff_email", "email"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    role: Mapped[str] = mapped_column(String(40))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    password_hash: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(24), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"
    __table_args__ = (Index("ix_revoked_tokens_staff_id", "staff_id"),)

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    staff_id: Mapped[str] = mapped_column(String(36))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    reason: Mapped[str] = mapped_column(String(100), default="logout")
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Mother(Base):
    __tablename__ = "mothers"
    __table_args__ = (Index("ix_mothers_clinic", "clinic"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(140))
    phone: Mapped[str] = mapped_column(String(24))
    patient_identifier: Mapped[str] = mapped_column(String(80), default="")
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    edd: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    lmp: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    address: Mapped[str] = mapped_column(String(300), default="")
    language: Mapped[str] = mapped_column(String(10), default="te")
    consent: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str] = mapped_column(Text, default="")
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    registered_by: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CarePlan(Base):
    __tablename__ = "care_plans"
    __table_args__ = (
        Index("ix_care_plans_clinic", "clinic"),
        Index("ix_care_plans_mother_id", "mother_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    mother_id: Mapped[str] = mapped_column(String(36), ForeignKey("mothers.id"))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    visit_date: Mapped[date] = mapped_column(Date)
    visit_type: Mapped[str] = mapped_column(String(50), default="anc_checkup")
    appointment_status: Mapped[str] = mapped_column(String(40), default="scheduled")
    follow_up_notes: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    approved_by: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Phase 4: Closed-loop follow-up state machine
    followup_state: Mapped[str] = mapped_column(String(50), default="scheduled")
    ack_deadline_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    visit_confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    superseded_by_plan_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_clinic", "clinic"),
        Index("ix_tasks_mother_id", "mother_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    mother_id: Mapped[str] = mapped_column(String(36), ForeignKey("mothers.id"))
    care_plan_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    category: Mapped[str] = mapped_column(String(60))
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="open")
    assigned_to: Mapped[str] = mapped_column(String(36), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    completion_notes: Mapped[str] = mapped_column(Text, default="")
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    escalated_to: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    escalated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    escalation_reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_clinic", "clinic"),
        Index("ix_messages_mother_id", "mother_id"),
        Index("ix_messages_provider_msg_id", "provider_message_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    mother_id: Mapped[str] = mapped_column(String(36), ForeignKey("mothers.id"))
    care_plan_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    reminder_job_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    direction: Mapped[str] = mapped_column(String(20))
    recipient_type: Mapped[str] = mapped_column(String(20), default="mother")
    recipient_phone_masked: Mapped[str] = mapped_column(String(30), default="")
    template_name: Mapped[str] = mapped_column(String(80), default="")
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="queued")
    delivery_status_rank: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str] = mapped_column(String(60), default="local-simulator")
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_code: Mapped[str] = mapped_column(String(60), default="")
    failure_reason: Mapped[str] = mapped_column(Text, default="")
    flagged_for_clinical_review: Mapped[bool] = mapped_column(Boolean, default=False)
    clinical_review_status: Mapped[str] = mapped_column(
        String(40), default="not_required"
    )
    clinical_review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Transport(Base):
    __tablename__ = "transport"
    __table_args__ = (
        Index("ix_transport_clinic", "clinic"),
        Index("ix_transport_mother_id", "mother_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    mother_id: Mapped[str] = mapped_column(String(36), ForeignKey("mothers.id"))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    date: Mapped[date] = mapped_column(Date)
    pickup_time: Mapped[str] = mapped_column(String(20), default="09:00")
    from_location: Mapped[str] = mapped_column(String(255))
    destination: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(40), default="requested")
    partner: Mapped[str] = mapped_column(String(160), default="not assigned")
    vehicle_notes: Mapped[str] = mapped_column(Text, default="")
    requested_by: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    # Phase 5: Extended transport partner, vehicle/driver, trip lifecycle & expense fields
    service_request_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    referral_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    partner_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    vehicle_driver_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    driver_response_status: Mapped[str] = mapped_column(String(40), default="pending")
    driver_rejection_reason: Mapped[str] = mapped_column(String(200), default="")
    trip_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trip_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancellation_reason: Mapped[str] = mapped_column(String(200), default="")
    failed_pickup_reason: Mapped[str] = mapped_column(String(200), default="")
    reassigned_from_driver_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    trip_expense_paise: Mapped[int] = mapped_column(Integer, default=0)
    receipt_ref: Mapped[str] = mapped_column(String(120), default="")
    expense_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (Index("ix_expenses_clinic", "clinic"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    category: Mapped[str] = mapped_column(String(60))
    amount_paise: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text, default="")
    receipt_ref: Mapped[str] = mapped_column(String(120), default="")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(36), default="")
    approved_by: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    # Phase 6: Contract, Budget, Claim, Payroll & Funding Reimbursement linkage (no duplicate financial rows)
    contract_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    budget_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    expense_claim_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    payroll_run_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    funding_claim_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    reimbursement_status: Mapped[str] = mapped_column(String(40), default="unclaimed")
    payment_ref: Mapped[str] = mapped_column(String(120), default="")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_clinic", "clinic"),
        Index("ix_documents_mother_id", "mother_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    mother_id: Mapped[str] = mapped_column(String(36), ForeignKey("mothers.id"))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    supersedes_document_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    filename: Mapped[str] = mapped_column(String(200))
    stored_path: Mapped[str] = mapped_column(String(255), default="")
    preview_path: Mapped[str] = mapped_column(String(255), default="")
    content_type: Mapped[str] = mapped_column(String(60), default="image/png")
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256_hash: Mapped[str] = mapped_column(String(64), default="")
    image_width: Mapped[int] = mapped_column(Integer, default=0)
    image_height: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=1)
    ocr_status: Mapped[str] = mapped_column(String(40), default="completed")
    ocr_engine: Mapped[str] = mapped_column(String(60), default="tesseract-5")
    ocr_error: Mapped[str] = mapped_column(Text, default="")
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    structured_fields: Mapped[str] = mapped_column(Text, default="{}")
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[str] = mapped_column(String(40), default="pending_review")
    uploaded_by: Mapped[str] = mapped_column(String(36), default="")
    confirmed_by: Mapped[str] = mapped_column(String(36), default="")
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OcrJob(Base):
    __tablename__ = "ocr_jobs"
    __table_args__ = (
        Index("ix_ocr_jobs_document_id", "document_id"),
        Index("ix_ocr_jobs_clinic", "clinic"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    engine: Mapped[str] = mapped_column(String(60), default="tesseract-5")
    external_provider_used: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(40), default="succeeded")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    mean_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    missing_fields_json: Mapped[str] = mapped_column(Text, default="[]")
    conflicts_json: Mapped[str] = mapped_column(Text, default="[]")
    error_message: Mapped[str] = mapped_column(Text, default="")
    raw_tokens_json: Mapped[str] = mapped_column(Text, default="[]")


class ExtractedField(Base):
    __tablename__ = "extracted_fields"
    __table_args__ = (
        Index("ix_extracted_fields_document_id", "document_id"),
        Index("ix_extracted_fields_clinic", "clinic"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"))
    ocr_job_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    field_key: Mapped[str] = mapped_column(String(60))
    field_label: Mapped[str] = mapped_column(String(120))
    extracted_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    normalized_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    uncertainty_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    uncertainty_reason: Mapped[str] = mapped_column(String(255), default="")
    conflict_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    conflicting_values_json: Mapped[str] = mapped_column(Text, default="[]")
    source_page: Mapped[int] = mapped_column(Integer, default=1)
    bbox_x: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bbox_y: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bbox_w: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bbox_h: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_snippet: Mapped[str] = mapped_column(Text, default="")
    verification_status: Mapped[str] = mapped_column(String(40), default="unreviewed")
    final_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewer_note: Mapped[str] = mapped_column(Text, default="")
    verified_by: Mapped[str] = mapped_column(String(36), default="")
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class FieldSourceLocation(Base):
    __tablename__ = "field_source_locations"
    __table_args__ = (
        Index("ix_field_source_locations_field_id", "extracted_field_id"),
        Index("ix_field_source_locations_document_id", "document_id"),
        Index("ix_field_source_locations_clinic", "clinic"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    extracted_field_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("extracted_fields.id")
    )
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    page_number: Mapped[int] = mapped_column(Integer, default=1)
    x: Mapped[int] = mapped_column(Integer)
    y: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    token_text: Mapped[str] = mapped_column(String(200), default="")
    token_confidence: Mapped[float] = mapped_column(Float, default=0.0)


class VerificationDecision(Base):
    __tablename__ = "verification_decisions"
    __table_args__ = (
        Index("ix_verification_decisions_document_id", "document_id"),
        Index("ix_verification_decisions_clinic", "clinic"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"))
    extracted_field_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    field_key: Mapped[str] = mapped_column(String(60))
    decision: Mapped[str] = mapped_column(String(40))
    extracted_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[str] = mapped_column(String(36))
    decided_by_role: Mapped[str] = mapped_column(String(40), default="")
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        Index("ix_document_versions_mother_id", "mother_id"),
        Index("ix_document_versions_document_id", "document_id"),
        Index("ix_document_versions_clinic", "clinic"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    mother_id: Mapped[str] = mapped_column(String(36), ForeignKey("mothers.id"))
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    previous_document_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    confirmed_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    diff_summary_json: Mapped[str] = mapped_column(Text, default="[]")
    created_by: Mapped[str] = mapped_column(String(36), default="")
    confirmed_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AdminChangeProposal(Base):
    __tablename__ = "admin_change_proposals"
    __table_args__ = (
        Index("ix_admin_change_proposals_mother_id", "mother_id"),
        Index("ix_admin_change_proposals_document_id", "document_id"),
        Index("ix_admin_change_proposals_clinic", "clinic"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    mother_id: Mapped[str] = mapped_column(String(36), ForeignKey("mothers.id"))
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    field_key: Mapped[str] = mapped_column(String(60))
    previous_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    proposed_value: Mapped[str] = mapped_column(Text)
    proposal_type: Mapped[str] = mapped_column(
        String(50), default="mother_profile_update"
    )
    status: Mapped[str] = mapped_column(String(30), default="pending")
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    reviewed_by_role: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_clinic", "clinic"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    actor: Mapped[str] = mapped_column(String(36))
    actor_role: Mapped[str] = mapped_column(String(40), default="")
    action: Mapped[str] = mapped_column(String(80))
    entity: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(60))
    occurred: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    detail: Mapped[str] = mapped_column(Text, default="")


class ReminderJob(Base):
    """Persistent appointment-based reminder job with unique idempotency key and retry/dead-letter state."""

    __tablename__ = "reminder_jobs"
    __table_args__ = (
        Index("ix_reminder_jobs_clinic", "clinic"),
        Index("ix_reminder_jobs_care_plan_id", "care_plan_id"),
        Index("ix_reminder_jobs_mother_id", "mother_id"),
        Index("ix_reminder_jobs_status_scheduled", "status", "scheduled_for"),
        Index("ix_reminder_jobs_idempotency_key", "idempotency_key", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True)
    care_plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("care_plans.id"))
    mother_id: Mapped[str] = mapped_column(String(36), ForeignKey("mothers.id"))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    recipient_type: Mapped[str] = mapped_column(String(20), default="mother")
    caregiver_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    offset_hours: Mapped[int] = mapped_column(Integer, default=-24)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone_name: Mapped[str] = mapped_column(String(40), default="Asia/Kolkata")
    channel: Mapped[str] = mapped_column(String(40), default="local-simulator")
    template_name: Mapped[str] = mapped_column(String(80), default="janani_anc_reminder_v1")
    status: Mapped[str] = mapped_column(String(40), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str] = mapped_column(Text, default="")
    dead_lettered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancellation_reason: Mapped[str] = mapped_column(String(160), default="")
    message_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TransactionalOutbox(Base):
    """Transactional outbox table preventing lost jobs between DB commits and worker queue dispatch."""

    __tablename__ = "transactional_outbox"
    __table_args__ = (
        Index("ix_transactional_outbox_clinic", "clinic"),
        Index("ix_transactional_outbox_status", "status"),
        Index("ix_transactional_outbox_idempotency", "idempotency_key", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    aggregate_type: Mapped[str] = mapped_column(String(60), default="reminder_job")
    aggregate_id: Mapped[str] = mapped_column(String(36))
    event_type: Mapped[str] = mapped_column(String(60), default="enqueue_reminder")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WebhookEvent(Base):
    """Idempotency ledger for signed inbound messages and delivery callbacks."""

    __tablename__ = "webhook_events"
    __table_args__ = (
        Index("ix_webhook_events_event_id", "event_id", unique=True),
        Index("ix_webhook_events_clinic", "clinic"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    provider: Mapped[str] = mapped_column(String(40), default="whatsapp-cloud")
    event_id: Mapped[str] = mapped_column(String(120), unique=True)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    event_type: Mapped[str] = mapped_column(String(40), default="delivery_callback")
    signature_verified: Mapped[bool] = mapped_column(Boolean, default=True)
    payload_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(30), default="processed")
    detail: Mapped[str] = mapped_column(Text, default="")
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ContactAttempt(Base):
    """Human follow-up contact attempt log recorded by nurses or field coordinators."""

    __tablename__ = "contact_attempts"
    __table_args__ = (
        Index("ix_contact_attempts_task_id", "task_id"),
        Index("ix_contact_attempts_mother_id", "mother_id"),
        Index("ix_contact_attempts_clinic", "clinic"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"))
    mother_id: Mapped[str] = mapped_column(String(36), ForeignKey("mothers.id"))
    care_plan_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    staff_id: Mapped[str] = mapped_column(String(36))
    staff_role: Mapped[str] = mapped_column(String(40), default="")
    channel: Mapped[str] = mapped_column(String(40), default="phone_call")
    outcome: Mapped[str] = mapped_column(String(50))
    notes: Mapped[str] = mapped_column(Text, default="")
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CaregiverConsent(Base):
    """Explicit, revocable caregiver permission for limited administrative reminders."""

    __tablename__ = "caregiver_consents"
    __table_args__ = (
        Index("ix_caregiver_consents_mother_id", "mother_id"),
        Index("ix_caregiver_consents_clinic", "clinic"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    mother_id: Mapped[str] = mapped_column(String(36), ForeignKey("mothers.id"))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    caregiver_name: Mapped[str] = mapped_column(String(140))
    caregiver_phone: Mapped[str] = mapped_column(String(24))
    relationship_type: Mapped[str] = mapped_column(String(60), default="spouse")
    language: Mapped[str] = mapped_column(String(10), default="te")
    consent_granted: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_admin_reminders: Mapped[bool] = mapped_column(Boolean, default=True)
    granted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=now
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recorded_by: Mapped[str] = mapped_column(String(36), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ClinicCommConfig(Base):
    """Clinic-scoped communication and reminder scheduling settings."""

    __tablename__ = "clinic_comm_configs"

    clinic: Mapped[str] = mapped_column(String(80), primary_key=True)
    timezone: Mapped[str] = mapped_column(String(40), default="Asia/Kolkata")
    reminder_offsets_hours_json: Mapped[str] = mapped_column(
        String(120), default="[-48, -24, 0]"
    )
    ack_deadline_hours: Mapped[int] = mapped_column(Integer, default=12)
    default_channel: Mapped[str] = mapped_column(String(40), default="local-simulator")
    whatsapp_template_en: Mapped[str] = mapped_column(
        String(80), default="janani_anc_reminder_en"
    )
    whatsapp_template_te: Mapped[str] = mapped_column(
        String(80), default="janani_anc_reminder_te"
    )
    whatsapp_template_hi: Mapped[str] = mapped_column(
        String(80), default="janani_anc_reminder_hi"
    )
    max_retry_attempts: Mapped[int] = mapped_column(Integer, default=3)
    retry_base_seconds: Mapped[int] = mapped_column(Integer, default=60)
    enable_caregiver_reminders: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by: Mapped[str] = mapped_column(String(36), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# ---------------------------------------------------------------------------
# Phase 5: Healthcare Workforce, Field Visits, Hospital Partnerships,
# Transport Operations & Clinical/Organisational Governance
# ---------------------------------------------------------------------------
class StaffWorkforceProfile(Base):
    """Workforce profile keeping employment/contractor status distinct from clinical role & permissions."""

    __tablename__ = "staff_workforce_profiles"
    __table_args__ = (
        Index("ix_staff_workforce_profiles_staff_id", "staff_id", unique=True),
        Index("ix_staff_workforce_profiles_clinic", "clinic"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    staff_id: Mapped[str] = mapped_column(String(36), ForeignKey("staff.id"), unique=True)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    employment_type: Mapped[str] = mapped_column(
        String(50), default="full_time_employee"
    )  # full_time_employee, part_time_employee, contract_clinician, nhm_deputed, community_honorarium
    onboarding_status: Mapped[str] = mapped_column(
        String(40), default="active_onboarded"
    )  # pending_onboarding, active_onboarded, on_leave, suspended, offboarded
    clinical_cadre: Mapped[str] = mapped_column(
        String(60), default="general"
    )  # medical_officer_obgyn, medical_officer_mbbs, anm_staff_nurse, asha_field_coordinator, clinic_administrator
    qualification: Mapped[str] = mapped_column(String(160), default="")
    registration_council: Mapped[str] = mapped_column(String(140), default="")
    registration_number: Mapped[str] = mapped_column(String(80), default="")
    # Self-entered credentials are NEVER treated as verified until reviewed by an authorised verifier with evidence
    credential_verification_status: Mapped[str] = mapped_column(
        String(40), default="unverified"
    )  # unverified, pending_review, verified, expired, rejected
    credential_verified_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    credential_verified_by_role: Mapped[str] = mapped_column(String(40), default="")
    credential_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    credential_evidence_ref: Mapped[str] = mapped_column(String(255), default="")
    credential_expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    assigned_facility: Mapped[str] = mapped_column(String(160), default="PHC Main Facility")
    availability_days_json: Mapped[str] = mapped_column(
        String(160), default='["Mon","Tue","Wed","Thu","Fri","Sat"]'
    )
    shift_preference: Mapped[str] = mapped_column(String(40), default="morning")
    onboarded_by: Mapped[str] = mapped_column(String(36), default="")
    onboarded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=now
    )
    offboarded_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    offboarded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    offboarding_reason: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class StaffCredentialDocument(Base):
    """Professional registration and credential document storage with expiry tracking and human verification."""

    __tablename__ = "staff_credential_documents"
    __table_args__ = (
        Index("ix_staff_credential_documents_staff_id", "staff_id"),
        Index("ix_staff_credential_documents_clinic", "clinic"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    staff_id: Mapped[str] = mapped_column(String(36), ForeignKey("staff.id"))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    document_type: Mapped[str] = mapped_column(
        String(60), default="medical_council_registration"
    )  # medical_council_registration, nursing_license, degree_certificate, id_proof
    registration_number: Mapped[str] = mapped_column(String(80))
    issuing_authority: Mapped[str] = mapped_column(String(160))
    issued_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    evidence_filename: Mapped[str] = mapped_column(String(200), default="credential_cert.pdf")
    evidence_notes: Mapped[str] = mapped_column(Text, default="")
    verification_status: Mapped[str] = mapped_column(
        String(40), default="unverified"
    )  # unverified, verified, rejected, expired
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    reviewed_by_role: Mapped[str] = mapped_column(String(40), default="")
    review_evidence_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    uploaded_by: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class StaffShift(Base):
    """Staff shift assignment, attendance tracking, and replacement management."""

    __tablename__ = "staff_shifts"
    __table_args__ = (
        Index("ix_staff_shifts_staff_date", "staff_id", "shift_date"),
        Index("ix_staff_shifts_clinic_date", "clinic", "shift_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    staff_id: Mapped[str] = mapped_column(String(36), ForeignKey("staff.id"))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    facility_name: Mapped[str] = mapped_column(String(160), default="PHC Main Facility")
    shift_date: Mapped[date] = mapped_column(Date)
    start_time: Mapped[str] = mapped_column(String(10), default="08:00")
    end_time: Mapped[str] = mapped_column(String(10), default="16:00")
    shift_type: Mapped[str] = mapped_column(
        String(40), default="morning"
    )  # morning, afternoon, night, field_outreach
    status: Mapped[str] = mapped_column(
        String(40), default="scheduled"
    )  # scheduled, checked_in, completed, absent, leave_covered, cancelled
    check_in_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    check_out_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replacement_staff_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    assigned_by: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class StaffLeaveRequest(Base):
    """Staff leave and replacement staff coordination."""

    __tablename__ = "staff_leave_requests"
    __table_args__ = (
        Index("ix_staff_leave_requests_staff_id", "staff_id"),
        Index("ix_staff_leave_requests_clinic", "clinic"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    staff_id: Mapped[str] = mapped_column(String(36), ForeignKey("staff.id"))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    leave_type: Mapped[str] = mapped_column(String(40), default="casual")
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(
        String(40), default="pending"
    )  # pending, approved, rejected, cancelled
    replacement_staff_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ServiceRequest(Base):
    """Operational patient service coordination lifecycle:
    service_requested -> staff_assigned -> scheduled -> in_progress -> completed -> verified -> closed.
    """

    __tablename__ = "service_requests"
    __table_args__ = (
        Index("ix_service_requests_clinic", "clinic"),
        Index("ix_service_requests_mother_id", "mother_id"),
        Index("ix_service_requests_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    mother_id: Mapped[str] = mapped_column(String(36), ForeignKey("mothers.id"))
    care_plan_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    service_type: Mapped[str] = mapped_column(
        String(60), default="anc_home_visit"
    )  # anc_home_visit, postnatal_check, nutrition_counselling, lab_sample_collection, clinical_consultation, transport_escort
    requires_clinical_qualification: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(40), default="service_requested")
    assigned_staff_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    assigned_staff_role: Mapped[str] = mapped_column(String(40), default="")
    scheduled_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    scheduled_time: Mapped[str] = mapped_column(String(20), default="10:00")
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verified_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancellation_reason: Mapped[str] = mapped_column(String(255), default="")
    failure_reason: Mapped[str] = mapped_column(String(255), default="")
    reassigned_from_staff_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    clinical_authorisation_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    completion_evidence: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FieldVisit(Base):
    """Nurse and field-worker daily visit schedule, consent check, role-scoped notes, and offline draft sync."""

    __tablename__ = "field_visits"
    __table_args__ = (
        Index("ix_field_visits_clinic_date", "clinic", "visit_date"),
        Index("ix_field_visits_staff_date", "assigned_staff_id", "visit_date"),
        Index("ix_field_visits_mother_id", "mother_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    service_request_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    mother_id: Mapped[str] = mapped_column(String(36), ForeignKey("mothers.id"))
    care_plan_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    assigned_staff_id: Mapped[str] = mapped_column(String(36), ForeignKey("staff.id"))
    staff_role: Mapped[str] = mapped_column(String(40), default="nurse")
    visit_date: Mapped[date] = mapped_column(Date)
    scheduled_window: Mapped[str] = mapped_column(String(40), default="09:00-11:00")
    visit_address: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(
        String(40), default="scheduled"
    )  # scheduled, confirmed_with_patient, in_progress, completed, failed_visit, rescheduled, cancelled
    contact_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    patient_consent_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    # Location collection is strictly optional, purpose-limited, and requires explicit consent
    location_consent_granted: Mapped[bool] = mapped_column(Boolean, default=False)
    checkin_latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    checkin_longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_purpose: Mapped[str] = mapped_column(String(160), default="")
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    role_scoped_notes: Mapped[str] = mapped_column(Text, default="")
    clinical_observations_by_clinician: Mapped[str] = mapped_column(Text, default="")
    completion_evidence_type: Mapped[str] = mapped_column(String(60), default="")
    completion_evidence_ref: Mapped[str] = mapped_column(String(255), default="")
    failed_reason: Mapped[str] = mapped_column(String(160), default="")
    rescheduled_to_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    offline_draft_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    synced_from_offline: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PartnerFacility(Base):
    """Hospital, diagnostic lab, and ultrasound partner facility registry."""

    __tablename__ = "partner_facilities"
    __table_args__ = (Index("ix_partner_facilities_clinic", "clinic"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    name: Mapped[str] = mapped_column(String(160))
    facility_type: Mapped[str] = mapped_column(
        String(60), default="referral_hospital"
    )  # referral_hospital, diagnostic_lab, ultrasound_centre, blood_bank, chc_fr_unit
    contact_person: Mapped[str] = mapped_column(String(120), default="")
    contact_phone: Mapped[str] = mapped_column(String(24), default="")
    address: Mapped[str] = mapped_column(String(255), default="")
    services_offered_json: Mapped[str] = mapped_column(
        Text, default='["High-Risk Obstetrics","Ultrasound","Complete Blood Count"]'
    )
    agreement_reference: Mapped[str] = mapped_column(String(100), default="")
    effective_from: Mapped[date] = mapped_column(Date)
    effective_until: Mapped[date] = mapped_column(Date)
    contract_status: Mapped[str] = mapped_column(
        String(40), default="active"
    )  # active, expiring_soon, expired, suspended
    schedule_charges_json: Mapped[str] = mapped_column(Text, default="{}")
    is_verified_partner: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class HospitalReferral(Base):
    """Clinician-authorised referral and diagnostic service completion workflow."""

    __tablename__ = "hospital_referrals"
    __table_args__ = (
        Index("ix_hospital_referrals_clinic", "clinic"),
        Index("ix_hospital_referrals_mother_id", "mother_id"),
        Index("ix_hospital_referrals_partner_id", "partner_facility_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    mother_id: Mapped[str] = mapped_column(String(36), ForeignKey("mothers.id"))
    care_plan_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    partner_facility_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("partner_facilities.id")
    )
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    referral_category: Mapped[str] = mapped_column(
        String(60), default="clinical_obstetric"
    )  # clinical_obstetric, routine_ultrasound, diagnostic_lab, administrative_transfer
    requires_clinician_authorisation: Mapped[bool] = mapped_column(Boolean, default=True)
    authorised_by_clinician_id: Mapped[str] = mapped_column(String(36))
    authorised_by_role: Mapped[str] = mapped_column(String(40), default="doctor")
    reason_and_clinical_summary: Mapped[str] = mapped_column(Text)
    requested_services_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(
        String(40), default="initiated"
    )  # initiated, sent_to_partner, acknowledged_by_partner, appointment_booked, service_completed, verified_closed, cancelled
    partner_acknowledgement_ref: Mapped[str] = mapped_column(String(120), default="")
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scheduled_service_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    service_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completion_evidence_ref: Mapped[str] = mapped_column(String(255), default="")
    verified_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    contractual_charge_paise: Mapped[int] = mapped_column(Integer, default=0)
    expense_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    cancellation_reason: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TransportPartner(Base):
    """Registered non-emergency maternal transport partners."""

    __tablename__ = "transport_partners"
    __table_args__ = (Index("ix_transport_partners_clinic", "clinic"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    name: Mapped[str] = mapped_column(String(160))
    partner_type: Mapped[str] = mapped_column(
        String(60), default="community_van_contract"
    )  # community_van_contract, 102_janani_express_liaison, local_empaneled_taxi
    contact_person: Mapped[str] = mapped_column(String(120), default="")
    contact_phone: Mapped[str] = mapped_column(String(24), default="")
    agreement_ref: Mapped[str] = mapped_column(String(100), default="")
    effective_until: Mapped[date] = mapped_column(Date)
    base_tariff_paise: Mapped[int] = mapped_column(Integer, default=50000)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    disclaimer_note: Mapped[str] = mapped_column(
        String(255),
        default="Scheduled maternal transport coordination only (not live emergency ambulance dispatch).",
    )
    created_by: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TransportVehicleDriver(Base):
    """Registered vehicles, drivers, and licence/insurance expiry tracking."""

    __tablename__ = "transport_vehicles_drivers"
    __table_args__ = (
        Index("ix_transport_vehicles_drivers_clinic", "clinic"),
        Index("ix_transport_vehicles_drivers_partner", "partner_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    partner_id: Mapped[str] = mapped_column(String(36), ForeignKey("transport_partners.id"))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    driver_name: Mapped[str] = mapped_column(String(120))
    driver_phone: Mapped[str] = mapped_column(String(24))
    driving_licence_no: Mapped[str] = mapped_column(String(80))
    licence_expiry_date: Mapped[date] = mapped_column(Date)
    vehicle_registration_no: Mapped[str] = mapped_column(String(60))
    vehicle_type: Mapped[str] = mapped_column(
        String(60), default="patient_transport_van"
    )  # patient_transport_van, empaneled_sedan, basic_support_ambulance
    insurance_policy_no: Mapped[str] = mapped_column(String(80))
    insurance_expiry_date: Mapped[date] = mapped_column(Date)
    credentials_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    availability_status: Mapped[str] = mapped_column(
        String(40), default="available"
    )  # available, on_trip, off_duty, maintenance
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class GovernanceIncident(Base):
    """Clinical and organisational governance incident reporting & human review escalation."""

    __tablename__ = "governance_incidents"
    __table_args__ = (
        Index("ix_governance_incidents_clinic", "clinic"),
        Index("ix_governance_incidents_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    incident_type: Mapped[str] = mapped_column(
        String(60), default="protocol_deviation"
    )  # missed_high_priority_visit, credential_expiry_alert, partner_contract_expiry, failed_pickup_escalation, data_correction_request, protocol_deviation
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    entity_type: Mapped[str] = mapped_column(String(60), default="")
    entity_id: Mapped[str] = mapped_column(String(60), default="")
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(40), default="open"
    )  # open, under_review, escalated, resolved
    reported_by: Mapped[str] = mapped_column(String(36))
    assigned_reviewer_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    resolution_notes: Mapped[str] = mapped_column(Text, default="")
    resolved_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RecordCorrectionLog(Base):
    """Immutable audit log of record corrections with human approval history."""

    __tablename__ = "record_correction_logs"
    __table_args__ = (
        Index("ix_record_correction_logs_clinic", "clinic"),
        Index("ix_record_correction_logs_entity", "entity_type", "entity_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str] = mapped_column(String(60))
    field_name: Mapped[str] = mapped_column(String(80))
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[str] = mapped_column(Text)
    correction_reason: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[str] = mapped_column(String(36))
    approved_by: Mapped[str] = mapped_column(String(36))
    approved_by_role: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# ---------------------------------------------------------------------------
# Phase 6: Government Contracts, Programme Budgets, Healthcare Payroll,
# Transport Expenses & Funding Accountability
# ---------------------------------------------------------------------------
class FundingOrganisation(Base):
    """Government department, NHM authority, hospital, NGO, or CSR funder registry."""

    __tablename__ = "funding_organisations"
    __table_args__ = (Index("ix_funding_organisations_clinic", "clinic"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    name: Mapped[str] = mapped_column(String(180))
    funder_type: Mapped[str] = mapped_column(
        String(50), default="nhm_authority"
    )  # government_department, nhm_authority, public_hospital, ngo_foundation, csr_funder
    registration_or_grant_code: Mapped[str] = mapped_column(String(100), default="")
    nodal_officer_name: Mapped[str] = mapped_column(String(140), default="")
    nodal_officer_designation: Mapped[str] = mapped_column(String(140), default="")
    contact_email: Mapped[str] = mapped_column(String(160), default="")
    contact_phone: Mapped[str] = mapped_column(String(24), default="")
    address: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProgrammeContract(Base):
    """Funding contract / grant lifecycle:
    draft -> submitted -> approved -> active -> suspended | completed | terminated.
    Draft proposals are NEVER represented as government-approved funding.
    """

    __tablename__ = "programme_contracts"
    __table_args__ = (
        Index("ix_programme_contracts_clinic", "clinic"),
        Index("ix_programme_contracts_funder", "funder_id"),
        Index("ix_programme_contracts_state", "state"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    funder_id: Mapped[str] = mapped_column(String(36), ForeignKey("funding_organisations.id"))
    programme_name: Mapped[str] = mapped_column(String(200))
    contract_reference: Mapped[str] = mapped_column(String(100))
    sanction_order_ref: Mapped[str] = mapped_column(String(120), default="")
    state: Mapped[str] = mapped_column(
        String(40), default="draft"
    )  # draft, submitted, approved, active, suspended, completed, terminated
    is_simulated_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    approval_disclaimer: Mapped[str] = mapped_column(
        String(300),
        default="DRAFT PROPOSAL — Not an approved government or institutional sanction order.",
    )
    funder_signatory_name: Mapped[str] = mapped_column(String(140), default="")
    funder_signatory_designation: Mapped[str] = mapped_column(String(140), default="")
    recipient_signatory_name: Mapped[str] = mapped_column(String(140), default="")
    signed_agreement_filename: Mapped[str] = mapped_column(String(200), default="")
    signed_agreement_sha256: Mapped[str] = mapped_column(String(64), default="")
    signed_agreement_stored_path: Mapped[str] = mapped_column(String(255), default="")
    effective_from: Mapped[date] = mapped_column(Date)
    effective_until: Mapped[date] = mapped_column(Date)
    funding_ceiling_paise: Mapped[int] = mapped_column(Integer)
    funding_received_paise: Mapped[int] = mapped_column(Integer, default=0)
    funder_share_bps: Mapped[int] = mapped_column(Integer, default=10000)  # 10000 bps = 100.00%
    reimbursement_basis: Mapped[str] = mapped_column(
        String(50), default="actual_verified_cost"
    )  # actual_verified_cost, fixed_unit_rate, milestone_tranche
    allow_private_transport_reimbursement: Mapped[bool] = mapped_column(Boolean, default=False)
    objectives_json: Mapped[str] = mapped_column(Text, default="[]")
    delivery_obligations_json: Mapped[str] = mapped_column(Text, default="[]")
    allowed_categories_json: Mapped[str] = mapped_column(
        Text,
        default='["salary","travel","transport","clinical_services","diagnostics","technology","administration"]',
    )
    disallowed_categories_json: Mapped[str] = mapped_column(
        Text, default='["private_unapproved_transport","entertainment","unverified_cash"]'
    )
    participating_clinics_json: Mapped[str] = mapped_column(Text, default='["demo-clinic"]')
    clinic_allocations_json: Mapped[str] = mapped_column(Text, default="{}")
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    submitted_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_evidence_ref: Mapped[str] = mapped_column(String(200), default="")
    created_by: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ContractMilestone(Base):
    """Contract payment milestones and funding tranche receipts."""

    __tablename__ = "contract_milestones"
    __table_args__ = (
        Index("ix_contract_milestones_contract", "contract_id"),
        Index("ix_contract_milestones_clinic", "clinic"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    contract_id: Mapped[str] = mapped_column(String(36), ForeignKey("programme_contracts.id"))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    milestone_name: Mapped[str] = mapped_column(String(180))
    due_date: Mapped[date] = mapped_column(Date)
    deliverable_obligation: Mapped[str] = mapped_column(String(300), default="")
    tranche_amount_paise: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(40), default="pending"
    )  # pending, submitted, approved, received
    received_amount_paise: Mapped[int] = mapped_column(Integer, default=0)
    payment_reference: Mapped[str] = mapped_column(String(120), default="")
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ContractAmendment(Base):
    """Versioned contract extensions, ceiling revisions, and category rule amendments."""

    __tablename__ = "contract_amendments"
    __table_args__ = (
        Index("ix_contract_amendments_contract", "contract_id"),
        Index("ix_contract_amendments_clinic", "clinic"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    contract_id: Mapped[str] = mapped_column(String(36), ForeignKey("programme_contracts.id"))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    version_number: Mapped[int] = mapped_column(Integer, default=2)
    amendment_type: Mapped[str] = mapped_column(
        String(50), default="extension"
    )  # extension, ceiling_revision, category_rule_change, clinic_allocation_change
    previous_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    new_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    previous_ceiling_paise: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    new_ceiling_paise: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    amendment_summary: Mapped[str] = mapped_column(Text)
    approval_reference: Mapped[str] = mapped_column(String(140))
    approved_by: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProgrammeBudget(Base):
    """Programme-level and clinic-level approved budgets."""

    __tablename__ = "programme_budgets"
    __table_args__ = (
        Index("ix_programme_budgets_clinic", "clinic"),
        Index("ix_programme_budgets_contract", "contract_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    contract_id: Mapped[str] = mapped_column(String(36), ForeignKey("programme_contracts.id"))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    budget_scope: Mapped[str] = mapped_column(
        String(40), default="clinic_level"
    )  # programme_level, clinic_level
    target_clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    fiscal_year: Mapped[str] = mapped_column(String(20), default="2026-27")
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    total_allocated_paise: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40), default="approved")  # draft, approved, locked
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(36), default="")
    approved_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class BudgetCategoryLine(Base):
    """Category-level budget tracking exact integer paise across committed, incurred, approved, paid & reimbursed."""

    __tablename__ = "budget_category_lines"
    __table_args__ = (
        Index("ix_budget_category_lines_budget", "budget_id"),
        Index("ix_budget_category_lines_clinic", "clinic"),
        Index("ix_budget_category_lines_unique_cat", "budget_id", "category", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    budget_id: Mapped[str] = mapped_column(String(36), ForeignKey("programme_budgets.id"))
    contract_id: Mapped[str] = mapped_column(String(36), ForeignKey("programme_contracts.id"))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    category: Mapped[str] = mapped_column(
        String(50)
    )  # salary, travel, transport, clinical_services, diagnostics, technology, administration
    allocated_paise: Mapped[int] = mapped_column(Integer, default=0)
    committed_paise: Mapped[int] = mapped_column(Integer, default=0)
    incurred_paise: Mapped[int] = mapped_column(Integer, default=0)
    approved_paise: Mapped[int] = mapped_column(Integer, default=0)
    paid_paise: Mapped[int] = mapped_column(Integer, default=0)
    reimbursed_paise: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class BudgetAmendmentLog(Base):
    """Authorised budget amendments with version history."""

    __tablename__ = "budget_amendment_logs"
    __table_args__ = (
        Index("ix_budget_amendment_logs_budget", "budget_id"),
        Index("ix_budget_amendment_logs_clinic", "clinic"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    budget_id: Mapped[str] = mapped_column(String(36), ForeignKey("programme_budgets.id"))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    version_number: Mapped[int] = mapped_column(Integer, default=2)
    category: Mapped[str] = mapped_column(String(50))
    old_allocated_paise: Mapped[int] = mapped_column(Integer)
    new_allocated_paise: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    approval_reference: Mapped[str] = mapped_column(String(120))
    requested_by: Mapped[str] = mapped_column(String(36))
    approved_by: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PayrollStatutoryConfig(Base):
    """Explicit, versioned statutory deduction and employer contribution configuration.
    Never assumes universal Indian tax, PF, ESI, or PT rates without explicit professional validation.
    """

    __tablename__ = "payroll_statutory_configs"
    __table_args__ = (Index("ix_payroll_statutory_configs_clinic", "clinic"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    config_name: Mapped[str] = mapped_column(String(160))
    effective_from: Mapped[date] = mapped_column(Date)
    pf_employee_bps: Mapped[int] = mapped_column(Integer, default=0)  # e.g. 1200 bps = 12.00%
    pf_employer_bps: Mapped[int] = mapped_column(Integer, default=0)
    pf_wage_ceiling_paise: Mapped[int] = mapped_column(Integer, default=1500000)
    esi_employee_bps: Mapped[int] = mapped_column(Integer, default=0)  # e.g. 75 bps = 0.75%
    esi_employer_bps: Mapped[int] = mapped_column(Integer, default=0)  # e.g. 325 bps = 3.25%
    esi_wage_ceiling_paise: Mapped[int] = mapped_column(Integer, default=2100000)
    professional_tax_paise: Mapped[int] = mapped_column(Integer, default=0)
    tds_default_bps: Mapped[int] = mapped_column(Integer, default=0)
    validated_by_professional_name: Mapped[str] = mapped_column(String(140))
    validated_by_credentials: Mapped[str] = mapped_column(String(140))
    validation_notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class StaffCompensationAgreement(Base):
    """Staff compensation agreement with effective dates, employment terms, and attendance adjustment rules."""

    __tablename__ = "staff_compensation_agreements"
    __table_args__ = (
        Index("ix_staff_compensation_agreements_staff", "staff_id"),
        Index("ix_staff_compensation_agreements_clinic", "clinic"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    staff_id: Mapped[str] = mapped_column(String(36), ForeignKey("staff.id"))
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    contract_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    budget_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    employment_type: Mapped[str] = mapped_column(String(50), default="full_time_employee")
    pay_structure: Mapped[str] = mapped_column(
        String(40), default="monthly_fixed"
    )  # monthly_fixed, per_shift_rate, per_visit_rate, retainer_plus_visit
    base_monthly_paise: Mapped[int] = mapped_column(Integer, default=0)
    per_shift_rate_paise: Mapped[int] = mapped_column(Integer, default=0)
    per_visit_rate_paise: Mapped[int] = mapped_column(Integer, default=0)
    field_allowance_paise: Mapped[int] = mapped_column(Integer, default=0)
    expected_monthly_days: Mapped[int] = mapped_column(Integer, default=26)
    attendance_adjustment_permitted: Mapped[bool] = mapped_column(Boolean, default=False)
    statutory_deductions_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")  # active, superseded, terminated
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    approved_by: Mapped[str] = mapped_column(String(36), default="")
    created_by: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PayrollRun(Base):
    """Monthly payroll batch calculation, review, approval, lock, and verified payment confirmation."""

    __tablename__ = "payroll_runs"
    __table_args__ = (
        Index("ix_payroll_runs_clinic_month", "clinic", "period_month"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    period_month: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    contract_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    budget_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    statutory_config_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(
        String(40), default="draft"
    )  # draft, reviewed, approved, locked, paid_verified
    total_gross_paise: Mapped[int] = mapped_column(Integer, default=0)
    total_deductions_paise: Mapped[int] = mapped_column(Integer, default=0)
    total_employer_contributions_paise: Mapped[int] = mapped_column(Integer, default=0)
    total_reimbursements_paise: Mapped[int] = mapped_column(Integer, default=0)
    total_net_payable_paise: Mapped[int] = mapped_column(Integer, default=0)
    payslip_count: Mapped[int] = mapped_column(Integer, default=0)
    calculated_by: Mapped[str] = mapped_column(String(36), default="")
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_batch_ref: Mapped[str] = mapped_column(String(120), default="")
    payment_evidence_ref: Mapped[str] = mapped_column(String(200), default="")
    paid_confirmed_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    paid_confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expense_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PayslipRecord(Base):
    """Individual staff monthly payslip with unique constraint preventing duplicate payroll."""

    __tablename__ = "payslip_records"
    __table_args__ = (
        Index(
            "ix_payslip_records_unique_staff_month",
            "clinic",
            "period_month",
            "staff_id",
            unique=True,
        ),
        Index("ix_payslip_records_run", "payroll_run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    payroll_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("payroll_runs.id"))
    staff_id: Mapped[str] = mapped_column(String(36), ForeignKey("staff.id"))
    agreement_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("staff_compensation_agreements.id")
    )
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    period_month: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    employment_type: Mapped[str] = mapped_column(String(50), default="full_time_employee")
    pay_structure: Mapped[str] = mapped_column(String(40), default="monthly_fixed")
    days_scheduled: Mapped[int] = mapped_column(Integer, default=0)
    days_attended: Mapped[int] = mapped_column(Integer, default=0)
    approved_leave_days: Mapped[int] = mapped_column(Integer, default=0)
    unexcused_absent_days: Mapped[int] = mapped_column(Integer, default=0)
    completed_visits_count: Mapped[int] = mapped_column(Integer, default=0)
    base_pay_paise: Mapped[int] = mapped_column(Integer, default=0)
    visit_or_shift_pay_paise: Mapped[int] = mapped_column(Integer, default=0)
    allowance_paise: Mapped[int] = mapped_column(Integer, default=0)
    attendance_deduction_paise: Mapped[int] = mapped_column(Integer, default=0)
    gross_earnings_paise: Mapped[int] = mapped_column(Integer, default=0)
    pf_employee_paise: Mapped[int] = mapped_column(Integer, default=0)
    esi_employee_paise: Mapped[int] = mapped_column(Integer, default=0)
    professional_tax_paise: Mapped[int] = mapped_column(Integer, default=0)
    tds_paise: Mapped[int] = mapped_column(Integer, default=0)
    total_deductions_paise: Mapped[int] = mapped_column(Integer, default=0)
    pf_employer_paise: Mapped[int] = mapped_column(Integer, default=0)
    esi_employer_paise: Mapped[int] = mapped_column(Integer, default=0)
    approved_reimbursements_paise: Mapped[int] = mapped_column(Integer, default=0)
    net_payable_paise: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        String(40), default="draft"
    )  # draft, reviewed, approved, locked, paid_verified
    payment_ref: Mapped[str] = mapped_column(String(120), default="")
    payment_evidence_ref: Mapped[str] = mapped_column(String(200), default="")
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    correction_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ExpensePolicyRule(Base):
    """Approved travel mileage, fixed allowance, and transport reimbursement rules."""

    __tablename__ = "expense_policy_rules"
    __table_args__ = (Index("ix_expense_policy_rules_clinic", "clinic"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    contract_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    policy_name: Mapped[str] = mapped_column(String(160))
    claim_type: Mapped[str] = mapped_column(
        String(50), default="staff_travel_claim"
    )  # staff_travel_claim, transport_partner_invoice, diagnostic_partner_invoice, field_outreach_allowance
    rate_basis: Mapped[str] = mapped_column(
        String(40), default="per_km_mileage"
    )  # per_km_mileage, fixed_allowance, contracted_tariff
    per_km_rate_paise: Mapped[int] = mapped_column(Integer, default=0)
    fixed_allowance_paise: Mapped[int] = mapped_column(Integer, default=0)
    max_single_claim_paise: Mapped[int] = mapped_column(Integer, default=500000)
    requires_receipt_above_paise: Mapped[int] = mapped_column(Integer, default=10000)
    allow_private_transport: Mapped[bool] = mapped_column(Boolean, default=False)
    effective_from: Mapped[date] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_by: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ExpenseClaim(Base):
    """Staff travel claims, transport partner invoices, receipt verification, and multi-stage reimbursement."""

    __tablename__ = "expense_claims"
    __table_args__ = (
        Index("ix_expense_claims_clinic", "clinic"),
        Index("ix_expense_claims_status", "status"),
        Index("ix_expense_claims_receipt", "clinic", "receipt_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    contract_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    budget_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    policy_rule_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    expense_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    claim_type: Mapped[str] = mapped_column(
        String(50), default="staff_travel_claim"
    )  # staff_travel_claim, transport_partner_invoice, diagnostic_partner_invoice, field_outreach_allowance
    expense_category: Mapped[str] = mapped_column(
        String(50), default="travel"
    )  # travel, transport, clinical_services, diagnostics, administration
    claimant_staff_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    transport_partner_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    partner_facility_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    transport_trip_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    field_visit_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    service_request_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    referral_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    transport_mode: Mapped[str] = mapped_column(
        String(50), default="empaneled_partner_van"
    )  # empaneled_partner_van, public_bus_rail, staff_two_wheeler_mileage, private_unapproved
    distance_km: Mapped[int] = mapped_column(Integer, default=0)
    amount_paise: Mapped[int] = mapped_column(Integer)
    receipt_number: Mapped[str] = mapped_column(String(120))
    receipt_filename: Mapped[str] = mapped_column(String(200), default="receipt.pdf")
    receipt_sha256: Mapped[str] = mapped_column(String(64), default="")
    receipt_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(
        String(40), default="submitted"
    )  # submitted, verified_by_supervisor, approved_by_finance, reimbursed_paid, rejected, returned_for_correction
    submitted_by: Mapped[str] = mapped_column(String(36))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    verified_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_notes: Mapped[str] = mapped_column(Text, default="")
    approved_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_notes: Mapped[str] = mapped_column(Text, default="")
    rejection_or_return_reason: Mapped[str] = mapped_column(Text, default="")
    reimbursement_payment_ref: Mapped[str] = mapped_column(String(120), default="")
    reimbursed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    version_number: Mapped[int] = mapped_column(Integer, default=1)


class FundingClaim(Base):
    """Institutional funding claim / invoice submitted against an active contract and budget."""

    __tablename__ = "funding_claims"
    __table_args__ = (
        Index("ix_funding_claims_clinic", "clinic"),
        Index("ix_funding_claims_contract", "contract_id"),
        Index("ix_funding_claims_ref", "clinic", "claim_reference", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    contract_id: Mapped[str] = mapped_column(String(36), ForeignKey("programme_contracts.id"))
    budget_id: Mapped[str] = mapped_column(String(36), ForeignKey("programme_budgets.id"))
    milestone_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    claim_reference: Mapped[str] = mapped_column(String(100))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    total_claimed_paise: Mapped[int] = mapped_column(Integer, default=0)
    funder_reimbursable_paise: Mapped[int] = mapped_column(Integer, default=0)
    approved_reimbursed_paise: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        String(40), default="draft"
    )  # draft, submitted_to_funder, under_verification, approved_by_funder, reimbursed_settled, disputed_returned
    evidence_package_hash: Mapped[str] = mapped_column(String(64), default="")
    submitted_by: Mapped[str] = mapped_column(String(36), default="")
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    settled_payment_ref: Mapped[str] = mapped_column(String(120), default="")
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ServiceFundingEvidenceLink(Base):
    """Auditable link between Contract, Programme, Service Category, Staff/Provider, Completed Service/Trip,
    Verification Evidence, Expenditure, and Funding Claim without exposing private clinical details.
    """

    __tablename__ = "service_funding_evidence_links"
    __table_args__ = (
        Index("ix_service_funding_evidence_claim", "funding_claim_id"),
        Index("ix_service_funding_evidence_clinic", "clinic"),
        Index("ix_service_funding_evidence_unique_exp", "clinic", "expense_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    funding_claim_id: Mapped[str] = mapped_column(String(36), ForeignKey("funding_claims.id"))
    contract_id: Mapped[str] = mapped_column(String(36), ForeignKey("programme_contracts.id"))
    budget_id: Mapped[str] = mapped_column(String(36), ForeignKey("programme_budgets.id"))
    service_category: Mapped[str] = mapped_column(String(50))
    staff_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    provider_entity_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    service_request_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    field_visit_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    transport_trip_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    referral_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    expense_id: Mapped[str] = mapped_column(String(36), ForeignKey("expenses.id"))
    expense_claim_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    payslip_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    beneficiary_anonymised_ref: Mapped[str] = mapped_column(String(80), default="SYN-BENEFICIARY")
    verification_evidence_ref: Mapped[str] = mapped_column(String(200))
    verified_by_staff_id: Mapped[str] = mapped_column(String(36))
    amount_paise: Mapped[int] = mapped_column(Integer)
    reimbursable_paise: Mapped[int] = mapped_column(Integer)
    reimbursement_status: Mapped[str] = mapped_column(
        String(40), default="linked"
    )  # linked, submitted, reimbursed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FinancialAuditLedger(Base):
    """Immutable append-only financial audit ledger with idempotency key protection."""

    __tablename__ = "financial_audit_ledger"
    __table_args__ = (
        Index("ix_financial_audit_ledger_clinic", "clinic"),
        Index("ix_financial_audit_ledger_entity", "entity_type", "entity_id"),
        Index("ix_financial_audit_ledger_idem", "idempotency_key", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, unique=True)
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(80))
    previous_state: Mapped[str] = mapped_column(String(50), default="")
    new_state: Mapped[str] = mapped_column(String(50), default="")
    amount_paise: Mapped[int] = mapped_column(Integer, default=0)
    actor_id: Mapped[str] = mapped_column(String(36))
    actor_role: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(Text, default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FinancialCorrectionRecord(Base):
    """Versioned financial corrections instead of destructive overwrites."""

    __tablename__ = "financial_correction_records"
    __table_args__ = (
        Index("ix_financial_correction_records_clinic", "clinic"),
        Index("ix_financial_correction_records_entity", "entity_type", "entity_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    clinic: Mapped[str] = mapped_column(String(80), default="demo-clinic")
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str] = mapped_column(String(60))
    version_number: Mapped[int] = mapped_column(Integer, default=2)
    field_name: Mapped[str] = mapped_column(String(80))
    previous_value_paise: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    new_value_paise: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    previous_text: Mapped[str] = mapped_column(Text, default="")
    new_text: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[str] = mapped_column(String(36))
    approved_by: Mapped[str] = mapped_column(String(36))
    approved_by_role: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

