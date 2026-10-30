"""Phase 4: Durable reminder infrastructure, closed-loop follow-up state machine, messaging & caregiver consent

Revision ID: 0003_phase4_followup_and_messaging
Revises: 0002_phase3_anc_digitisation
Create Date: 2026-10-29 17:25:00
"""
from __future__ import annotations

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0003_phase4_followup_and_messaging"
down_revision: Union[str, None] = "0002_phase3_anc_digitisation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(inspector, table_name: str, col_name: str) -> bool:
    return any(c["name"] == col_name for c in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "care_plans" in existing_tables:
        cp_cols = [
            ("followup_state", sa.Column("followup_state", sa.String(50), server_default="scheduled")),
            ("ack_deadline_at", sa.Column("ack_deadline_at", sa.DateTime(timezone=True), nullable=True)),
            ("acknowledged_at", sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True)),
            ("visit_confirmed_at", sa.Column("visit_confirmed_at", sa.DateTime(timezone=True), nullable=True)),
            ("closed_at", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True)),
            ("superseded_by_plan_id", sa.Column("superseded_by_plan_id", sa.String(36), nullable=True)),
        ]
        for col_name, col_obj in cp_cols:
            if not _has_column(inspector, "care_plans", col_name):
                op.add_column("care_plans", col_obj)

    if "tasks" in existing_tables:
        task_cols = [
            ("care_plan_id", sa.Column("care_plan_id", sa.String(36), nullable=True)),
            ("escalated_to", sa.Column("escalated_to", sa.String(36), nullable=True)),
            ("escalated_at", sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True)),
            ("escalation_reason", sa.Column("escalation_reason", sa.Text(), server_default="")),
        ]
        for col_name, col_obj in task_cols:
            if not _has_column(inspector, "tasks", col_name):
                op.add_column("tasks", col_obj)

    if "messages" in existing_tables:
        msg_cols = [
            ("care_plan_id", sa.Column("care_plan_id", sa.String(36), nullable=True)),
            ("reminder_job_id", sa.Column("reminder_job_id", sa.String(36), nullable=True)),
            ("recipient_type", sa.Column("recipient_type", sa.String(20), server_default="mother")),
            ("recipient_phone_masked", sa.Column("recipient_phone_masked", sa.String(30), server_default="")),
            ("template_name", sa.Column("template_name", sa.String(80), server_default="")),
            ("delivery_status_rank", sa.Column("delivery_status_rank", sa.Integer(), server_default="0")),
            ("provider_message_id", sa.Column("provider_message_id", sa.String(120), nullable=True)),
            ("idempotency_key", sa.Column("idempotency_key", sa.String(120), nullable=True)),
            ("delivered_at", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True)),
            ("acknowledged_at", sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True)),
            ("failure_code", sa.Column("failure_code", sa.String(60), server_default="")),
            ("failure_reason", sa.Column("failure_reason", sa.Text(), server_default="")),
            ("flagged_for_clinical_review", sa.Column("flagged_for_clinical_review", sa.Boolean(), server_default="0")),
            ("clinical_review_status", sa.Column("clinical_review_status", sa.String(40), server_default="not_required")),
            ("clinical_review_note", sa.Column("clinical_review_note", sa.Text(), server_default="")),
            ("reviewed_by", sa.Column("reviewed_by", sa.String(36), nullable=True)),
            ("reviewed_at", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True)),
        ]
        for col_name, col_obj in msg_cols:
            if not _has_column(inspector, "messages", col_name):
                op.add_column("messages", col_obj)

    if "reminder_jobs" not in existing_tables:
        op.create_table(
            "reminder_jobs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("idempotency_key", sa.String(120), unique=True, nullable=False),
            sa.Column("care_plan_id", sa.String(36), sa.ForeignKey("care_plans.id"), nullable=False),
            sa.Column("mother_id", sa.String(36), sa.ForeignKey("mothers.id"), nullable=False),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("recipient_type", sa.String(20), server_default="mother"),
            sa.Column("caregiver_id", sa.String(36), nullable=True),
            sa.Column("offset_hours", sa.Integer(), server_default="-24"),
            sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
            sa.Column("timezone_name", sa.String(40), server_default="Asia/Kolkata"),
            sa.Column("channel", sa.String(40), server_default="local-simulator"),
            sa.Column("template_name", sa.String(80), server_default="janani_anc_reminder_v1"),
            sa.Column("status", sa.String(40), server_default="pending"),
            sa.Column("attempts", sa.Integer(), server_default="0"),
            sa.Column("max_attempts", sa.Integer(), server_default="3"),
            sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), server_default=""),
            sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancellation_reason", sa.String(160), server_default=""),
            sa.Column("message_id", sa.String(36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_reminder_jobs_clinic", "reminder_jobs", ["clinic"])
        op.create_index("ix_reminder_jobs_care_plan_id", "reminder_jobs", ["care_plan_id"])
        op.create_index("ix_reminder_jobs_mother_id", "reminder_jobs", ["mother_id"])
        op.create_index("ix_reminder_jobs_status_scheduled", "reminder_jobs", ["status", "scheduled_for"])
        op.create_index("ix_reminder_jobs_idempotency_key", "reminder_jobs", ["idempotency_key"], unique=True)

    if "transactional_outbox" not in existing_tables:
        op.create_table(
            "transactional_outbox",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("idempotency_key", sa.String(120), unique=True, nullable=False),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("aggregate_type", sa.String(60), server_default="reminder_job"),
            sa.Column("aggregate_id", sa.String(36), nullable=False),
            sa.Column("event_type", sa.String(60), server_default="enqueue_reminder"),
            sa.Column("payload_json", sa.Text(), server_default="{}"),
            sa.Column("status", sa.String(30), server_default="pending"),
            sa.Column("attempts", sa.Integer(), server_default="0"),
            sa.Column("last_error", sa.Text(), server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_transactional_outbox_clinic", "transactional_outbox", ["clinic"])
        op.create_index("ix_transactional_outbox_status", "transactional_outbox", ["status"])
        op.create_index("ix_transactional_outbox_idempotency", "transactional_outbox", ["idempotency_key"], unique=True)

    if "webhook_events" not in existing_tables:
        op.create_table(
            "webhook_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("provider", sa.String(40), server_default="whatsapp-cloud"),
            sa.Column("event_id", sa.String(120), unique=True, nullable=False),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic"),
            sa.Column("event_type", sa.String(40), server_default="delivery_callback"),
            sa.Column("signature_verified", sa.Boolean(), server_default="1"),
            sa.Column("payload_hash", sa.String(64), server_default=""),
            sa.Column("status", sa.String(30), server_default="processed"),
            sa.Column("detail", sa.Text(), server_default=""),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_webhook_events_event_id", "webhook_events", ["event_id"], unique=True)
        op.create_index("ix_webhook_events_clinic", "webhook_events", ["clinic"])

    if "contact_attempts" not in existing_tables:
        op.create_table(
            "contact_attempts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id"), nullable=False),
            sa.Column("mother_id", sa.String(36), sa.ForeignKey("mothers.id"), nullable=False),
            sa.Column("care_plan_id", sa.String(36), nullable=True),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("staff_id", sa.String(36), nullable=False),
            sa.Column("staff_role", sa.String(40), server_default=""),
            sa.Column("channel", sa.String(40), server_default="phone_call"),
            sa.Column("outcome", sa.String(50), nullable=False),
            sa.Column("notes", sa.Text(), server_default=""),
            sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_contact_attempts_task_id", "contact_attempts", ["task_id"])
        op.create_index("ix_contact_attempts_mother_id", "contact_attempts", ["mother_id"])
        op.create_index("ix_contact_attempts_clinic", "contact_attempts", ["clinic"])

    if "caregiver_consents" not in existing_tables:
        op.create_table(
            "caregiver_consents",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("mother_id", sa.String(36), sa.ForeignKey("mothers.id"), nullable=False),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("caregiver_name", sa.String(140), nullable=False),
            sa.Column("caregiver_phone", sa.String(24), nullable=False),
            sa.Column("relationship_type", sa.String(60), server_default="spouse"),
            sa.Column("language", sa.String(10), server_default="te"),
            sa.Column("consent_granted", sa.Boolean(), server_default="1"),
            sa.Column("allow_admin_reminders", sa.Boolean(), server_default="1"),
            sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("recorded_by", sa.String(36), server_default=""),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_caregiver_consents_mother_id", "caregiver_consents", ["mother_id"])
        op.create_index("ix_caregiver_consents_clinic", "caregiver_consents", ["clinic"])

    if "clinic_comm_configs" not in existing_tables:
        op.create_table(
            "clinic_comm_configs",
            sa.Column("clinic", sa.String(80), primary_key=True),
            sa.Column("timezone", sa.String(40), server_default="Asia/Kolkata"),
            sa.Column("reminder_offsets_hours_json", sa.String(120), server_default="[-48, -24, 0]"),
            sa.Column("ack_deadline_hours", sa.Integer(), server_default="12"),
            sa.Column("default_channel", sa.String(40), server_default="local-simulator"),
            sa.Column("whatsapp_template_en", sa.String(80), server_default="janani_anc_reminder_en"),
            sa.Column("whatsapp_template_te", sa.String(80), server_default="janani_anc_reminder_te"),
            sa.Column("whatsapp_template_hi", sa.String(80), server_default="janani_anc_reminder_hi"),
            sa.Column("max_retry_attempts", sa.Integer(), server_default="3"),
            sa.Column("retry_base_seconds", sa.Integer(), server_default="60"),
            sa.Column("enable_caregiver_reminders", sa.Boolean(), server_default="1"),
            sa.Column("updated_by", sa.String(36), server_default=""),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for tbl in [
        "clinic_comm_configs",
        "caregiver_consents",
        "contact_attempts",
        "webhook_events",
        "transactional_outbox",
        "reminder_jobs",
    ]:
        if tbl in existing_tables:
            op.drop_table(tbl)
