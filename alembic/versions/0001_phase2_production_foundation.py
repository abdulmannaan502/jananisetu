"""Phase 2 production foundation schema with multi-clinic isolation and RBAC.

Revision ID: 0001_phase2_foundation
Revises: None
Create Date: 2026-10-29 16:30:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001_phase2_foundation"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "staff" not in existing_tables:
        op.create_table(
            "staff",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("email", sa.String(160), nullable=True),
            sa.Column("role", sa.String(40), nullable=False),
            sa.Column("clinic", sa.String(80), nullable=False, server_default="demo-clinic"),
            sa.Column("password_hash", sa.String(255), nullable=False, server_default=""),
            sa.Column("phone", sa.String(24), nullable=False, server_default=""),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_staff_clinic", "staff", ["clinic"])
        op.create_index("ix_staff_email", "staff", ["email"])

    if "mothers" not in existing_tables:
        op.create_table(
            "mothers",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("name", sa.String(140), nullable=False),
            sa.Column("phone", sa.String(24), nullable=False),
            sa.Column("age", sa.Integer(), nullable=True),
            sa.Column("edd", sa.Date(), nullable=True),
            sa.Column("lmp", sa.Date(), nullable=True),
            sa.Column("address", sa.String(300), nullable=False, server_default=""),
            sa.Column("language", sa.String(10), nullable=False, server_default="te"),
            sa.Column("consent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("consent_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("clinic", sa.String(80), nullable=False, server_default="demo-clinic"),
            sa.Column("registered_by", sa.String(36), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_mothers_clinic", "mothers", ["clinic"])

    if "care_plans" not in existing_tables:
        op.create_table(
            "care_plans",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("mother_id", sa.String(36), sa.ForeignKey("mothers.id"), nullable=False),
            sa.Column("clinic", sa.String(80), nullable=False, server_default="demo-clinic"),
            sa.Column("visit_date", sa.Date(), nullable=False),
            sa.Column("visit_type", sa.String(50), nullable=False, server_default="anc_checkup"),
            sa.Column("appointment_status", sa.String(40), nullable=False, server_default="scheduled"),
            sa.Column("follow_up_notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("note", sa.Text(), nullable=False, server_default=""),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("approved_by", sa.String(36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )
        op.create_index("ix_care_plans_clinic", "care_plans", ["clinic"])
        op.create_index("ix_care_plans_mother_id", "care_plans", ["mother_id"])

    if "tasks" not in existing_tables:
        op.create_table(
            "tasks",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("mother_id", sa.String(36), sa.ForeignKey("mothers.id"), nullable=False),
            sa.Column("clinic", sa.String(80), nullable=False, server_default="demo-clinic"),
            sa.Column("category", sa.String(60), nullable=False),
            sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("status", sa.String(40), nullable=False, server_default="open"),
            sa.Column("assigned_to", sa.String(36), nullable=False, server_default=""),
            sa.Column("detail", sa.Text(), nullable=False, server_default=""),
            sa.Column("completion_notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.String(36), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_tasks_clinic", "tasks", ["clinic"])
        op.create_index("ix_tasks_mother_id", "tasks", ["mother_id"])

    if "messages" not in existing_tables:
        op.create_table(
            "messages",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("mother_id", sa.String(36), sa.ForeignKey("mothers.id"), nullable=False),
            sa.Column("clinic", sa.String(80), nullable=False, server_default="demo-clinic"),
            sa.Column("direction", sa.String(20), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("status", sa.String(40), nullable=False, server_default="queued"),
            sa.Column("provider", sa.String(60), nullable=False, server_default="local-simulator"),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_messages_clinic", "messages", ["clinic"])
        op.create_index("ix_messages_mother_id", "messages", ["mother_id"])

    if "transport" not in existing_tables:
        op.create_table(
            "transport",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("mother_id", sa.String(36), sa.ForeignKey("mothers.id"), nullable=False),
            sa.Column("clinic", sa.String(80), nullable=False, server_default="demo-clinic"),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("pickup_time", sa.String(20), nullable=False, server_default="09:00"),
            sa.Column("from_location", sa.String(255), nullable=False),
            sa.Column("destination", sa.String(255), nullable=False),
            sa.Column("status", sa.String(40), nullable=False, server_default="requested"),
            sa.Column("partner", sa.String(160), nullable=False, server_default="not assigned"),
            sa.Column("vehicle_notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("requested_by", sa.String(36), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_transport_clinic", "transport", ["clinic"])
        op.create_index("ix_transport_mother_id", "transport", ["mother_id"])

    if "expenses" not in existing_tables:
        op.create_table(
            "expenses",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("clinic", sa.String(80), nullable=False, server_default="demo-clinic"),
            sa.Column("category", sa.String(60), nullable=False),
            sa.Column("amount_paise", sa.Integer(), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("receipt_ref", sa.String(120), nullable=False, server_default=""),
            sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_by", sa.String(36), nullable=False, server_default=""),
            sa.Column("approved_by", sa.String(36), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_expenses_clinic", "expenses", ["clinic"])

    if "documents" not in existing_tables:
        op.create_table(
            "documents",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("mother_id", sa.String(36), sa.ForeignKey("mothers.id"), nullable=False),
            sa.Column("clinic", sa.String(80), nullable=False, server_default="demo-clinic"),
            sa.Column("filename", sa.String(200), nullable=False),
            sa.Column("content_type", sa.String(60), nullable=False, server_default="image/png"),
            sa.Column("extracted_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("structured_fields", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("uploaded_by", sa.String(36), nullable=False, server_default=""),
            sa.Column("confirmed_by", sa.String(36), nullable=False, server_default=""),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_documents_clinic", "documents", ["clinic"])
        op.create_index("ix_documents_mother_id", "documents", ["mother_id"])

    if "events" not in existing_tables:
        op.create_table(
            "events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("clinic", sa.String(80), nullable=False, server_default="demo-clinic"),
            sa.Column("actor", sa.String(36), nullable=False),
            sa.Column("actor_role", sa.String(40), nullable=False, server_default=""),
            sa.Column("action", sa.String(80), nullable=False),
            sa.Column("entity", sa.String(80), nullable=False),
            sa.Column("entity_id", sa.String(60), nullable=False),
            sa.Column("occurred", sa.DateTime(timezone=True), nullable=True),
            sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        )
        op.create_index("ix_events_clinic", "events", ["clinic"])


def downgrade() -> None:
    for table in [
        "events",
        "documents",
        "expenses",
        "transport",
        "messages",
        "tasks",
        "care_plans",
        "mothers",
        "staff",
    ]:
        op.drop_table(table)

