"""Phase 6: Government contracts, programme budgets, healthcare payroll, transport expenses,
service-to-funding evidence chains, and financial accountability ledger.

Revision ID: 0005_phase6_contracts_budgets_payroll_finance
Revises: 0004_phase5_workforce_operations_governance
Create Date: 2026-10-29 19:35:00
"""
from __future__ import annotations

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0005_phase6_contracts_budgets_payroll_finance"
down_revision: Union[str, None] = "0004_phase5_workforce_operations_governance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(inspector, table_name: str, col_name: str) -> bool:
    return any(c["name"] == col_name for c in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "expenses" in existing_tables:
        exp_cols = [
            ("contract_id", sa.Column("contract_id", sa.String(36), nullable=True)),
            ("budget_id", sa.Column("budget_id", sa.String(36), nullable=True)),
            ("expense_claim_id", sa.Column("expense_claim_id", sa.String(36), nullable=True)),
            ("payroll_run_id", sa.Column("payroll_run_id", sa.String(36), nullable=True)),
            ("funding_claim_id", sa.Column("funding_claim_id", sa.String(36), nullable=True)),
            ("reimbursement_status", sa.Column("reimbursement_status", sa.String(40), server_default="unclaimed")),
            ("payment_ref", sa.Column("payment_ref", sa.String(120), server_default="")),
        ]
        for col_name, col_obj in exp_cols:
            if not _has_column(inspector, "expenses", col_name):
                op.add_column("expenses", col_obj)

    if "funding_organisations" not in existing_tables:
        op.create_table(
            "funding_organisations",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("name", sa.String(180), nullable=False),
            sa.Column("funder_type", sa.String(50), server_default="nhm_authority"),
            sa.Column("registration_or_grant_code", sa.String(100), server_default=""),
            sa.Column("nodal_officer_name", sa.String(140), server_default=""),
            sa.Column("nodal_officer_designation", sa.String(140), server_default=""),
            sa.Column("contact_email", sa.String(160), server_default=""),
            sa.Column("contact_phone", sa.String(24), server_default=""),
            sa.Column("address", sa.String(255), server_default=""),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
            sa.Column("created_by", sa.String(36), server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_funding_organisations_clinic", "funding_organisations", ["clinic"])

    if "programme_contracts" not in existing_tables:
        op.create_table(
            "programme_contracts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("funder_id", sa.String(36), sa.ForeignKey("funding_organisations.id"), nullable=False),
            sa.Column("programme_name", sa.String(200), nullable=False),
            sa.Column("contract_reference", sa.String(100), nullable=False),
            sa.Column("sanction_order_ref", sa.String(120), server_default=""),
            sa.Column("state", sa.String(40), server_default="draft"),
            sa.Column("is_simulated_approval", sa.Boolean(), server_default=sa.text("true")),
            sa.Column(
                "approval_disclaimer",
                sa.String(300),
                server_default="DRAFT PROPOSAL — Not an approved government or institutional sanction order.",
            ),
            sa.Column("funder_signatory_name", sa.String(140), server_default=""),
            sa.Column("funder_signatory_designation", sa.String(140), server_default=""),
            sa.Column("recipient_signatory_name", sa.String(140), server_default=""),
            sa.Column("signed_agreement_filename", sa.String(200), server_default=""),
            sa.Column("signed_agreement_sha256", sa.String(64), server_default=""),
            sa.Column("signed_agreement_stored_path", sa.String(255), server_default=""),
            sa.Column("effective_from", sa.Date(), nullable=False),
            sa.Column("effective_until", sa.Date(), nullable=False),
            sa.Column("funding_ceiling_paise", sa.Integer(), nullable=False),
            sa.Column("funding_received_paise", sa.Integer(), server_default="0"),
            sa.Column("funder_share_bps", sa.Integer(), server_default="10000"),
            sa.Column("reimbursement_basis", sa.String(50), server_default="actual_verified_cost"),
            sa.Column("allow_private_transport_reimbursement", sa.Boolean(), server_default=sa.text("false")),
            sa.Column("objectives_json", sa.Text(), server_default="[]"),
            sa.Column("delivery_obligations_json", sa.Text(), server_default="[]"),
            sa.Column(
                "allowed_categories_json",
                sa.Text(),
                server_default='["salary","travel","transport","clinical_services","diagnostics","technology","administration"]',
            ),
            sa.Column(
                "disallowed_categories_json",
                sa.Text(),
                server_default='["private_unapproved_transport","entertainment","unverified_cash"]',
            ),
            sa.Column("participating_clinics_json", sa.Text(), server_default='["demo-clinic"]'),
            sa.Column("clinic_allocations_json", sa.Text(), server_default="{}"),
            sa.Column("version_number", sa.Integer(), server_default="1"),
            sa.Column("submitted_by", sa.String(36), nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("approved_by", sa.String(36), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("approval_evidence_ref", sa.String(200), server_default=""),
            sa.Column("created_by", sa.String(36), server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_programme_contracts_clinic", "programme_contracts", ["clinic"])
        op.create_index("ix_programme_contracts_funder", "programme_contracts", ["funder_id"])
        op.create_index("ix_programme_contracts_state", "programme_contracts", ["state"])

    if "contract_milestones" not in existing_tables:
        op.create_table(
            "contract_milestones",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("contract_id", sa.String(36), sa.ForeignKey("programme_contracts.id"), nullable=False),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("milestone_name", sa.String(180), nullable=False),
            sa.Column("due_date", sa.Date(), nullable=False),
            sa.Column("deliverable_obligation", sa.String(300), server_default=""),
            sa.Column("tranche_amount_paise", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(40), server_default="pending"),
            sa.Column("received_amount_paise", sa.Integer(), server_default="0"),
            sa.Column("payment_reference", sa.String(120), server_default=""),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("verified_by", sa.String(36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_contract_milestones_contract", "contract_milestones", ["contract_id"])
        op.create_index("ix_contract_milestones_clinic", "contract_milestones", ["clinic"])

    if "contract_amendments" not in existing_tables:
        op.create_table(
            "contract_amendments",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("contract_id", sa.String(36), sa.ForeignKey("programme_contracts.id"), nullable=False),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("version_number", sa.Integer(), server_default="2"),
            sa.Column("amendment_type", sa.String(50), server_default="extension"),
            sa.Column("previous_end_date", sa.Date(), nullable=True),
            sa.Column("new_end_date", sa.Date(), nullable=True),
            sa.Column("previous_ceiling_paise", sa.Integer(), nullable=True),
            sa.Column("new_ceiling_paise", sa.Integer(), nullable=True),
            sa.Column("amendment_summary", sa.Text(), nullable=False),
            sa.Column("approval_reference", sa.String(140), nullable=False),
            sa.Column("approved_by", sa.String(36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_contract_amendments_contract", "contract_amendments", ["contract_id"])
        op.create_index("ix_contract_amendments_clinic", "contract_amendments", ["clinic"])

    if "programme_budgets" not in existing_tables:
        op.create_table(
            "programme_budgets",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("contract_id", sa.String(36), sa.ForeignKey("programme_contracts.id"), nullable=False),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("budget_scope", sa.String(40), server_default="clinic_level"),
            sa.Column("target_clinic", sa.String(80), server_default="demo-clinic"),
            sa.Column("fiscal_year", sa.String(20), server_default="2026-27"),
            sa.Column("period_start", sa.Date(), nullable=False),
            sa.Column("period_end", sa.Date(), nullable=False),
            sa.Column("total_allocated_paise", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(40), server_default="approved"),
            sa.Column("version_number", sa.Integer(), server_default="1"),
            sa.Column("created_by", sa.String(36), server_default=""),
            sa.Column("approved_by", sa.String(36), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_programme_budgets_clinic", "programme_budgets", ["clinic"])
        op.create_index("ix_programme_budgets_contract", "programme_budgets", ["contract_id"])

    if "budget_category_lines" not in existing_tables:
        op.create_table(
            "budget_category_lines",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("budget_id", sa.String(36), sa.ForeignKey("programme_budgets.id"), nullable=False),
            sa.Column("contract_id", sa.String(36), sa.ForeignKey("programme_contracts.id"), nullable=False),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("category", sa.String(50), nullable=False),
            sa.Column("allocated_paise", sa.Integer(), server_default="0"),
            sa.Column("committed_paise", sa.Integer(), server_default="0"),
            sa.Column("incurred_paise", sa.Integer(), server_default="0"),
            sa.Column("approved_paise", sa.Integer(), server_default="0"),
            sa.Column("paid_paise", sa.Integer(), server_default="0"),
            sa.Column("reimbursed_paise", sa.Integer(), server_default="0"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_budget_category_lines_budget", "budget_category_lines", ["budget_id"])
        op.create_index("ix_budget_category_lines_clinic", "budget_category_lines", ["clinic"])
        op.create_index("ix_budget_category_lines_unique_cat", "budget_category_lines", ["budget_id", "category"], unique=True)

    if "budget_amendment_logs" not in existing_tables:
        op.create_table(
            "budget_amendment_logs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("budget_id", sa.String(36), sa.ForeignKey("programme_budgets.id"), nullable=False),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("version_number", sa.Integer(), server_default="2"),
            sa.Column("category", sa.String(50), nullable=False),
            sa.Column("old_allocated_paise", sa.Integer(), nullable=False),
            sa.Column("new_allocated_paise", sa.Integer(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("approval_reference", sa.String(120), nullable=False),
            sa.Column("requested_by", sa.String(36), nullable=False),
            sa.Column("approved_by", sa.String(36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_budget_amendment_logs_budget", "budget_amendment_logs", ["budget_id"])
        op.create_index("ix_budget_amendment_logs_clinic", "budget_amendment_logs", ["clinic"])

    if "payroll_statutory_configs" not in existing_tables:
        op.create_table(
            "payroll_statutory_configs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("version_number", sa.Integer(), server_default="1"),
            sa.Column("config_name", sa.String(160), nullable=False),
            sa.Column("effective_from", sa.Date(), nullable=False),
            sa.Column("pf_employee_bps", sa.Integer(), server_default="0"),
            sa.Column("pf_employer_bps", sa.Integer(), server_default="0"),
            sa.Column("pf_wage_ceiling_paise", sa.Integer(), server_default="1500000"),
            sa.Column("esi_employee_bps", sa.Integer(), server_default="0"),
            sa.Column("esi_employer_bps", sa.Integer(), server_default="0"),
            sa.Column("esi_wage_ceiling_paise", sa.Integer(), server_default="2100000"),
            sa.Column("professional_tax_paise", sa.Integer(), server_default="0"),
            sa.Column("tds_default_bps", sa.Integer(), server_default="0"),
            sa.Column("validated_by_professional_name", sa.String(140), nullable=False),
            sa.Column("validated_by_credentials", sa.String(140), nullable=False),
            sa.Column("validation_notes", sa.Text(), server_default=""),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
            sa.Column("created_by", sa.String(36), server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_payroll_statutory_configs_clinic", "payroll_statutory_configs", ["clinic"])

    if "staff_compensation_agreements" not in existing_tables:
        op.create_table(
            "staff_compensation_agreements",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("staff_id", sa.String(36), sa.ForeignKey("staff.id"), nullable=False),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("contract_id", sa.String(36), nullable=True),
            sa.Column("budget_id", sa.String(36), nullable=True),
            sa.Column("employment_type", sa.String(50), server_default="full_time_employee"),
            sa.Column("pay_structure", sa.String(40), server_default="monthly_fixed"),
            sa.Column("base_monthly_paise", sa.Integer(), server_default="0"),
            sa.Column("per_shift_rate_paise", sa.Integer(), server_default="0"),
            sa.Column("per_visit_rate_paise", sa.Integer(), server_default="0"),
            sa.Column("field_allowance_paise", sa.Integer(), server_default="0"),
            sa.Column("expected_monthly_days", sa.Integer(), server_default="26"),
            sa.Column("attendance_adjustment_permitted", sa.Boolean(), server_default=sa.text("false")),
            sa.Column("statutory_deductions_enabled", sa.Boolean(), server_default=sa.text("true")),
            sa.Column("effective_from", sa.Date(), nullable=False),
            sa.Column("effective_until", sa.Date(), nullable=True),
            sa.Column("status", sa.String(30), server_default="active"),
            sa.Column("version_number", sa.Integer(), server_default="1"),
            sa.Column("approved_by", sa.String(36), server_default=""),
            sa.Column("created_by", sa.String(36), server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_staff_compensation_agreements_staff", "staff_compensation_agreements", ["staff_id"])
        op.create_index("ix_staff_compensation_agreements_clinic", "staff_compensation_agreements", ["clinic"])

    if "payroll_runs" not in existing_tables:
        op.create_table(
            "payroll_runs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("period_month", sa.String(7), nullable=False),
            sa.Column("contract_id", sa.String(36), nullable=True),
            sa.Column("budget_id", sa.String(36), nullable=True),
            sa.Column("statutory_config_id", sa.String(36), nullable=True),
            sa.Column("status", sa.String(40), server_default="draft"),
            sa.Column("total_gross_paise", sa.Integer(), server_default="0"),
            sa.Column("total_deductions_paise", sa.Integer(), server_default="0"),
            sa.Column("total_employer_contributions_paise", sa.Integer(), server_default="0"),
            sa.Column("total_reimbursements_paise", sa.Integer(), server_default="0"),
            sa.Column("total_net_payable_paise", sa.Integer(), server_default="0"),
            sa.Column("payslip_count", sa.Integer(), server_default="0"),
            sa.Column("calculated_by", sa.String(36), server_default=""),
            sa.Column("reviewed_by", sa.String(36), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("approved_by", sa.String(36), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("locked_by", sa.String(36), nullable=True),
            sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("payment_batch_ref", sa.String(120), server_default=""),
            sa.Column("payment_evidence_ref", sa.String(200), server_default=""),
            sa.Column("paid_confirmed_by", sa.String(36), nullable=True),
            sa.Column("paid_confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expense_id", sa.String(36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_payroll_runs_clinic_month", "payroll_runs", ["clinic", "period_month"])

    if "payslip_records" not in existing_tables:
        op.create_table(
            "payslip_records",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("payroll_run_id", sa.String(36), sa.ForeignKey("payroll_runs.id"), nullable=False),
            sa.Column("staff_id", sa.String(36), sa.ForeignKey("staff.id"), nullable=False),
            sa.Column("agreement_id", sa.String(36), sa.ForeignKey("staff_compensation_agreements.id"), nullable=False),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("period_month", sa.String(7), nullable=False),
            sa.Column("employment_type", sa.String(50), server_default="full_time_employee"),
            sa.Column("pay_structure", sa.String(40), server_default="monthly_fixed"),
            sa.Column("days_scheduled", sa.Integer(), server_default="0"),
            sa.Column("days_attended", sa.Integer(), server_default="0"),
            sa.Column("approved_leave_days", sa.Integer(), server_default="0"),
            sa.Column("unexcused_absent_days", sa.Integer(), server_default="0"),
            sa.Column("completed_visits_count", sa.Integer(), server_default="0"),
            sa.Column("base_pay_paise", sa.Integer(), server_default="0"),
            sa.Column("visit_or_shift_pay_paise", sa.Integer(), server_default="0"),
            sa.Column("allowance_paise", sa.Integer(), server_default="0"),
            sa.Column("attendance_deduction_paise", sa.Integer(), server_default="0"),
            sa.Column("gross_earnings_paise", sa.Integer(), server_default="0"),
            sa.Column("pf_employee_paise", sa.Integer(), server_default="0"),
            sa.Column("esi_employee_paise", sa.Integer(), server_default="0"),
            sa.Column("professional_tax_paise", sa.Integer(), server_default="0"),
            sa.Column("tds_paise", sa.Integer(), server_default="0"),
            sa.Column("total_deductions_paise", sa.Integer(), server_default="0"),
            sa.Column("pf_employer_paise", sa.Integer(), server_default="0"),
            sa.Column("esi_employer_paise", sa.Integer(), server_default="0"),
            sa.Column("approved_reimbursements_paise", sa.Integer(), server_default="0"),
            sa.Column("net_payable_paise", sa.Integer(), server_default="0"),
            sa.Column("status", sa.String(40), server_default="draft"),
            sa.Column("payment_ref", sa.String(120), server_default=""),
            sa.Column("payment_evidence_ref", sa.String(200), server_default=""),
            sa.Column("version_number", sa.Integer(), server_default="1"),
            sa.Column("correction_note", sa.Text(), server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_payslip_records_unique_staff_month",
            "payslip_records",
            ["clinic", "period_month", "staff_id"],
            unique=True,
        )
        op.create_index("ix_payslip_records_run", "payslip_records", ["payroll_run_id"])

    if "expense_policy_rules" not in existing_tables:
        op.create_table(
            "expense_policy_rules",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("contract_id", sa.String(36), nullable=True),
            sa.Column("policy_name", sa.String(160), nullable=False),
            sa.Column("claim_type", sa.String(50), server_default="staff_travel_claim"),
            sa.Column("rate_basis", sa.String(40), server_default="per_km_mileage"),
            sa.Column("per_km_rate_paise", sa.Integer(), server_default="0"),
            sa.Column("fixed_allowance_paise", sa.Integer(), server_default="0"),
            sa.Column("max_single_claim_paise", sa.Integer(), server_default="500000"),
            sa.Column("requires_receipt_above_paise", sa.Integer(), server_default="10000"),
            sa.Column("allow_private_transport", sa.Boolean(), server_default=sa.text("false")),
            sa.Column("effective_from", sa.Date(), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
            sa.Column("approved_by", sa.String(36), server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_expense_policy_rules_clinic", "expense_policy_rules", ["clinic"])

    if "expense_claims" not in existing_tables:
        op.create_table(
            "expense_claims",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("contract_id", sa.String(36), nullable=True),
            sa.Column("budget_id", sa.String(36), nullable=True),
            sa.Column("policy_rule_id", sa.String(36), nullable=True),
            sa.Column("expense_id", sa.String(36), nullable=True),
            sa.Column("claim_type", sa.String(50), server_default="staff_travel_claim"),
            sa.Column("expense_category", sa.String(50), server_default="travel"),
            sa.Column("claimant_staff_id", sa.String(36), nullable=True),
            sa.Column("transport_partner_id", sa.String(36), nullable=True),
            sa.Column("partner_facility_id", sa.String(36), nullable=True),
            sa.Column("transport_trip_id", sa.String(36), nullable=True),
            sa.Column("field_visit_id", sa.String(36), nullable=True),
            sa.Column("service_request_id", sa.String(36), nullable=True),
            sa.Column("referral_id", sa.String(36), nullable=True),
            sa.Column("transport_mode", sa.String(50), server_default="empaneled_partner_van"),
            sa.Column("distance_km", sa.Integer(), server_default="0"),
            sa.Column("amount_paise", sa.Integer(), nullable=False),
            sa.Column("receipt_number", sa.String(120), nullable=False),
            sa.Column("receipt_filename", sa.String(200), server_default="receipt.pdf"),
            sa.Column("receipt_sha256", sa.String(64), server_default=""),
            sa.Column("receipt_verified", sa.Boolean(), server_default=sa.text("false")),
            sa.Column("description", sa.Text(), server_default=""),
            sa.Column("status", sa.String(40), server_default="submitted"),
            sa.Column("submitted_by", sa.String(36), nullable=False),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("verified_by", sa.String(36), nullable=True),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("verification_notes", sa.Text(), server_default=""),
            sa.Column("approved_by", sa.String(36), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("approval_notes", sa.Text(), server_default=""),
            sa.Column("rejection_or_return_reason", sa.Text(), server_default=""),
            sa.Column("reimbursement_payment_ref", sa.String(120), server_default=""),
            sa.Column("reimbursed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("version_number", sa.Integer(), server_default="1"),
        )
        op.create_index("ix_expense_claims_clinic", "expense_claims", ["clinic"])
        op.create_index("ix_expense_claims_status", "expense_claims", ["status"])
        op.create_index("ix_expense_claims_receipt", "expense_claims", ["clinic", "receipt_number"])

    if "funding_claims" not in existing_tables:
        op.create_table(
            "funding_claims",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("contract_id", sa.String(36), sa.ForeignKey("programme_contracts.id"), nullable=False),
            sa.Column("budget_id", sa.String(36), sa.ForeignKey("programme_budgets.id"), nullable=False),
            sa.Column("milestone_id", sa.String(36), nullable=True),
            sa.Column("claim_reference", sa.String(100), nullable=False),
            sa.Column("period_start", sa.Date(), nullable=False),
            sa.Column("period_end", sa.Date(), nullable=False),
            sa.Column("total_claimed_paise", sa.Integer(), server_default="0"),
            sa.Column("funder_reimbursable_paise", sa.Integer(), server_default="0"),
            sa.Column("approved_reimbursed_paise", sa.Integer(), server_default="0"),
            sa.Column("status", sa.String(40), server_default="draft"),
            sa.Column("evidence_package_hash", sa.String(64), server_default=""),
            sa.Column("submitted_by", sa.String(36), server_default=""),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("settled_payment_ref", sa.String(120), server_default=""),
            sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notes", sa.Text(), server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_funding_claims_clinic", "funding_claims", ["clinic"])
        op.create_index("ix_funding_claims_contract", "funding_claims", ["contract_id"])
        op.create_index("ix_funding_claims_ref", "funding_claims", ["clinic", "claim_reference"], unique=True)

    if "service_funding_evidence_links" not in existing_tables:
        op.create_table(
            "service_funding_evidence_links",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("funding_claim_id", sa.String(36), sa.ForeignKey("funding_claims.id"), nullable=False),
            sa.Column("contract_id", sa.String(36), sa.ForeignKey("programme_contracts.id"), nullable=False),
            sa.Column("budget_id", sa.String(36), sa.ForeignKey("programme_budgets.id"), nullable=False),
            sa.Column("service_category", sa.String(50), nullable=False),
            sa.Column("staff_id", sa.String(36), nullable=True),
            sa.Column("provider_entity_id", sa.String(36), nullable=True),
            sa.Column("service_request_id", sa.String(36), nullable=True),
            sa.Column("field_visit_id", sa.String(36), nullable=True),
            sa.Column("transport_trip_id", sa.String(36), nullable=True),
            sa.Column("referral_id", sa.String(36), nullable=True),
            sa.Column("expense_id", sa.String(36), sa.ForeignKey("expenses.id"), nullable=False),
            sa.Column("expense_claim_id", sa.String(36), nullable=True),
            sa.Column("payslip_id", sa.String(36), nullable=True),
            sa.Column("beneficiary_anonymised_ref", sa.String(80), server_default="SYN-BENEFICIARY"),
            sa.Column("verification_evidence_ref", sa.String(200), nullable=False),
            sa.Column("verified_by_staff_id", sa.String(36), nullable=False),
            sa.Column("amount_paise", sa.Integer(), nullable=False),
            sa.Column("reimbursable_paise", sa.Integer(), nullable=False),
            sa.Column("reimbursement_status", sa.String(40), server_default="linked"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_service_funding_evidence_claim", "service_funding_evidence_links", ["funding_claim_id"])
        op.create_index("ix_service_funding_evidence_clinic", "service_funding_evidence_links", ["clinic"])
        op.create_index(
            "ix_service_funding_evidence_unique_exp",
            "service_funding_evidence_links",
            ["clinic", "expense_id"],
            unique=True,
        )

    if "financial_audit_ledger" not in existing_tables:
        op.create_table(
            "financial_audit_ledger",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("idempotency_key", sa.String(120), nullable=True, unique=True),
            sa.Column("entity_type", sa.String(60), nullable=False),
            sa.Column("entity_id", sa.String(60), nullable=False),
            sa.Column("action", sa.String(80), nullable=False),
            sa.Column("previous_state", sa.String(50), server_default=""),
            sa.Column("new_state", sa.String(50), server_default=""),
            sa.Column("amount_paise", sa.Integer(), server_default="0"),
            sa.Column("actor_id", sa.String(36), nullable=False),
            sa.Column("actor_role", sa.String(40), nullable=False),
            sa.Column("detail", sa.Text(), server_default=""),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_financial_audit_ledger_clinic", "financial_audit_ledger", ["clinic"])
        op.create_index("ix_financial_audit_ledger_entity", "financial_audit_ledger", ["entity_type", "entity_id"])
        op.create_index("ix_financial_audit_ledger_idem", "financial_audit_ledger", ["idempotency_key"], unique=True)

    if "financial_correction_records" not in existing_tables:
        op.create_table(
            "financial_correction_records",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("clinic", sa.String(80), server_default="demo-clinic", nullable=False),
            sa.Column("entity_type", sa.String(60), nullable=False),
            sa.Column("entity_id", sa.String(60), nullable=False),
            sa.Column("version_number", sa.Integer(), server_default="2"),
            sa.Column("field_name", sa.String(80), nullable=False),
            sa.Column("previous_value_paise", sa.Integer(), nullable=True),
            sa.Column("new_value_paise", sa.Integer(), nullable=True),
            sa.Column("previous_text", sa.Text(), server_default=""),
            sa.Column("new_text", sa.Text(), server_default=""),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("requested_by", sa.String(36), nullable=False),
            sa.Column("approved_by", sa.String(36), nullable=False),
            sa.Column("approved_by_role", sa.String(40), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_financial_correction_records_clinic", "financial_correction_records", ["clinic"])
        op.create_index("ix_financial_correction_records_entity", "financial_correction_records", ["entity_type", "entity_id"])


def downgrade() -> None:
    for tbl in [
        "financial_correction_records",
        "financial_audit_ledger",
        "service_funding_evidence_links",
        "funding_claims",
        "expense_claims",
        "expense_policy_rules",
        "payslip_records",
        "payroll_runs",
        "staff_compensation_agreements",
        "payroll_statutory_configs",
        "budget_amendment_logs",
        "budget_category_lines",
        "programme_budgets",
        "contract_amendments",
        "contract_milestones",
        "programme_contracts",
        "funding_organisations",
    ]:
        op.drop_table(tbl)

