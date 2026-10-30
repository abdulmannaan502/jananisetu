"""Phase 3 ANC card digitisation, evidence-linked verification, document versioning, and token revocation.

Revision ID: 0002_phase3_anc_digitisation
Revises: 0001_phase2_foundation
Create Date: 2026-10-29 17:02:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002_phase3_anc_digitisation"
down_revision: Union[str, None] = "0001_phase2_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_col_if_missing(inspector, table_name: str, col_name: str, col: sa.Column) -> None:
    existing = {c["name"] for c in inspector.get_columns(table_name)}
    if col_name not in existing:
        op.add_column(table_name, col)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "staff" in existing_tables:
        _add_col_if_missing(
            inspector,
            "staff",
            "token_version",
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="1"),
        )

    if "mothers" in existing_tables:
        _add_col_if_missing(
            inspector,
            "mothers",
            "patient_identifier",
            sa.Column("patient_identifier", sa.String(80), nullable=False, server_default=""),
        )

    if "documents" in existing_tables:
        doc_cols = [
            ("version_number", sa.Column("version_number", sa.Integer(), nullable=False, server_default="1")),
            ("supersedes_document_id", sa.Column("supersedes_document_id", sa.String(36), nullable=True)),
            ("stored_path", sa.Column("stored_path", sa.String(255), nullable=False, server_default="")),
            ("preview_path", sa.Column("preview_path", sa.String(255), nullable=False, server_default="")),
            ("file_size_bytes", sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0")),
            ("sha256_hash", sa.Column("sha256_hash", sa.String(64), nullable=False, server_default="")),
            ("image_width", sa.Column("image_width", sa.Integer(), nullable=False, server_default="0")),
            ("image_height", sa.Column("image_height", sa.Integer(), nullable=False, server_default="0")),
            ("page_count", sa.Column("page_count", sa.Integer(), nullable=False, server_default="1")),
            ("ocr_status", sa.Column("ocr_status", sa.String(40), nullable=False, server_default="completed")),
            ("ocr_engine", sa.Column("ocr_engine", sa.String(60), nullable=False, server_default="tesseract-5")),
            ("ocr_error", sa.Column("ocr_error", sa.Text(), nullable=False, server_default="")),
            ("review_status", sa.Column("review_status", sa.String(40), nullable=False, server_default="pending_review")),
        ]
        for cname, cdef in doc_cols:
            _add_col_if_missing(inspector, "documents", cname, cdef)

    if "revoked_tokens" not in existing_tables:
        op.create_table(
            "revoked_tokens",
            sa.Column("jti", sa.String(64), primary_key=True),
            sa.Column("staff_id", sa.String(36), nullable=False),
            sa.Column("clinic", sa.String(80), nullable=False, server_default="demo-clinic"),
            sa.Column("reason", sa.String(100), nullable=False, server_default="logout"),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_revoked_tokens_staff_id", "revoked_tokens", ["staff_id"])

    if "ocr_jobs" not in existing_tables:
        op.create_table(
            "ocr_jobs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
            sa.Column("clinic", sa.String(80), nullable=False, server_default="demo-clinic"),
            sa.Column("engine", sa.String(60), nullable=False, server_default="tesseract-5"),
            sa.Column("external_provider_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("status", sa.String(40), nullable=False, server_default="succeeded"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("mean_confidence", sa.Float(), nullable=True),
            sa.Column("missing_fields_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("conflicts_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
            sa.Column("raw_tokens_json", sa.Text(), nullable=False, server_default="[]"),
        )
        op.create_index("ix_ocr_jobs_document_id", "ocr_jobs", ["document_id"])
        op.create_index("ix_ocr_jobs_clinic", "ocr_jobs", ["clinic"])

    if "extracted_fields" not in existing_tables:
        op.create_table(
            "extracted_fields",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
            sa.Column("ocr_job_id", sa.String(36), nullable=True),
            sa.Column("clinic", sa.String(80), nullable=False, server_default="demo-clinic"),
            sa.Column("field_key", sa.String(60), nullable=False),
            sa.Column("field_label", sa.String(120), nullable=False),
            sa.Column("extracted_value", sa.Text(), nullable=True),
            sa.Column("normalized_value", sa.Text(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("uncertainty_flag", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("uncertainty_reason", sa.String(255), nullable=False, server_default=""),
            sa.Column("conflict_detected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("conflicting_values_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("source_page", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("bbox_x", sa.Integer(), nullable=True),
            sa.Column("bbox_y", sa.Integer(), nullable=True),
            sa.Column("bbox_w", sa.Integer(), nullable=True),
            sa.Column("bbox_h", sa.Integer(), nullable=True),
            sa.Column("source_snippet", sa.Text(), nullable=False, server_default=""),
            sa.Column("verification_status", sa.String(40), nullable=False, server_default="unreviewed"),
            sa.Column("final_value", sa.Text(), nullable=True),
            sa.Column("reviewer_note", sa.Text(), nullable=False, server_default=""),
            sa.Column("verified_by", sa.String(36), nullable=False, server_default=""),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_extracted_fields_document_id", "extracted_fields", ["document_id"])
        op.create_index("ix_extracted_fields_clinic", "extracted_fields", ["clinic"])

    if "field_source_locations" not in existing_tables:
        op.create_table(
            "field_source_locations",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("extracted_field_id", sa.String(36), sa.ForeignKey("extracted_fields.id"), nullable=False),
            sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
            sa.Column("clinic", sa.String(80), nullable=False, server_default="demo-clinic"),
            sa.Column("page_number", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("x", sa.Integer(), nullable=False),
            sa.Column("y", sa.Integer(), nullable=False),
            sa.Column("width", sa.Integer(), nullable=False),
            sa.Column("height", sa.Integer(), nullable=False),
            sa.Column("token_text", sa.String(200), nullable=False, server_default=""),
            sa.Column("token_confidence", sa.Float(), nullable=False, server_default="0"),
        )
        op.create_index("ix_field_source_locations_field_id", "field_source_locations", ["extracted_field_id"])
        op.create_index("ix_field_source_locations_document_id", "field_source_locations", ["document_id"])
        op.create_index("ix_field_source_locations_clinic", "field_source_locations", ["clinic"])

    if "verification_decisions" not in existing_tables:
        op.create_table(
            "verification_decisions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
            sa.Column("extracted_field_id", sa.String(36), nullable=True),
            sa.Column("clinic", sa.String(80), nullable=False, server_default="demo-clinic"),
            sa.Column("field_key", sa.String(60), nullable=False),
            sa.Column("decision", sa.String(40), nullable=False),
            sa.Column("extracted_value", sa.Text(), nullable=True),
            sa.Column("final_value", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("decided_by", sa.String(36), nullable=False),
            sa.Column("decided_by_role", sa.String(40), nullable=False, server_default=""),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_verification_decisions_document_id", "verification_decisions", ["document_id"])
        op.create_index("ix_verification_decisions_clinic", "verification_decisions", ["clinic"])

    if "document_versions" not in existing_tables:
        op.create_table(
            "document_versions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("mother_id", sa.String(36), sa.ForeignKey("mothers.id"), nullable=False),
            sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
            sa.Column("clinic", sa.String(80), nullable=False, server_default="demo-clinic"),
            sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("previous_document_id", sa.String(36), nullable=True),
            sa.Column("confirmed_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("diff_summary_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_by", sa.String(36), nullable=False, server_default=""),
            sa.Column("confirmed_by", sa.String(36), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_document_versions_mother_id", "document_versions", ["mother_id"])
        op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])
        op.create_index("ix_document_versions_clinic", "document_versions", ["clinic"])

    if "admin_change_proposals" not in existing_tables:
        op.create_table(
            "admin_change_proposals",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("mother_id", sa.String(36), sa.ForeignKey("mothers.id"), nullable=False),
            sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
            sa.Column("clinic", sa.String(80), nullable=False, server_default="demo-clinic"),
            sa.Column("field_key", sa.String(60), nullable=False),
            sa.Column("previous_value", sa.Text(), nullable=True),
            sa.Column("proposed_value", sa.Text(), nullable=False),
            sa.Column("proposal_type", sa.String(50), nullable=False, server_default="mother_profile_update"),
            sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
            sa.Column("reviewed_by", sa.String(36), nullable=True),
            sa.Column("reviewed_by_role", sa.String(40), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=False, server_default=""),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_admin_change_proposals_mother_id", "admin_change_proposals", ["mother_id"])
        op.create_index("ix_admin_change_proposals_document_id", "admin_change_proposals", ["document_id"])
        op.create_index("ix_admin_change_proposals_clinic", "admin_change_proposals", ["clinic"])


def downgrade() -> None:
    for tbl in [
        "admin_change_proposals",
        "document_versions",
        "verification_decisions",
        "field_source_locations",
        "extracted_fields",
        "ocr_jobs",
        "revoked_tokens",
    ]:
        op.drop_table(tbl)

