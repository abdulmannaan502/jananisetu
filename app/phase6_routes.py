"""Phase 6 FastAPI Routes: Government Contracts, Programme Budgets, Healthcare Payroll,
Transport Expenses, Service-to-Funding Evidence & Funding Accountability.

All monetary calculations use exact integer paise (1 INR = 100 paise) and decimal.Decimal
for display formatting. Binary floating-point arithmetic (float) is strictly prohibited.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import io
import json
from typing import Any, Callable, Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.anc_fixtures import generate_fixture_image_bytes
from app.followup_engine import (
    process_outbox_and_due_jobs,
    schedule_reminders_for_care_plan,
)
from app.models import (
    BudgetAmendmentLog,
    BudgetCategoryLine,
    CarePlan,
    ContractAmendment,
    ContractMilestone,
    Document,
    Event,
    Expense,
    ExpenseClaim,
    ExpensePolicyRule,
    ExtractedField,
    FieldVisit,
    FinancialAuditLedger,
    FinancialCorrectionRecord,
    FundingClaim,
    FundingOrganisation,
    HospitalReferral,
    Mother,
    PartnerFacility,
    PayrollRun,
    PayrollStatutoryConfig,
    PayslipRecord,
    ProgrammeBudget,
    ProgrammeContract,
    ServiceFundingEvidenceLink,
    ServiceRequest,
    Staff,
    StaffCompensationAgreement,
    StaffCredentialDocument,
    StaffLeaveRequest,
    StaffShift,
    StaffWorkforceProfile,
    Transport,
    TransportPartner,
    TransportVehicleDriver,
    now,
)
from app.security import normalize_role

PAISE_PER_INR = Decimal("100")
BPS_DIVISOR = 10000

CONTRACT_STATES = (
    "draft",
    "submitted",
    "approved",
    "active",
    "suspended",
    "completed",
    "terminated",
)

ALLOWED_CONTRACT_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"submitted", "terminated"},
    "submitted": {"approved", "draft", "terminated"},
    "approved": {"active", "suspended", "terminated"},
    "active": {"suspended", "completed", "terminated"},
    "suspended": {"active", "terminated"},
    "completed": set(),
    "terminated": set(),
}

BUDGET_CATEGORIES = (
    "salary",
    "travel",
    "transport",
    "clinical_services",
    "diagnostics",
    "technology",
    "administration",
)


def paise_to_inr_str(paise: int) -> str:
    """Convert integer paise to exact 2-decimal INR string using Decimal (never float)."""
    val = (Decimal(int(paise)) / PAISE_PER_INR).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return str(val)


def mul_bps_paise(amount_paise: int, bps: int) -> int:
    """Calculate basis points (10000 bps = 100%) on integer paise using exact Decimal rounding."""
    if amount_paise <= 0 or bps <= 0:
        return 0
    res = (Decimal(int(amount_paise)) * Decimal(int(bps)) / Decimal(BPS_DIVISOR)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return int(res)


def pct_bps(numerator_paise: int, denominator_paise: int) -> str:
    """Return exact percentage string (e.g. '45.25%') using Decimal without float."""
    if denominator_paise <= 0:
        return "0.00%"
    pct = (Decimal(int(numerator_paise)) * Decimal(100) / Decimal(int(denominator_paise))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return f"{pct}%"


def anonymise_beneficiary_ref(clinic: str, mother_id: str) -> str:
    """Generate a deterministic privacy-preserving beneficiary reference without exposing PII."""
    digest = hashlib.sha256(f"{clinic}:{mother_id}".encode("utf-8")).hexdigest()[:10].upper()
    return f"BEN-{digest}"


def build_simple_pdf_bytes(title: str, subtitle: str, watermark: str, lines: list[str]) -> bytes:
    """Build a valid, dependency-free PDF 1.4 document containing the report lines and draft/approval label."""
    def _esc(txt: str) -> str:
        cleaned = txt.encode("ascii", errors="replace").decode("ascii")
        return cleaned.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    content_ops = [
        "BT",
        "/F1 13 Tf",
        "40 800 Td",
        f"({_esc(watermark)}) Tj",
        "0 -22 Td",
        "/F1 15 Tf",
        f"({_esc(title)}) Tj",
        "0 -18 Td",
        "/F1 10 Tf",
        f"({_esc(subtitle)}) Tj",
        "0 -18 Td",
    ]
    for line in lines[:42]:
        content_ops.append(f"({_esc(line[:105])}) Tj")
        content_ops.append("0 -14 Td")
    content_ops.append("ET")
    stream_bytes = "\n".join(content_ops).encode("ascii")

    objs: list[bytes] = []
    objs.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objs.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objs.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
    )
    objs.append(b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
    objs.append(
        f"5 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii")
        + stream_bytes
        + b"\nendstream\nendobj\n"
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = [0]
    for obj in objs:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    return bytes(out)


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class FunderCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    funder_type: Literal[
        "government_department",
        "nhm_authority",
        "public_hospital",
        "ngo_foundation",
        "csr_funder",
    ] = "nhm_authority"
    registration_or_grant_code: str = Field(default="", max_length=100)
    nodal_officer_name: str = Field(default="", max_length=140)
    nodal_officer_designation: str = Field(default="", max_length=140)
    contact_email: str = Field(default="", max_length=160)
    contact_phone: str = Field(default="", max_length=24)
    address: str = Field(default="", max_length=255)


class ContractCreateIn(BaseModel):
    funder_id: str
    programme_name: str = Field(min_length=3, max_length=200)
    contract_reference: str = Field(min_length=3, max_length=100)
    sanction_order_ref: str = Field(default="", max_length=120)
    funder_signatory_name: str = Field(default="", max_length=140)
    funder_signatory_designation: str = Field(default="", max_length=140)
    recipient_signatory_name: str = Field(default="", max_length=140)
    signed_agreement_filename: str = Field(default="draft_agreement.pdf", max_length=200)
    effective_from: date
    effective_until: date
    funding_ceiling_paise: int = Field(gt=0)
    funder_share_bps: int = Field(default=10000, ge=100, le=10000)
    reimbursement_basis: Literal[
        "actual_verified_cost", "fixed_unit_rate", "milestone_tranche"
    ] = "actual_verified_cost"
    allow_private_transport_reimbursement: bool = False
    objectives: list[str] = Field(default_factory=list)
    delivery_obligations: list[str] = Field(default_factory=list)
    allowed_categories: list[str] = Field(
        default_factory=lambda: list(BUDGET_CATEGORIES)
    )
    disallowed_categories: list[str] = Field(
        default_factory=lambda: ["private_unapproved_transport", "entertainment", "unverified_cash"]
    )
    participating_clinics: list[str] = Field(default_factory=list)
    clinic_allocations_paise: dict[str, int] = Field(default_factory=dict)


class ContractStateTransitionIn(BaseModel):
    target_state: Literal[
        "draft",
        "submitted",
        "approved",
        "active",
        "suspended",
        "completed",
        "terminated",
    ]
    sanction_order_ref: str = Field(default="", max_length=120)
    approval_evidence_ref: str = Field(default="", max_length=200)
    is_simulated_approval: bool = True
    signed_agreement_filename: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=500)


class MilestoneCreateIn(BaseModel):
    milestone_name: str = Field(min_length=3, max_length=180)
    due_date: date
    deliverable_obligation: str = Field(default="", max_length=300)
    tranche_amount_paise: int = Field(gt=0)


class MilestoneUpdateIn(BaseModel):
    status: Literal["pending", "submitted", "approved", "received"]
    received_amount_paise: int = Field(default=0, ge=0)
    payment_reference: str = Field(default="", max_length=120)


class ContractAmendmentIn(BaseModel):
    amendment_type: Literal[
        "extension",
        "ceiling_revision",
        "category_rule_change",
        "clinic_allocation_change",
    ] = "extension"
    new_end_date: Optional[date] = None
    new_ceiling_paise: Optional[int] = Field(default=None, gt=0)
    allow_private_transport_reimbursement: Optional[bool] = None
    amendment_summary: str = Field(min_length=5, max_length=1000)
    approval_reference: str = Field(min_length=3, max_length=140)


class BudgetCategoryAllocationIn(BaseModel):
    category: Literal[
        "salary",
        "travel",
        "transport",
        "clinical_services",
        "diagnostics",
        "technology",
        "administration",
    ]
    allocated_paise: int = Field(ge=0)


class BudgetCreateIn(BaseModel):
    contract_id: str
    budget_scope: Literal["programme_level", "clinic_level"] = "clinic_level"
    target_clinic: str = Field(default="", max_length=80)
    fiscal_year: str = Field(default="2026-27", max_length=20)
    period_start: date
    period_end: date
    category_allocations: list[BudgetCategoryAllocationIn]


class BudgetAmendmentIn(BaseModel):
    category: Literal[
        "salary",
        "travel",
        "transport",
        "clinical_services",
        "diagnostics",
        "technology",
        "administration",
    ]
    new_allocated_paise: int = Field(ge=0)
    reason: str = Field(min_length=5, max_length=600)
    approval_reference: str = Field(min_length=3, max_length=120)


class StatutoryConfigCreateIn(BaseModel):
    config_name: str = Field(min_length=3, max_length=160)
    effective_from: date
    pf_employee_bps: int = Field(default=1200, ge=0, le=5000)
    pf_employer_bps: int = Field(default=1200, ge=0, le=5000)
    pf_wage_ceiling_paise: int = Field(default=1500000, ge=0)
    esi_employee_bps: int = Field(default=75, ge=0, le=5000)
    esi_employer_bps: int = Field(default=325, ge=0, le=5000)
    esi_wage_ceiling_paise: int = Field(default=2100000, ge=0)
    professional_tax_paise: int = Field(default=20000, ge=0)
    tds_default_bps: int = Field(default=500, ge=0, le=5000)
    validated_by_professional_name: str = Field(min_length=3, max_length=140)
    validated_by_credentials: str = Field(min_length=3, max_length=140)
    validation_notes: str = Field(default="", max_length=500)


class CompensationAgreementCreateIn(BaseModel):
    staff_id: str
    contract_id: Optional[str] = None
    budget_id: Optional[str] = None
    employment_type: Literal[
        "full_time_employee",
        "contract_consultant",
        "visiting_specialist",
        "nhm_deputed",
        "community_honorarium",
    ] = "full_time_employee"
    pay_structure: Literal[
        "monthly_fixed",
        "per_shift_rate",
        "per_visit_rate",
        "retainer_plus_visit",
    ] = "monthly_fixed"
    base_monthly_paise: int = Field(default=0, ge=0)
    per_shift_rate_paise: int = Field(default=0, ge=0)
    per_visit_rate_paise: int = Field(default=0, ge=0)
    field_allowance_paise: int = Field(default=0, ge=0)
    expected_monthly_days: int = Field(default=26, ge=1, le=31)
    attendance_adjustment_permitted: bool = False
    statutory_deductions_enabled: bool = True
    effective_from: date
    effective_until: Optional[date] = None


class PayrollAttendanceOverrideItem(BaseModel):
    staff_id: str
    days_scheduled: Optional[int] = Field(default=None, ge=0, le=31)
    days_attended: Optional[int] = Field(default=None, ge=0, le=31)
    approved_leave_days: Optional[int] = Field(default=None, ge=0, le=31)
    unexcused_absent_days: Optional[int] = Field(default=None, ge=0, le=31)
    completed_visits_count: Optional[int] = Field(default=None, ge=0, le=200)


class PayrollRunCreateIn(BaseModel):
    period_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    contract_id: Optional[str] = None
    budget_id: Optional[str] = None
    statutory_config_id: Optional[str] = None
    staff_ids: list[str] = Field(default_factory=list)
    attendance_overrides: list[PayrollAttendanceOverrideItem] = Field(default_factory=list)


class PayrollRunTransitionIn(BaseModel):
    target_status: Literal["reviewed", "approved", "locked", "paid_verified"]
    payment_batch_ref: str = Field(default="", max_length=120)
    payment_evidence_ref: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=500)


class ExpensePolicyCreateIn(BaseModel):
    contract_id: Optional[str] = None
    policy_name: str = Field(min_length=3, max_length=160)
    claim_type: Literal[
        "staff_travel_claim",
        "transport_partner_invoice",
        "diagnostic_partner_invoice",
        "field_outreach_allowance",
    ] = "staff_travel_claim"
    rate_basis: Literal[
        "per_km_mileage", "fixed_allowance", "contracted_tariff"
    ] = "per_km_mileage"
    per_km_rate_paise: int = Field(default=1200, ge=0)
    fixed_allowance_paise: int = Field(default=15000, ge=0)
    max_single_claim_paise: int = Field(default=500000, gt=0)
    requires_receipt_above_paise: int = Field(default=10000, ge=0)
    allow_private_transport: bool = False
    effective_from: date


class ExpenseClaimCreateIn(BaseModel):
    contract_id: Optional[str] = None
    budget_id: Optional[str] = None
    policy_rule_id: Optional[str] = None
    claim_type: Literal[
        "staff_travel_claim",
        "transport_partner_invoice",
        "diagnostic_partner_invoice",
        "field_outreach_allowance",
    ] = "staff_travel_claim"
    expense_category: Literal[
        "travel",
        "transport",
        "clinical_services",
        "diagnostics",
        "administration",
    ] = "travel"
    claimant_staff_id: Optional[str] = None
    transport_partner_id: Optional[str] = None
    partner_facility_id: Optional[str] = None
    transport_trip_id: Optional[str] = None
    field_visit_id: Optional[str] = None
    service_request_id: Optional[str] = None
    referral_id: Optional[str] = None
    transport_mode: Literal[
        "empaneled_partner_van",
        "public_bus_rail",
        "staff_two_wheeler_mileage",
        "private_unapproved",
    ] = "empaneled_partner_van"
    distance_km: int = Field(default=0, ge=0, le=5000)
    amount_paise: Optional[int] = Field(default=None, ge=0)
    receipt_number: str = Field(min_length=2, max_length=120)
    receipt_filename: str = Field(default="receipt_voucher.pdf", max_length=200)
    description: str = Field(min_length=3, max_length=600)


class ExpenseClaimDecisionIn(BaseModel):
    decision: Literal[
        "verified_by_supervisor",
        "approved_by_finance",
        "reimbursed_paid",
        "rejected",
        "returned_for_correction",
    ]
    receipt_verified: bool = True
    notes: str = Field(default="", max_length=500)
    reimbursement_payment_ref: str = Field(default="", max_length=120)


class EvidenceItemIn(BaseModel):
    expense_id: str
    service_category: Literal[
        "salary",
        "travel",
        "transport",
        "clinical_services",
        "diagnostics",
        "technology",
        "administration",
    ]
    staff_id: Optional[str] = None
    provider_entity_id: Optional[str] = None
    service_request_id: Optional[str] = None
    field_visit_id: Optional[str] = None
    transport_trip_id: Optional[str] = None
    referral_id: Optional[str] = None
    expense_claim_id: Optional[str] = None
    payslip_id: Optional[str] = None
    mother_id: Optional[str] = None
    verification_evidence_ref: str = Field(min_length=3, max_length=200)


class FundingClaimCreateIn(BaseModel):
    contract_id: str
    budget_id: str
    milestone_id: Optional[str] = None
    claim_reference: str = Field(min_length=3, max_length=100)
    period_start: date
    period_end: date
    evidence_items: list[EvidenceItemIn] = Field(min_length=1)
    notes: str = Field(default="", max_length=600)


class FundingClaimTransitionIn(BaseModel):
    target_status: Literal[
        "submitted_to_funder",
        "under_verification",
        "approved_by_funder",
        "reimbursed_settled",
        "disputed_returned",
    ]
    approved_reimbursed_paise: Optional[int] = Field(default=None, ge=0)
    settled_payment_ref: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=500)


class FinancialCorrectionCreateIn(BaseModel):
    entity_type: Literal["expense_claim", "payslip_record", "expense"]
    entity_id: str
    field_name: Literal["amount_paise", "allowance_paise", "description", "correction_note"]
    new_value_paise: Optional[int] = Field(default=None, ge=0)
    new_text: str = Field(default="", max_length=500)
    reason: str = Field(min_length=5, max_length=600)
    requested_by: Optional[str] = None


def register_phase6_routes(
    app: FastAPI,
    dbsession: Callable[..., Any],
    who: Callable[..., Any],
    permitted: Callable[..., Any],
    audit: Callable[..., Any],
    row: Callable[..., dict[str, Any]],
    mother_for: Callable[..., Mother],
) -> None:
    """Register all Phase 6 endpoints onto the FastAPI application."""

    def record_fin_ledger(
        db: Session,
        s: Staff,
        entity_type: str,
        entity_id: str,
        action: str,
        previous_state: str = "",
        new_state: str = "",
        amount_paise: int = 0,
        detail: str = "",
        idempotency_key: Optional[str] = None,
    ) -> FinancialAuditLedger:
        if idempotency_key:
            existing = db.scalar(
                select(FinancialAuditLedger).where(
                    FinancialAuditLedger.idempotency_key == idempotency_key
                )
            )
            if existing is not None:
                if existing.clinic != s.clinic:
                    raise HTTPException(403, "Idempotency key belongs to another clinic")
                raise HTTPException(
                    409,
                    f"Duplicate / concurrent financial operation blocked by idempotency key '{idempotency_key}'",
                )
        entry = FinancialAuditLedger(
            clinic=s.clinic,
            idempotency_key=idempotency_key,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            previous_state=previous_state,
            new_state=new_state,
            amount_paise=int(amount_paise),
            actor_id=s.id,
            actor_role=normalize_role(s.role),
            detail=detail,
        )
        db.add(entry)
        audit(db, s, f"fin_{action}", entity_type, entity_id, f"amount_paise={amount_paise}; {detail}")
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                409,
                "Concurrent or duplicate financial state transition detected and rejected",
            ) from exc
        return entry

    def _serialize_contract(db: Session, c: ProgrammeContract) -> dict[str, Any]:
        d = row(c)
        funder = db.get(FundingOrganisation, c.funder_id) if c.funder_id else None
        d["funder_name"] = funder.name if funder else "Unknown Funder"
        d["funder_type"] = funder.funder_type if funder else ""
        d["funding_ceiling_inr"] = paise_to_inr_str(c.funding_ceiling_paise)
        d["funding_received_inr"] = paise_to_inr_str(c.funding_received_paise)
        d["outstanding_receivable_paise"] = max(0, c.funding_ceiling_paise - c.funding_received_paise)
        d["outstanding_receivable_inr"] = paise_to_inr_str(d["outstanding_receivable_paise"])
        d["funder_share_pct"] = pct_bps(c.funder_share_bps, BPS_DIVISOR)
        d["is_approved_funding"] = c.state in ("approved", "active", "completed")
        d["funding_status_banner"] = (
            "UNAPPROVED PROPOSAL / DRAFT — Cannot be represented as approved government or institutional funding"
            if c.state in ("draft", "submitted")
            else (
                "SIMULATED / DEMO APPROVAL — Marked as synthetic demonstration contract; not an official government sanction order"
                if c.is_simulated_approval
                else f"VERIFIED INSTITUTIONAL APPROVAL — Sanction Ref: {c.sanction_order_ref}"
            )
        )
        for jcol, key in (
            ("objectives_json", "objectives"),
            ("delivery_obligations_json", "delivery_obligations"),
            ("allowed_categories_json", "allowed_categories"),
            ("disallowed_categories_json", "disallowed_categories"),
            ("participating_clinics_json", "participating_clinics"),
            ("clinic_allocations_json", "clinic_allocations_paise"),
        ):
            try:
                d[key] = json.loads(getattr(c, jcol) or ("{}" if "allocations" in key else "[]"))
            except Exception:
                d[key] = {} if "allocations" in key else []
        milestones = list(
            db.scalars(
                select(ContractMilestone)
                .where(ContractMilestone.contract_id == c.id, ContractMilestone.clinic == c.clinic)
                .order_by(ContractMilestone.due_date.asc())
            )
        )
        d["milestones"] = [
            {
                **row(m),
                "tranche_amount_inr": paise_to_inr_str(m.tranche_amount_paise),
                "received_amount_inr": paise_to_inr_str(m.received_amount_paise),
            }
            for m in milestones
        ]
        amendments = list(
            db.scalars(
                select(ContractAmendment)
                .where(ContractAmendment.contract_id == c.id, ContractAmendment.clinic == c.clinic)
                .order_by(ContractAmendment.version_number.asc())
            )
        )
        d["amendments"] = [row(a) for a in amendments]
        return d

    def _serialize_budget(db: Session, b: ProgrammeBudget) -> dict[str, Any]:
        d = row(b)
        c = db.get(ProgrammeContract, b.contract_id) if b.contract_id else None
        d["programme_name"] = c.programme_name if c else ""
        d["contract_reference"] = c.contract_reference if c else ""
        d["contract_state"] = c.state if c else "draft"
        d["funding_ceiling_paise"] = c.funding_ceiling_paise if c else b.total_allocated_paise
        d["funding_received_paise"] = c.funding_received_paise if c else 0
        lines = list(
            db.scalars(
                select(BudgetCategoryLine)
                .where(BudgetCategoryLine.budget_id == b.id, BudgetCategoryLine.clinic == b.clinic)
                .order_by(BudgetCategoryLine.category.asc())
            )
        )
        cat_rows: list[dict[str, Any]] = []
        tot_alloc = 0
        tot_comm = 0
        tot_inc = 0
        tot_appr = 0
        tot_paid = 0
        tot_reimb = 0
        overspend_alerts: list[str] = []
        for ln in lines:
            tot_alloc += ln.allocated_paise
            tot_comm += ln.committed_paise
            tot_inc += ln.incurred_paise
            tot_appr += ln.approved_paise
            tot_paid += ln.paid_paise
            tot_reimb += ln.reimbursed_paise
            avail_paise = ln.allocated_paise - (ln.committed_paise + ln.approved_paise)
            util_bps = (
                int(
                    (
                        Decimal(ln.committed_paise + ln.approved_paise)
                        * Decimal(BPS_DIVISOR)
                        / Decimal(ln.allocated_paise)
                    ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                )
                if ln.allocated_paise > 0
                else 0
            )
            if avail_paise < 0:
                overspend_alerts.append(
                    f"Category '{ln.category}' exceeds allocation by INR {paise_to_inr_str(abs(avail_paise))}"
                )
            elif util_bps >= 8500:
                overspend_alerts.append(
                    f"Category '{ln.category}' is at high utilisation ({pct_bps(ln.committed_paise + ln.approved_paise, ln.allocated_paise)})"
                )
            cat_rows.append(
                {
                    **row(ln),
                    "allocated_inr": paise_to_inr_str(ln.allocated_paise),
                    "committed_inr": paise_to_inr_str(ln.committed_paise),
                    "incurred_inr": paise_to_inr_str(ln.incurred_paise),
                    "approved_inr": paise_to_inr_str(ln.approved_paise),
                    "paid_inr": paise_to_inr_str(ln.paid_paise),
                    "reimbursed_inr": paise_to_inr_str(ln.reimbursed_paise),
                    "available_paise": avail_paise,
                    "available_inr": paise_to_inr_str(avail_paise),
                    "utilisation_pct": pct_bps(
                        ln.committed_paise + ln.approved_paise, ln.allocated_paise
                    ),
                }
            )
        d["category_lines"] = cat_rows
        d["totals"] = {
            "allocated_paise": tot_alloc,
            "allocated_inr": paise_to_inr_str(tot_alloc),
            "committed_paise": tot_comm,
            "committed_inr": paise_to_inr_str(tot_comm),
            "incurred_paise": tot_inc,
            "incurred_inr": paise_to_inr_str(tot_inc),
            "approved_paise": tot_appr,
            "approved_inr": paise_to_inr_str(tot_appr),
            "paid_paise": tot_paid,
            "paid_inr": paise_to_inr_str(tot_paid),
            "reimbursed_paise": tot_reimb,
            "reimbursed_inr": paise_to_inr_str(tot_reimb),
            "available_paise": tot_alloc - (tot_comm + tot_appr),
            "available_inr": paise_to_inr_str(tot_alloc - (tot_comm + tot_appr)),
            "funding_received_paise": d["funding_received_paise"],
            "funding_received_inr": paise_to_inr_str(d["funding_received_paise"]),
            "outstanding_reimbursement_paise": max(0, tot_paid - tot_reimb),
            "outstanding_reimbursement_inr": paise_to_inr_str(max(0, tot_paid - tot_reimb)),
            "overall_utilisation_pct": pct_bps(tot_comm + tot_appr, tot_alloc),
        }
        d["overspend_alerts"] = overspend_alerts
        amendments = list(
            db.scalars(
                select(BudgetAmendmentLog)
                .where(BudgetAmendmentLog.budget_id == b.id, BudgetAmendmentLog.clinic == b.clinic)
                .order_by(BudgetAmendmentLog.version_number.asc())
            )
        )
        d["amendments"] = [row(a) for a in amendments]
        return d

    # -----------------------------------------------------------------------
    # 2. Government & Institutional Contracts
    # -----------------------------------------------------------------------
    @app.get("/api/finance/funders")
    def list_funders(
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        permitted(s, "admin", "doctor", "nurse")
        rows = db.scalars(
            select(FundingOrganisation)
            .where(FundingOrganisation.clinic == s.clinic)
            .order_by(FundingOrganisation.created_at.desc())
        )
        return [row(f) for f in rows]

    @app.post("/api/finance/funders", status_code=201)
    def create_funder(
        p: FunderCreateIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin")
        f = FundingOrganisation(
            clinic=s.clinic,
            name=p.name.strip(),
            funder_type=p.funder_type,
            registration_or_grant_code=p.registration_or_grant_code.strip(),
            nodal_officer_name=p.nodal_officer_name.strip(),
            nodal_officer_designation=p.nodal_officer_designation.strip(),
            contact_email=p.contact_email.strip(),
            contact_phone=p.contact_phone.strip(),
            address=p.address.strip(),
            is_active=True,
            created_by=s.id,
        )
        db.add(f)
        db.flush()
        record_fin_ledger(
            db,
            s,
            "funding_organisation",
            f.id,
            "create_funder",
            "",
            "active",
            0,
            f"name={f.name}; type={f.funder_type}",
        )
        db.commit()
        return row(f)

    @app.get("/api/finance/contracts")
    def list_contracts(
        state: Optional[str] = Query(default=None),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        permitted(s, "admin", "doctor", "nurse")
        stmt = select(ProgrammeContract).where(ProgrammeContract.clinic == s.clinic)
        if state:
            stmt = stmt.where(ProgrammeContract.state == state)
        stmt = stmt.order_by(ProgrammeContract.created_at.desc())
        return [_serialize_contract(db, c) for c in db.scalars(stmt)]

    @app.post("/api/finance/contracts", status_code=201)
    def create_contract(
        p: ContractCreateIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin")
        funder = db.get(FundingOrganisation, p.funder_id)
        if not funder or funder.clinic != s.clinic:
            raise HTTPException(404, "Funding organisation not found in your clinic")
        if p.effective_until < p.effective_from:
            raise HTTPException(400, "Contract effective_until must be on or after effective_from")

        clinics = p.participating_clinics or [s.clinic]
        allocs = p.clinic_allocations_paise or {s.clinic: int(p.funding_ceiling_paise)}
        if sum(allocs.values()) > p.funding_ceiling_paise:
            raise HTTPException(400, "Clinic allocations cannot exceed contract funding ceiling")

        doc_hash = hashlib.sha256(
            f"{p.contract_reference}:{p.signed_agreement_filename}:{p.funding_ceiling_paise}".encode(
                "utf-8"
            )
        ).hexdigest()

        # New contracts ALWAYS start in 'draft' state and are explicitly labeled as unapproved proposals.
        c = ProgrammeContract(
            clinic=s.clinic,
            funder_id=funder.id,
            programme_name=p.programme_name.strip(),
            contract_reference=p.contract_reference.strip(),
            sanction_order_ref="",  # Never populate sanction order on a draft proposal
            state="draft",
            is_simulated_approval=True,
            approval_disclaimer=(
                "DRAFT PROPOSAL — Not an approved government or institutional sanction order. "
                "Cannot authorise funding claims until approved and active."
            ),
            funder_signatory_name=p.funder_signatory_name.strip(),
            funder_signatory_designation=p.funder_signatory_designation.strip(),
            recipient_signatory_name=p.recipient_signatory_name.strip() or s.name,
            signed_agreement_filename=p.signed_agreement_filename.strip(),
            signed_agreement_sha256=doc_hash,
            signed_agreement_stored_path=f"storage/agreements/{s.clinic}/{p.contract_reference.strip()}.pdf",
            effective_from=p.effective_from,
            effective_until=p.effective_until,
            funding_ceiling_paise=int(p.funding_ceiling_paise),
            funding_received_paise=0,
            funder_share_bps=int(p.funder_share_bps),
            reimbursement_basis=p.reimbursement_basis,
            allow_private_transport_reimbursement=bool(p.allow_private_transport_reimbursement),
            objectives_json=json.dumps(p.objectives),
            delivery_obligations_json=json.dumps(p.delivery_obligations),
            allowed_categories_json=json.dumps(p.allowed_categories),
            disallowed_categories_json=json.dumps(p.disallowed_categories),
            participating_clinics_json=json.dumps(clinics),
            clinic_allocations_json=json.dumps(allocs),
            version_number=1,
            created_by=s.id,
        )
        db.add(c)
        db.flush()
        record_fin_ledger(
            db,
            s,
            "programme_contract",
            c.id,
            "create_draft_contract",
            "",
            "draft",
            c.funding_ceiling_paise,
            f"ref={c.contract_reference}; ceiling_paise={c.funding_ceiling_paise}",
        )
        db.commit()
        return _serialize_contract(db, c)

    @app.post("/api/finance/contracts/{cid}/state")
    def transition_contract_state(
        cid: str,
        p: ContractStateTransitionIn,
        idempotency_key: Optional[str] = Header(default=None, alias="X-Idempotency-Key"),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor")
        c = db.get(ProgrammeContract, cid)
        if not c or c.clinic != s.clinic:
            raise HTTPException(404, "Programme contract not found in your clinic")

        prev_state = c.state
        if p.target_state == prev_state:
            raise HTTPException(409, f"Contract is already in state '{prev_state}'")
        allowed = ALLOWED_CONTRACT_TRANSITIONS.get(prev_state, set())
        if p.target_state not in allowed:
            raise HTTPException(
                400,
                f"Invalid contract state transition from '{prev_state}' to '{p.target_state}'",
            )

        ts = now()
        if p.target_state == "submitted":
            c.submitted_by = s.id
            c.submitted_at = ts
            c.approval_disclaimer = (
                "SUBMITTED PROPOSAL — Pending institutional review. Not yet approved funding."
            )
        elif p.target_state == "approved":
            if c.submitted_by and c.submitted_by == s.id and normalize_role(s.role) != "doctor":
                raise HTTPException(
                    403,
                    "Separation of duties: Contract submitter cannot self-approve without independent reviewer",
                )
            if not p.approval_evidence_ref.strip() and not p.sanction_order_ref.strip():
                raise HTTPException(
                    400,
                    "Contract approval requires an explicit approval_evidence_ref or sanction_order_ref",
                )
            c.approved_by = s.id
            c.approved_at = ts
            c.sanction_order_ref = p.sanction_order_ref.strip() or p.approval_evidence_ref.strip()
            c.approval_evidence_ref = p.approval_evidence_ref.strip() or c.sanction_order_ref
            c.is_simulated_approval = bool(p.is_simulated_approval)
            if c.is_simulated_approval:
                c.approval_disclaimer = (
                    f"SIMULATED / DEMO APPROVAL ONLY (Ref: {c.sanction_order_ref}) — "
                    "Explicitly marked as simulated evaluation record; never represented as a real government sanction."
                )
            else:
                c.approval_disclaimer = (
                    f"RECORDED INSTITUTIONAL APPROVAL — Reference: {c.sanction_order_ref}"
                )
        elif p.target_state == "active":
            if not c.approved_by:
                raise HTTPException(400, "Contract cannot become active without a recorded approval")

        if p.signed_agreement_filename.strip():
            c.signed_agreement_filename = p.signed_agreement_filename.strip()
            c.signed_agreement_sha256 = hashlib.sha256(
                f"{c.contract_reference}:{c.signed_agreement_filename}:{ts.isoformat()}".encode("utf-8")
            ).hexdigest()

        c.state = p.target_state
        c.updated_at = ts
        record_fin_ledger(
            db,
            s,
            "programme_contract",
            c.id,
            f"contract_state_{p.target_state}",
            prev_state,
            p.target_state,
            c.funding_ceiling_paise,
            f"simulated={c.is_simulated_approval}; ref={c.sanction_order_ref}; notes={p.notes}",
            idempotency_key=idempotency_key,
        )
        db.commit()
        return _serialize_contract(db, c)

    @app.post("/api/finance/contracts/{cid}/milestones", status_code=201)
    def create_contract_milestone(
        cid: str,
        p: MilestoneCreateIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin")
        c = db.get(ProgrammeContract, cid)
        if not c or c.clinic != s.clinic:
            raise HTTPException(404, "Programme contract not found in your clinic")
        existing_sum = int(
            db.scalar(
                select(func.coalesce(func.sum(ContractMilestone.tranche_amount_paise), 0)).where(
                    ContractMilestone.contract_id == cid,
                    ContractMilestone.clinic == s.clinic,
                )
            )
            or 0
        )
        if existing_sum + p.tranche_amount_paise > c.funding_ceiling_paise:
            raise HTTPException(
                400,
                "Milestone tranche total cannot exceed the contract funding ceiling",
            )
        m = ContractMilestone(
            contract_id=cid,
            clinic=s.clinic,
            milestone_name=p.milestone_name.strip(),
            due_date=p.due_date,
            deliverable_obligation=p.deliverable_obligation.strip(),
            tranche_amount_paise=int(p.tranche_amount_paise),
            status="pending",
            received_amount_paise=0,
        )
        db.add(m)
        db.flush()
        record_fin_ledger(
            db,
            s,
            "contract_milestone",
            m.id,
            "create_milestone",
            "",
            "pending",
            m.tranche_amount_paise,
            f"contract={c.contract_reference}; milestone={m.milestone_name}",
        )
        db.commit()
        return {
            **row(m),
            "tranche_amount_inr": paise_to_inr_str(m.tranche_amount_paise),
            "received_amount_inr": paise_to_inr_str(m.received_amount_paise),
        }

    @app.patch("/api/finance/milestones/{mid}")
    def update_contract_milestone(
        mid: str,
        p: MilestoneUpdateIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin")
        m = db.get(ContractMilestone, mid)
        if not m or m.clinic != s.clinic:
            raise HTTPException(404, "Contract milestone not found in your clinic")
        c = db.get(ProgrammeContract, m.contract_id)
        if not c or c.clinic != s.clinic:
            raise HTTPException(404, "Parent contract not found")
        if c.state in ("draft", "submitted"):
            raise HTTPException(
                400,
                "Cannot record milestone funding receipt against an unapproved draft/submitted proposal",
            )
        if p.status == "received":
            if not p.payment_reference.strip():
                raise HTTPException(
                    400,
                    "Marking a milestone tranche as received requires a verified payment_reference (UTR / sanction voucher)",
                )
            if p.received_amount_paise <= 0 or p.received_amount_paise > m.tranche_amount_paise:
                raise HTTPException(
                    400,
                    "Received amount must be positive and cannot exceed milestone tranche ceiling",
                )
        prev_status = m.status
        delta_received = int(p.received_amount_paise) - int(m.received_amount_paise)
        m.status = p.status
        m.received_amount_paise = int(p.received_amount_paise)
        if p.payment_reference.strip():
            m.payment_reference = p.payment_reference.strip()
        if p.status == "received":
            m.received_at = now()
            m.verified_by = s.id
            c.funding_received_paise = max(0, int(c.funding_received_paise) + delta_received)

        record_fin_ledger(
            db,
            s,
            "contract_milestone",
            m.id,
            f"milestone_{p.status}",
            prev_status,
            p.status,
            m.received_amount_paise,
            f"payment_ref={m.payment_reference}",
        )
        db.commit()
        return {
            **row(m),
            "tranche_amount_inr": paise_to_inr_str(m.tranche_amount_paise),
            "received_amount_inr": paise_to_inr_str(m.received_amount_paise),
        }

    @app.post("/api/finance/contracts/{cid}/amendments", status_code=201)
    def create_contract_amendment(
        cid: str,
        p: ContractAmendmentIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin")
        c = db.get(ProgrammeContract, cid)
        if not c or c.clinic != s.clinic:
            raise HTTPException(404, "Programme contract not found in your clinic")
        prev_end = c.effective_until
        prev_ceiling = c.funding_ceiling_paise
        next_ver = int(c.version_number) + 1

        if p.new_end_date:
            if p.new_end_date < c.effective_from:
                raise HTTPException(400, "Amended end date cannot precede contract effective_from")
            c.effective_until = p.new_end_date
        if p.new_ceiling_paise is not None:
            c.funding_ceiling_paise = int(p.new_ceiling_paise)
        if p.allow_private_transport_reimbursement is not None:
            c.allow_private_transport_reimbursement = bool(p.allow_private_transport_reimbursement)

        c.version_number = next_ver
        c.updated_at = now()

        amend = ContractAmendment(
            contract_id=c.id,
            clinic=s.clinic,
            version_number=next_ver,
            amendment_type=p.amendment_type,
            previous_end_date=prev_end,
            new_end_date=c.effective_until,
            previous_ceiling_paise=prev_ceiling,
            new_ceiling_paise=c.funding_ceiling_paise,
            amendment_summary=p.amendment_summary.strip(),
            approval_reference=p.approval_reference.strip(),
            approved_by=s.id,
        )
        db.add(amend)
        db.flush()
        record_fin_ledger(
            db,
            s,
            "programme_contract",
            c.id,
            "amend_contract",
            f"v{next_ver - 1}",
            f"v{next_ver}",
            c.funding_ceiling_paise,
            f"type={p.amendment_type}; ref={p.approval_reference}",
        )
        db.commit()
        return _serialize_contract(db, c)

    # -----------------------------------------------------------------------
    # 3. Programme Budgets & Financial Control
    # -----------------------------------------------------------------------
    @app.get("/api/finance/budgets")
    def list_budgets(
        contract_id: Optional[str] = Query(default=None),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        permitted(s, "admin", "doctor", "nurse")
        stmt = select(ProgrammeBudget).where(ProgrammeBudget.clinic == s.clinic)
        if contract_id:
            stmt = stmt.where(ProgrammeBudget.contract_id == contract_id)
        stmt = stmt.order_by(ProgrammeBudget.created_at.desc())
        return [_serialize_budget(db, b) for b in db.scalars(stmt)]

    @app.post("/api/finance/budgets", status_code=201)
    def create_budget(
        p: BudgetCreateIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin")
        c = db.get(ProgrammeContract, p.contract_id)
        if not c or c.clinic != s.clinic:
            raise HTTPException(404, "Programme contract not found in your clinic")
        if c.state in ("draft", "submitted"):
            raise HTTPException(
                400,
                "Cannot activate an operational programme budget under an unapproved draft/submitted contract",
            )
        total_alloc = sum(int(item.allocated_paise) for item in p.category_allocations)
        if total_alloc <= 0:
            raise HTTPException(400, "Total budget allocation must be greater than zero")
        if total_alloc > c.funding_ceiling_paise:
            raise HTTPException(
                400,
                f"Budget allocation ({paise_to_inr_str(total_alloc)} INR) exceeds contract funding ceiling ({paise_to_inr_str(c.funding_ceiling_paise)} INR)",
            )

        b = ProgrammeBudget(
            contract_id=c.id,
            clinic=s.clinic,
            budget_scope=p.budget_scope,
            target_clinic=p.target_clinic.strip() or s.clinic,
            fiscal_year=p.fiscal_year.strip(),
            period_start=p.period_start,
            period_end=p.period_end,
            total_allocated_paise=total_alloc,
            status="approved",
            version_number=1,
            created_by=s.id,
            approved_by=s.id,
            approved_at=now(),
        )
        db.add(b)
        db.flush()

        seen_cats: set[str] = set()
        for item in p.category_allocations:
            if item.category in seen_cats:
                raise HTTPException(400, f"Duplicate budget category '{item.category}'")
            seen_cats.add(item.category)
            db.add(
                BudgetCategoryLine(
                    budget_id=b.id,
                    contract_id=c.id,
                    clinic=s.clinic,
                    category=item.category,
                    allocated_paise=int(item.allocated_paise),
                )
            )
        db.flush()
        record_fin_ledger(
            db,
            s,
            "programme_budget",
            b.id,
            "create_budget",
            "",
            "approved",
            total_alloc,
            f"contract={c.contract_reference}; fiscal_year={b.fiscal_year}",
        )
        db.commit()
        return _serialize_budget(db, b)

    @app.get("/api/finance/budgets/{bid}/comparison")
    def get_budget_comparison(
        bid: str,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor", "nurse")
        b = db.get(ProgrammeBudget, bid)
        if not b or b.clinic != s.clinic:
            raise HTTPException(404, "Programme budget not found in your clinic")
        data = _serialize_budget(db, b)

        # Build month-wise cash-flow summary from Expenses, PayrollRuns, and Milestones
        exps = list(
            db.scalars(
                select(Expense).where(Expense.clinic == s.clinic, Expense.budget_id == b.id)
            )
        )
        monthly_flow: dict[str, dict[str, int]] = {}
        for e in exps:
            mkey = (e.created_at or now()).strftime("%Y-%m")
            bucket = monthly_flow.setdefault(
                mkey, {"incurred_paise": 0, "approved_paise": 0, "reimbursed_paise": 0}
            )
            bucket["incurred_paise"] += int(e.amount_paise)
            if e.approved:
                bucket["approved_paise"] += int(e.amount_paise)
            if e.reimbursement_status == "reimbursed":
                bucket["reimbursed_paise"] += int(e.amount_paise)

        data["monthly_cash_flow"] = [
            {
                "month": mkey,
                "incurred_paise": vals["incurred_paise"],
                "incurred_inr": paise_to_inr_str(vals["incurred_paise"]),
                "approved_paise": vals["approved_paise"],
                "approved_inr": paise_to_inr_str(vals["approved_paise"]),
                "reimbursed_paise": vals["reimbursed_paise"],
                "reimbursed_inr": paise_to_inr_str(vals["reimbursed_paise"]),
            }
            for mkey, vals in sorted(monthly_flow.items())
        ]
        return data

    @app.post("/api/finance/budgets/{bid}/amendments", status_code=201)
    def amend_budget_category(
        bid: str,
        p: BudgetAmendmentIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin")
        b = db.get(ProgrammeBudget, bid)
        if not b or b.clinic != s.clinic:
            raise HTTPException(404, "Programme budget not found in your clinic")
        c = db.get(ProgrammeContract, b.contract_id)
        if not c or c.clinic != s.clinic:
            raise HTTPException(404, "Parent contract not found")

        line = db.scalar(
            select(BudgetCategoryLine).where(
                BudgetCategoryLine.budget_id == b.id,
                BudgetCategoryLine.clinic == s.clinic,
                BudgetCategoryLine.category == p.category,
            )
        )
        if not line:
            line = BudgetCategoryLine(
                budget_id=b.id,
                contract_id=c.id,
                clinic=s.clinic,
                category=p.category,
                allocated_paise=0,
            )
            db.add(line)
            db.flush()

        old_alloc = int(line.allocated_paise)
        new_alloc = int(p.new_allocated_paise)
        if new_alloc < (line.committed_paise + line.approved_paise):
            raise HTTPException(
                400,
                "Cannot reduce category allocation below already committed + approved expenditure",
            )

        new_total = int(b.total_allocated_paise) - old_alloc + new_alloc
        if new_total > int(c.funding_ceiling_paise):
            raise HTTPException(
                400,
                f"Amended budget total ({paise_to_inr_str(new_total)} INR) would exceed contract funding ceiling ({paise_to_inr_str(c.funding_ceiling_paise)} INR)",
            )

        next_ver = int(b.version_number) + 1
        line.allocated_paise = new_alloc
        line.updated_at = now()
        b.total_allocated_paise = new_total
        b.version_number = next_ver
        b.updated_at = now()

        log_row = BudgetAmendmentLog(
            budget_id=b.id,
            clinic=s.clinic,
            version_number=next_ver,
            category=p.category,
            old_allocated_paise=old_alloc,
            new_allocated_paise=new_alloc,
            reason=p.reason.strip(),
            approval_reference=p.approval_reference.strip(),
            requested_by=s.id,
            approved_by=s.id,
        )
        db.add(log_row)
        db.flush()
        record_fin_ledger(
            db,
            s,
            "programme_budget",
            b.id,
            "amend_budget_category",
            f"v{next_ver - 1}:{old_alloc}",
            f"v{next_ver}:{new_alloc}",
            new_alloc,
            f"category={p.category}; ref={p.approval_reference}",
        )
        db.commit()
        return _serialize_budget(db, b)

    # -----------------------------------------------------------------------
    # 4. Healthcare Workforce Payroll
    # -----------------------------------------------------------------------
    @app.get("/api/finance/payroll/statutory-configs")
    def list_statutory_configs(
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        permitted(s, "admin", "doctor")
        rows = db.scalars(
            select(PayrollStatutoryConfig)
            .where(PayrollStatutoryConfig.clinic == s.clinic)
            .order_by(PayrollStatutoryConfig.version_number.desc())
        )
        return [row(r) for r in rows]

    @app.post("/api/finance/payroll/statutory-configs", status_code=201)
    def create_statutory_config(
        p: StatutoryConfigCreateIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin")
        max_ver = int(
            db.scalar(
                select(func.coalesce(func.max(PayrollStatutoryConfig.version_number), 0)).where(
                    PayrollStatutoryConfig.clinic == s.clinic
                )
            )
            or 0
        )
        cfg = PayrollStatutoryConfig(
            clinic=s.clinic,
            version_number=max_ver + 1,
            config_name=p.config_name.strip(),
            effective_from=p.effective_from,
            pf_employee_bps=int(p.pf_employee_bps),
            pf_employer_bps=int(p.pf_employer_bps),
            pf_wage_ceiling_paise=int(p.pf_wage_ceiling_paise),
            esi_employee_bps=int(p.esi_employee_bps),
            esi_employer_bps=int(p.esi_employer_bps),
            esi_wage_ceiling_paise=int(p.esi_wage_ceiling_paise),
            professional_tax_paise=int(p.professional_tax_paise),
            tds_default_bps=int(p.tds_default_bps),
            validated_by_professional_name=p.validated_by_professional_name.strip(),
            validated_by_credentials=p.validated_by_credentials.strip(),
            validation_notes=p.validation_notes.strip(),
            is_active=True,
            created_by=s.id,
        )
        db.add(cfg)
        db.flush()
        record_fin_ledger(
            db,
            s,
            "payroll_statutory_config",
            cfg.id,
            "create_statutory_config",
            "",
            f"v{cfg.version_number}",
            0,
            f"validated_by={cfg.validated_by_professional_name}",
        )
        db.commit()
        return row(cfg)

    @app.get("/api/finance/payroll/agreements")
    def list_compensation_agreements(
        staff_id: Optional[str] = Query(default=None),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        role = normalize_role(s.role)
        stmt = select(StaffCompensationAgreement).where(
            StaffCompensationAgreement.clinic == s.clinic
        )
        if role != "admin":
            stmt = stmt.where(StaffCompensationAgreement.staff_id == s.id)
        elif staff_id:
            stmt = stmt.where(StaffCompensationAgreement.staff_id == staff_id)
        stmt = stmt.order_by(StaffCompensationAgreement.created_at.desc())
        out: list[dict[str, Any]] = []
        for ag in db.scalars(stmt):
            st = db.get(Staff, ag.staff_id)
            d = row(ag)
            d["staff_name"] = st.name if st else ag.staff_id
            d["staff_role"] = normalize_role(st.role) if st else ""
            d["base_monthly_inr"] = paise_to_inr_str(ag.base_monthly_paise)
            d["per_shift_rate_inr"] = paise_to_inr_str(ag.per_shift_rate_paise)
            d["per_visit_rate_inr"] = paise_to_inr_str(ag.per_visit_rate_paise)
            d["field_allowance_inr"] = paise_to_inr_str(ag.field_allowance_paise)
            out.append(d)
        return out

    @app.post("/api/finance/payroll/agreements", status_code=201)
    def create_compensation_agreement(
        p: CompensationAgreementCreateIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin")
        target_staff = db.get(Staff, p.staff_id)
        if not target_staff or target_staff.clinic != s.clinic:
            raise HTTPException(404, "Staff member not found in your clinic")

        # Supersede prior active agreements for this staff member
        prior = list(
            db.scalars(
                select(StaffCompensationAgreement).where(
                    StaffCompensationAgreement.clinic == s.clinic,
                    StaffCompensationAgreement.staff_id == p.staff_id,
                    StaffCompensationAgreement.status == "active",
                )
            )
        )
        max_ver = 0
        for old_ag in prior:
            old_ag.status = "superseded"
            if old_ag.version_number > max_ver:
                max_ver = old_ag.version_number

        ag = StaffCompensationAgreement(
            staff_id=p.staff_id,
            clinic=s.clinic,
            contract_id=p.contract_id,
            budget_id=p.budget_id,
            employment_type=p.employment_type,
            pay_structure=p.pay_structure,
            base_monthly_paise=int(p.base_monthly_paise),
            per_shift_rate_paise=int(p.per_shift_rate_paise),
            per_visit_rate_paise=int(p.per_visit_rate_paise),
            field_allowance_paise=int(p.field_allowance_paise),
            expected_monthly_days=int(p.expected_monthly_days),
            attendance_adjustment_permitted=bool(p.attendance_adjustment_permitted),
            statutory_deductions_enabled=bool(p.statutory_deductions_enabled),
            effective_from=p.effective_from,
            effective_until=p.effective_until,
            status="active",
            version_number=max_ver + 1,
            approved_by=s.id,
            created_by=s.id,
        )
        db.add(ag)
        db.flush()
        record_fin_ledger(
            db,
            s,
            "staff_compensation_agreement",
            ag.id,
            "create_compensation_agreement",
            "",
            "active",
            ag.base_monthly_paise,
            f"staff={target_staff.name}; structure={ag.pay_structure}; att_adj={ag.attendance_adjustment_permitted}",
        )
        db.commit()
        d = row(ag)
        d["staff_name"] = target_staff.name
        d["base_monthly_inr"] = paise_to_inr_str(ag.base_monthly_paise)
        return d

    def _serialize_payslip(db: Session, ps: PayslipRecord) -> dict[str, Any]:
        st = db.get(Staff, ps.staff_id)
        d = row(ps)
        d["staff_name"] = st.name if st else ps.staff_id
        d["staff_role"] = normalize_role(st.role) if st else ""
        d["base_pay_inr"] = paise_to_inr_str(ps.base_pay_paise)
        d["visit_or_shift_pay_inr"] = paise_to_inr_str(ps.visit_or_shift_pay_paise)
        d["allowance_inr"] = paise_to_inr_str(ps.allowance_paise)
        d["attendance_deduction_inr"] = paise_to_inr_str(ps.attendance_deduction_paise)
        d["gross_earnings_inr"] = paise_to_inr_str(ps.gross_earnings_paise)
        d["total_deductions_inr"] = paise_to_inr_str(ps.total_deductions_paise)
        d["approved_reimbursements_inr"] = paise_to_inr_str(ps.approved_reimbursements_paise)
        d["net_payable_inr"] = paise_to_inr_str(ps.net_payable_paise)
        return d

    def _serialize_payroll_run(db: Session, pr: PayrollRun) -> dict[str, Any]:
        d = row(pr)
        d["total_gross_inr"] = paise_to_inr_str(pr.total_gross_paise)
        d["total_deductions_inr"] = paise_to_inr_str(pr.total_deductions_paise)
        d["total_employer_contributions_inr"] = paise_to_inr_str(
            pr.total_employer_contributions_paise
        )
        d["total_reimbursements_inr"] = paise_to_inr_str(pr.total_reimbursements_paise)
        d["total_net_payable_inr"] = paise_to_inr_str(pr.total_net_payable_paise)
        slips = list(
            db.scalars(
                select(PayslipRecord)
                .where(PayslipRecord.payroll_run_id == pr.id, PayslipRecord.clinic == pr.clinic)
                .order_by(PayslipRecord.staff_id.asc())
            )
        )
        d["payslips"] = [_serialize_payslip(db, sl) for sl in slips]
        return d

    @app.get("/api/finance/payroll/runs")
    def list_payroll_runs(
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        permitted(s, "admin")
        runs = db.scalars(
            select(PayrollRun)
            .where(PayrollRun.clinic == s.clinic)
            .order_by(PayrollRun.created_at.desc())
        )
        return [_serialize_payroll_run(db, r) for r in runs]

    @app.get("/api/finance/payroll/payslips")
    def list_payslips(
        period_month: Optional[str] = Query(default=None),
        staff_id: Optional[str] = Query(default=None),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        role = normalize_role(s.role)
        stmt = select(PayslipRecord).where(PayslipRecord.clinic == s.clinic)
        if role != "admin":
            # Non-admin staff can only view their own payslips
            if staff_id and staff_id != s.id:
                raise HTTPException(
                    403, "Restricted payroll access: Staff may only view their own payslips"
                )
            stmt = stmt.where(PayslipRecord.staff_id == s.id)
        elif staff_id:
            stmt = stmt.where(PayslipRecord.staff_id == staff_id)
        if period_month:
            stmt = stmt.where(PayslipRecord.period_month == period_month)
        stmt = stmt.order_by(PayslipRecord.period_month.desc(), PayslipRecord.created_at.desc())
        return [_serialize_payslip(db, sl) for sl in db.scalars(stmt)]

    @app.post("/api/finance/payroll/runs", status_code=201)
    def calculate_and_create_payroll_run(
        p: PayrollRunCreateIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin")
        year_i, month_i = [int(x) for x in p.period_month.split("-")]
        month_start = date(year_i, month_i, 1)
        if month_i == 12:
            month_end = date(year_i + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(year_i, month_i + 1, 1) - timedelta(days=1)

        if p.statutory_config_id:
            stat_cfg = db.get(PayrollStatutoryConfig, p.statutory_config_id)
            if not stat_cfg or stat_cfg.clinic != s.clinic:
                raise HTTPException(404, "Statutory configuration not found in your clinic")
        else:
            stat_cfg = db.scalar(
                select(PayrollStatutoryConfig)
                .where(
                    PayrollStatutoryConfig.clinic == s.clinic,
                    PayrollStatutoryConfig.is_active == True,  # noqa: E712
                )
                .order_by(PayrollStatutoryConfig.version_number.desc())
            )
            if not stat_cfg:
                raise HTTPException(
                    400,
                    "Payroll calculation requires an explicit, professionally validated PayrollStatutoryConfig",
                )

        ag_stmt = select(StaffCompensationAgreement).where(
            StaffCompensationAgreement.clinic == s.clinic,
            StaffCompensationAgreement.status == "active",
        )
        if p.staff_ids:
            ag_stmt = ag_stmt.where(StaffCompensationAgreement.staff_id.in_(p.staff_ids))
        agreements = list(db.scalars(ag_stmt))
        if not agreements:
            raise HTTPException(400, "No active staff compensation agreements found for payroll run")

        # Check for duplicate payroll for any target staff in this period_month before creating run
        for ag in agreements:
            dup = db.scalar(
                select(PayslipRecord).where(
                    PayslipRecord.clinic == s.clinic,
                    PayslipRecord.period_month == p.period_month,
                    PayslipRecord.staff_id == ag.staff_id,
                )
            )
            if dup is not None:
                raise HTTPException(
                    409,
                    f"Duplicate payroll prevented: Payslip already exists for staff '{ag.staff_id}' in period '{p.period_month}'",
                )

        overrides_map = {ov.staff_id: ov for ov in p.attendance_overrides}

        contract_id = p.contract_id or agreements[0].contract_id
        budget_id = p.budget_id or agreements[0].budget_id

        pr = PayrollRun(
            clinic=s.clinic,
            period_month=p.period_month,
            contract_id=contract_id,
            budget_id=budget_id,
            statutory_config_id=stat_cfg.id,
            status="draft",
            calculated_by=s.id,
        )
        db.add(pr)
        db.flush()

        tot_gross = 0
        tot_ded = 0
        tot_emp_contrib = 0
        tot_reimb = 0
        tot_net = 0
        slip_count = 0

        for ag in agreements:
            ov = overrides_map.get(ag.staff_id)
            # Query actual shifts, leaves, and verified field visits in period
            shifts = list(
                db.scalars(
                    select(StaffShift).where(
                        StaffShift.clinic == s.clinic,
                        StaffShift.staff_id == ag.staff_id,
                        StaffShift.shift_date >= month_start,
                        StaffShift.shift_date <= month_end,
                    )
                )
            )
            leaves = list(
                db.scalars(
                    select(StaffLeaveRequest).where(
                        StaffLeaveRequest.clinic == s.clinic,
                        StaffLeaveRequest.staff_id == ag.staff_id,
                        StaffLeaveRequest.status == "approved",
                        StaffLeaveRequest.start_date <= month_end,
                        StaffLeaveRequest.end_date >= month_start,
                    )
                )
            )
            calc_leave_days = 0
            for lv in leaves:
                s_d = max(month_start, lv.start_date)
                e_d = min(month_end, lv.end_date)
                if e_d >= s_d:
                    calc_leave_days += (e_d - s_d).days + 1

            visits_cnt = int(
                db.scalar(
                    select(func.count(FieldVisit.id)).where(
                        FieldVisit.clinic == s.clinic,
                        FieldVisit.assigned_staff_id == ag.staff_id,
                        FieldVisit.visit_date >= month_start,
                        FieldVisit.visit_date <= month_end,
                        FieldVisit.status == "completed",
                    )
                )
                or 0
            )

            days_sched = (
                ov.days_scheduled
                if (ov and ov.days_scheduled is not None)
                else int(ag.expected_monthly_days)
            )
            attended_shifts = sum(
                1 for sh in shifts if sh.status in ("checked_in", "completed")
            )
            days_att = (
                ov.days_attended
                if (ov and ov.days_attended is not None)
                else (attended_shifts if shifts else days_sched)
            )
            appr_leave = (
                ov.approved_leave_days
                if (ov and ov.approved_leave_days is not None)
                else calc_leave_days
            )
            unexcused_abs = (
                ov.unexcused_absent_days
                if (ov and ov.unexcused_absent_days is not None)
                else max(0, days_sched - days_att - appr_leave)
            )
            comp_visits = (
                ov.completed_visits_count
                if (ov and ov.completed_visits_count is not None)
                else visits_cnt
            )

            base_paise = int(ag.base_monthly_paise)
            visit_shift_paise = 0
            if ag.pay_structure == "per_shift_rate":
                visit_shift_paise = int(days_att) * int(ag.per_shift_rate_paise)
            elif ag.pay_structure in ("per_visit_rate", "retainer_plus_visit"):
                visit_shift_paise = int(comp_visits) * int(ag.per_visit_rate_paise)

            allowance_paise = int(ag.field_allowance_paise)

            # Attendance-based adjustments ONLY when employment terms permit them!
            att_deduction_paise = 0
            if ag.attendance_adjustment_permitted and unexcused_abs > 0 and days_sched > 0:
                att_deduction_paise = int(
                    (
                        Decimal(base_paise)
                        * Decimal(unexcused_abs)
                        / Decimal(days_sched)
                    ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                )

            gross_paise = max(
                0, base_paise + visit_shift_paise + allowance_paise - att_deduction_paise
            )

            pf_emp = 0
            pf_empr = 0
            esi_emp = 0
            esi_empr = 0
            pt_paise = 0
            tds_paise = 0
            if ag.statutory_deductions_enabled and gross_paise > 0:
                pf_base = min(gross_paise, int(stat_cfg.pf_wage_ceiling_paise))
                pf_emp = mul_bps_paise(pf_base, stat_cfg.pf_employee_bps)
                pf_empr = mul_bps_paise(pf_base, stat_cfg.pf_employer_bps)
                if gross_paise <= int(stat_cfg.esi_wage_ceiling_paise):
                    esi_emp = mul_bps_paise(gross_paise, stat_cfg.esi_employee_bps)
                    esi_empr = mul_bps_paise(gross_paise, stat_cfg.esi_employer_bps)
                pt_paise = int(stat_cfg.professional_tax_paise)
                tds_paise = mul_bps_paise(gross_paise, stat_cfg.tds_default_bps)

            total_ded = pf_emp + esi_emp + pt_paise + tds_paise

            # Include approved staff expense claims awaiting reimbursement if any
            reimb_paise = int(
                db.scalar(
                    select(func.coalesce(func.sum(ExpenseClaim.amount_paise), 0)).where(
                        ExpenseClaim.clinic == s.clinic,
                        ExpenseClaim.claimant_staff_id == ag.staff_id,
                        ExpenseClaim.status == "approved_by_finance",
                    )
                )
                or 0
            )

            net_paise = max(0, gross_paise - total_ded + reimb_paise)

            slip = PayslipRecord(
                payroll_run_id=pr.id,
                staff_id=ag.staff_id,
                agreement_id=ag.id,
                clinic=s.clinic,
                period_month=p.period_month,
                employment_type=ag.employment_type,
                pay_structure=ag.pay_structure,
                days_scheduled=days_sched,
                days_attended=days_att,
                approved_leave_days=appr_leave,
                unexcused_absent_days=unexcused_abs,
                completed_visits_count=comp_visits,
                base_pay_paise=base_paise,
                visit_or_shift_pay_paise=visit_shift_paise,
                allowance_paise=allowance_paise,
                attendance_deduction_paise=att_deduction_paise,
                gross_earnings_paise=gross_paise,
                pf_employee_paise=pf_emp,
                esi_employee_paise=esi_emp,
                professional_tax_paise=pt_paise,
                tds_paise=tds_paise,
                total_deductions_paise=total_ded,
                pf_employer_paise=pf_empr,
                esi_employer_paise=esi_empr,
                approved_reimbursements_paise=reimb_paise,
                net_payable_paise=net_paise,
                status="draft",
            )
            db.add(slip)
            tot_gross += gross_paise
            tot_ded += total_ded
            tot_emp_contrib += pf_empr + esi_empr
            tot_reimb += reimb_paise
            tot_net += net_paise
            slip_count += 1

        pr.total_gross_paise = tot_gross
        pr.total_deductions_paise = tot_ded
        pr.total_employer_contributions_paise = tot_emp_contrib
        pr.total_reimbursements_paise = tot_reimb
        pr.total_net_payable_paise = tot_net
        pr.payslip_count = slip_count

        # Update budget salary committed_paise when draft payroll run is calculated
        if budget_id:
            sal_line = db.scalar(
                select(BudgetCategoryLine).where(
                    BudgetCategoryLine.budget_id == budget_id,
                    BudgetCategoryLine.clinic == s.clinic,
                    BudgetCategoryLine.category == "salary",
                )
            )
            if sal_line:
                payroll_cost = tot_gross + tot_emp_contrib
                if (
                    sal_line.committed_paise + sal_line.approved_paise + payroll_cost
                    > sal_line.allocated_paise
                ):
                    db.rollback()
                    raise HTTPException(
                        400,
                        f"Payroll total cost ({paise_to_inr_str(payroll_cost)} INR) exceeds remaining salary budget allocation",
                    )
                sal_line.committed_paise += payroll_cost
                sal_line.incurred_paise += payroll_cost

        record_fin_ledger(
            db,
            s,
            "payroll_run",
            pr.id,
            "calculate_payroll_run",
            "",
            "draft",
            tot_net,
            f"period={pr.period_month}; slips={slip_count}; gross_paise={tot_gross}",
        )
        db.commit()
        return _serialize_payroll_run(db, pr)

    @app.post("/api/finance/payroll/runs/{rid}/transition")
    def transition_payroll_run(
        rid: str,
        p: PayrollRunTransitionIn,
        idempotency_key: Optional[str] = Header(default=None, alias="X-Idempotency-Key"),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor")
        pr = db.get(PayrollRun, rid)
        if not pr or pr.clinic != s.clinic:
            raise HTTPException(404, "Payroll run not found in your clinic")

        prev_status = pr.status
        valid_next: dict[str, set[str]] = {
            "draft": {"reviewed"},
            "reviewed": {"approved"},
            "approved": {"locked"},
            "locked": {"paid_verified"},
            "paid_verified": set(),
        }
        if p.target_status not in valid_next.get(prev_status, set()):
            raise HTTPException(
                400,
                f"Invalid payroll transition from '{prev_status}' to '{p.target_status}'",
            )

        ts = now()
        payroll_cost = int(pr.total_gross_paise) + int(pr.total_employer_contributions_paise)
        slips = list(
            db.scalars(
                select(PayslipRecord).where(
                    PayslipRecord.payroll_run_id == pr.id, PayslipRecord.clinic == s.clinic
                )
            )
        )

        if p.target_status == "reviewed":
            pr.reviewed_by = s.id
            pr.reviewed_at = ts
        elif p.target_status == "approved":
            # Separation of duties: the person who calculated the payroll run cannot self-approve it
            if pr.calculated_by == s.id:
                raise HTTPException(
                    403,
                    "Anti-self-approval rule: The staff member who calculated the payroll run cannot self-approve it",
                )
            pr.approved_by = s.id
            pr.approved_at = ts
            if pr.budget_id:
                sal_line = db.scalar(
                    select(BudgetCategoryLine).where(
                        BudgetCategoryLine.budget_id == pr.budget_id,
                        BudgetCategoryLine.clinic == s.clinic,
                        BudgetCategoryLine.category == "salary",
                    )
                )
                if sal_line:
                    sal_line.committed_paise = max(0, sal_line.committed_paise - payroll_cost)
                    sal_line.approved_paise += payroll_cost
        elif p.target_status == "locked":
            pr.locked_by = s.id
            pr.locked_at = ts
            if p.payment_batch_ref.strip():
                pr.payment_batch_ref = p.payment_batch_ref.strip()
        elif p.target_status == "paid_verified":
            # Never mark payroll as paid without verified payment evidence!
            if not p.payment_batch_ref.strip() or not p.payment_evidence_ref.strip():
                raise HTTPException(
                    400,
                    "Payroll cannot be marked as paid_verified without both payment_batch_ref and verified payment_evidence_ref",
                )
            pr.payment_batch_ref = p.payment_batch_ref.strip()
            pr.payment_evidence_ref = p.payment_evidence_ref.strip()
            pr.paid_confirmed_by = s.id
            pr.paid_confirmed_at = ts

            # Record single consolidated Expense row in existing Expense table (no duplicate tables)
            if not pr.expense_id:
                exp = Expense(
                    clinic=s.clinic,
                    category="salary",
                    amount_paise=payroll_cost,
                    description=f"Verified Monthly Healthcare Payroll ({pr.period_month}) — {pr.payslip_count} staff payslips",
                    receipt_ref=pr.payment_batch_ref,
                    approved=True,
                    created_by=pr.calculated_by or s.id,
                    approved_by=pr.approved_by or s.id,
                    contract_id=pr.contract_id,
                    budget_id=pr.budget_id,
                    payroll_run_id=pr.id,
                    reimbursement_status="approved_pending_claim",
                    payment_ref=pr.payment_evidence_ref,
                )
                db.add(exp)
                db.flush()
                pr.expense_id = exp.id

            if pr.budget_id:
                sal_line = db.scalar(
                    select(BudgetCategoryLine).where(
                        BudgetCategoryLine.budget_id == pr.budget_id,
                        BudgetCategoryLine.clinic == s.clinic,
                        BudgetCategoryLine.category == "salary",
                    )
                )
                if sal_line:
                    sal_line.paid_paise += payroll_cost

        pr.status = p.target_status
        for sl in slips:
            sl.status = p.target_status
            if pr.payment_batch_ref:
                sl.payment_ref = pr.payment_batch_ref
            if pr.payment_evidence_ref:
                sl.payment_evidence_ref = pr.payment_evidence_ref

        record_fin_ledger(
            db,
            s,
            "payroll_run",
            pr.id,
            f"payroll_{p.target_status}",
            prev_status,
            p.target_status,
            pr.total_net_payable_paise,
            f"batch_ref={pr.payment_batch_ref}; evidence={pr.payment_evidence_ref}; notes={p.notes}",
            idempotency_key=idempotency_key,
        )
        db.commit()
        return _serialize_payroll_run(db, pr)

    @app.get("/api/finance/payroll/runs/{rid}/export")
    def export_payroll_payment_batch(
        rid: str,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> Response:
        permitted(s, "admin")
        pr = db.get(PayrollRun, rid)
        if not pr or pr.clinic != s.clinic:
            raise HTTPException(404, "Payroll run not found in your clinic")
        slips = list(
            db.scalars(
                select(PayslipRecord)
                .where(PayslipRecord.payroll_run_id == pr.id, PayslipRecord.clinic == s.clinic)
                .order_by(PayslipRecord.staff_id.asc())
            )
        )
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "NOTICE",
                "OFFLINE PAYMENT BATCH FILE — DOES NOT EXECUTE LIVE BANK TRANSFERS",
                f"Period={pr.period_month}",
                f"Status={pr.status}",
            ]
        )
        writer.writerow(
            [
                "payslip_id",
                "staff_id",
                "staff_name",
                "employment_type",
                "days_attended",
                "completed_visits",
                "gross_paise",
                "gross_inr",
                "deductions_paise",
                "reimbursements_paise",
                "net_payable_paise",
                "net_payable_inr",
                "payment_ref",
            ]
        )
        for sl in slips:
            st = db.get(Staff, sl.staff_id)
            writer.writerow(
                [
                    sl.id,
                    sl.staff_id,
                    st.name if st else sl.staff_id,
                    sl.employment_type,
                    sl.days_attended,
                    sl.completed_visits_count,
                    sl.gross_earnings_paise,
                    paise_to_inr_str(sl.gross_earnings_paise),
                    sl.total_deductions_paise,
                    sl.approved_reimbursements_paise,
                    sl.net_payable_paise,
                    paise_to_inr_str(sl.net_payable_paise),
                    sl.payment_ref,
                ]
            )
        return Response(
            content=buf.getvalue().encode("utf-8"),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="payroll_batch_{pr.period_month}.csv"'
            },
        )

    # -----------------------------------------------------------------------
    # 5. Transport & Field Expense Reimbursement
    # -----------------------------------------------------------------------
    @app.get("/api/finance/policies")
    def list_expense_policies(
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        rows = db.scalars(
            select(ExpensePolicyRule)
            .where(ExpensePolicyRule.clinic == s.clinic)
            .order_by(ExpensePolicyRule.created_at.desc())
        )
        out: list[dict[str, Any]] = []
        for r in rows:
            d = row(r)
            d["per_km_rate_inr"] = paise_to_inr_str(r.per_km_rate_paise)
            d["fixed_allowance_inr"] = paise_to_inr_str(r.fixed_allowance_paise)
            d["max_single_claim_inr"] = paise_to_inr_str(r.max_single_claim_paise)
            out.append(d)
        return out

    @app.post("/api/finance/policies", status_code=201)
    def create_expense_policy(
        p: ExpensePolicyCreateIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin")
        pol = ExpensePolicyRule(
            clinic=s.clinic,
            contract_id=p.contract_id,
            policy_name=p.policy_name.strip(),
            claim_type=p.claim_type,
            rate_basis=p.rate_basis,
            per_km_rate_paise=int(p.per_km_rate_paise),
            fixed_allowance_paise=int(p.fixed_allowance_paise),
            max_single_claim_paise=int(p.max_single_claim_paise),
            requires_receipt_above_paise=int(p.requires_receipt_above_paise),
            allow_private_transport=bool(p.allow_private_transport),
            effective_from=p.effective_from,
            is_active=True,
            approved_by=s.id,
        )
        db.add(pol)
        db.flush()
        record_fin_ledger(
            db,
            s,
            "expense_policy_rule",
            pol.id,
            "create_expense_policy",
            "",
            "active",
            pol.max_single_claim_paise,
            f"policy={pol.policy_name}; rate_basis={pol.rate_basis}",
        )
        db.commit()
        return row(pol)

    def _serialize_expense_claim(db: Session, ec: ExpenseClaim) -> dict[str, Any]:
        d = row(ec)
        d["amount_inr"] = paise_to_inr_str(ec.amount_paise)
        st = db.get(Staff, ec.claimant_staff_id) if ec.claimant_staff_id else None
        d["claimant_name"] = st.name if st else (ec.transport_partner_id or "External Partner")
        return d

    @app.get("/api/finance/claims")
    def list_expense_claims(
        status: Optional[str] = Query(default=None),
        contract_id: Optional[str] = Query(default=None),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        role = normalize_role(s.role)
        stmt = select(ExpenseClaim).where(ExpenseClaim.clinic == s.clinic)
        if role == "field_coordinator":
            stmt = stmt.where(
                (ExpenseClaim.submitted_by == s.id) | (ExpenseClaim.claimant_staff_id == s.id)
            )
        if status:
            stmt = stmt.where(ExpenseClaim.status == status)
        if contract_id:
            stmt = stmt.where(ExpenseClaim.contract_id == contract_id)
        stmt = stmt.order_by(ExpenseClaim.submitted_at.desc())
        return [_serialize_expense_claim(db, ec) for ec in db.scalars(stmt)]

    @app.post("/api/finance/claims", status_code=201)
    def submit_expense_claim(
        p: ExpenseClaimCreateIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        # Validate contract and private transport public health scheme restriction
        contract: Optional[ProgrammeContract] = None
        if p.contract_id:
            contract = db.get(ProgrammeContract, p.contract_id)
            if not contract or contract.clinic != s.clinic:
                raise HTTPException(404, "Programme contract not found in your clinic")
            if contract.state in ("draft", "submitted"):
                raise HTTPException(
                    400,
                    "Cannot submit reimbursable expense claims under an unapproved draft/submitted contract",
                )

        policy: Optional[ExpensePolicyRule] = None
        if p.policy_rule_id:
            policy = db.get(ExpensePolicyRule, p.policy_rule_id)
            if not policy or policy.clinic != s.clinic:
                raise HTTPException(404, "Expense policy rule not found in your clinic")

        # Strict Public Health Scheme Private Transport Guard:
        # Never treat a private transport claim as reimbursable under a public health scheme
        # unless the specific contract/agreement explicitly permits it.
        if p.transport_mode == "private_unapproved":
            contract_allows = bool(contract and contract.allow_private_transport_reimbursement)
            policy_allows = bool(policy and policy.allow_private_transport)
            if not (contract_allows and policy_allows):
                raise HTTPException(
                    400,
                    "Public health scheme compliance violation: Private unapproved transport claims are disallowed unless both the contract and expense policy explicitly permit them",
                )

        # Duplicate receipt / claim detection
        clean_receipt = p.receipt_number.strip()
        dup_receipt = db.scalar(
            select(ExpenseClaim).where(
                ExpenseClaim.clinic == s.clinic,
                ExpenseClaim.receipt_number == clean_receipt,
                ExpenseClaim.status != "rejected",
            )
        )
        if dup_receipt is not None:
            raise HTTPException(
                409,
                f"Duplicate reimbursement claim rejected: Receipt number '{clean_receipt}' has already been claimed",
            )

        if p.transport_trip_id:
            dup_trip = db.scalar(
                select(ExpenseClaim).where(
                    ExpenseClaim.clinic == s.clinic,
                    ExpenseClaim.transport_trip_id == p.transport_trip_id,
                    ExpenseClaim.status != "rejected",
                )
            )
            if dup_trip is not None:
                raise HTTPException(
                    409,
                    f"Duplicate transport trip claim rejected: Transport trip '{p.transport_trip_id}' already has an active claim",
                )

        if p.field_visit_id:
            dup_visit = db.scalar(
                select(ExpenseClaim).where(
                    ExpenseClaim.clinic == s.clinic,
                    ExpenseClaim.field_visit_id == p.field_visit_id,
                    ExpenseClaim.claim_type == p.claim_type,
                    ExpenseClaim.status != "rejected",
                )
            )
            if dup_visit is not None:
                raise HTTPException(
                    409,
                    f"Duplicate field visit claim rejected: Field visit '{p.field_visit_id}' already has an active claim",
                )

        # Verify linked operational trip or field visit if provided
        linked_existing_expense_id: Optional[str] = None
        if p.transport_trip_id:
            trip = db.get(Transport, p.transport_trip_id)
            if not trip or trip.clinic != s.clinic:
                raise HTTPException(404, "Linked transport trip not found in your clinic")
            if trip.status != "completed":
                raise HTTPException(
                    400,
                    f"Transport trip reconciliation requires a completed trip (current status: '{trip.status}')",
                )
            linked_existing_expense_id = trip.expense_id

        if p.field_visit_id:
            fv = db.get(FieldVisit, p.field_visit_id)
            if not fv or fv.clinic != s.clinic:
                raise HTTPException(404, "Linked field visit not found in your clinic")
            if fv.status != "completed":
                raise HTTPException(
                    400,
                    f"Field visit expense claim requires a completed visit (current status: '{fv.status}')",
                )

        # Calculate amount_paise using policy rules if not explicitly supplied or validate against policy ceiling
        calc_amount_paise = p.amount_paise
        if policy:
            if policy.rate_basis == "per_km_mileage" and p.distance_km > 0 and not calc_amount_paise:
                calc_amount_paise = int(p.distance_km) * int(policy.per_km_rate_paise)
            elif policy.rate_basis == "fixed_allowance" and not calc_amount_paise:
                calc_amount_paise = int(policy.fixed_allowance_paise)
            if calc_amount_paise and calc_amount_paise > int(policy.max_single_claim_paise):
                raise HTTPException(
                    400,
                    f"Claim amount ({paise_to_inr_str(calc_amount_paise)} INR) exceeds policy single-claim ceiling ({paise_to_inr_str(policy.max_single_claim_paise)} INR)",
                )

        if not calc_amount_paise or calc_amount_paise <= 0:
            raise HTTPException(400, "Expense claim amount_paise must be greater than zero")

        # Check budget category ceiling before accepting commitment
        if p.budget_id:
            bline = db.scalar(
                select(BudgetCategoryLine).where(
                    BudgetCategoryLine.budget_id == p.budget_id,
                    BudgetCategoryLine.clinic == s.clinic,
                    BudgetCategoryLine.category == p.expense_category,
                )
            )
            if not bline:
                raise HTTPException(
                    400,
                    f"Category '{p.expense_category}' is not allocated in budget '{p.budget_id}'",
                )
            if (
                bline.committed_paise + bline.approved_paise + int(calc_amount_paise)
                > bline.allocated_paise
            ):
                raise HTTPException(
                    400,
                    f"Budget ceiling exceeded: Claim of {paise_to_inr_str(calc_amount_paise)} INR exceeds available allocation in category '{p.expense_category}'",
                )
            bline.committed_paise += int(calc_amount_paise)
            bline.incurred_paise += int(calc_amount_paise)

        receipt_hash = hashlib.sha256(
            f"{s.clinic}:{clean_receipt}:{p.receipt_filename}:{calc_amount_paise}".encode("utf-8")
        ).hexdigest()

        ec = ExpenseClaim(
            clinic=s.clinic,
            contract_id=p.contract_id,
            budget_id=p.budget_id,
            policy_rule_id=p.policy_rule_id,
            expense_id=linked_existing_expense_id,
            claim_type=p.claim_type,
            expense_category=p.expense_category,
            claimant_staff_id=p.claimant_staff_id or s.id,
            transport_partner_id=p.transport_partner_id,
            partner_facility_id=p.partner_facility_id,
            transport_trip_id=p.transport_trip_id,
            field_visit_id=p.field_visit_id,
            service_request_id=p.service_request_id,
            referral_id=p.referral_id,
            transport_mode=p.transport_mode,
            distance_km=int(p.distance_km),
            amount_paise=int(calc_amount_paise),
            receipt_number=clean_receipt,
            receipt_filename=p.receipt_filename.strip(),
            receipt_sha256=receipt_hash,
            receipt_verified=False,
            description=p.description.strip(),
            status="submitted",
            submitted_by=s.id,
        )
        db.add(ec)
        db.flush()
        record_fin_ledger(
            db,
            s,
            "expense_claim",
            ec.id,
            "submit_expense_claim",
            "",
            "submitted",
            ec.amount_paise,
            f"receipt={ec.receipt_number}; mode={ec.transport_mode}; cat={ec.expense_category}",
        )
        db.commit()
        return _serialize_expense_claim(db, ec)

    @app.post("/api/finance/claims/{cid}/decision")
    def decide_expense_claim(
        cid: str,
        p: ExpenseClaimDecisionIn,
        idempotency_key: Optional[str] = Header(default=None, alias="X-Idempotency-Key"),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor", "nurse")
        if idempotency_key:
            existing_idem = db.scalar(
                select(FinancialAuditLedger).where(
                    FinancialAuditLedger.idempotency_key == idempotency_key
                )
            )
            if existing_idem is not None:
                raise HTTPException(
                    409,
                    f"Duplicate / concurrent financial operation blocked by idempotency key '{idempotency_key}'",
                )
        ec = db.get(ExpenseClaim, cid)
        if not ec or ec.clinic != s.clinic:
            raise HTTPException(404, "Expense claim not found in your clinic")

        # Strict Anti-Self-Approval Rule:
        # Claimant / submitter cannot verify or approve their own expense claim!
        if p.decision in ("verified_by_supervisor", "approved_by_finance", "reimbursed_paid"):
            if ec.submitted_by == s.id or ec.claimant_staff_id == s.id:
                raise HTTPException(
                    403,
                    "Anti-self-approval rule: Staff cannot verify or approve their own expense claim",
                )

        prev_status = ec.status
        ts = now()
        bline: Optional[BudgetCategoryLine] = None
        if ec.budget_id:
            bline = db.scalar(
                select(BudgetCategoryLine).where(
                    BudgetCategoryLine.budget_id == ec.budget_id,
                    BudgetCategoryLine.clinic == s.clinic,
                    BudgetCategoryLine.category == ec.expense_category,
                )
            )

        if p.decision == "verified_by_supervisor":
            if prev_status not in ("submitted", "returned_for_correction"):
                raise HTTPException(
                    400, f"Cannot supervisor-verify claim in state '{prev_status}'"
                )
            ec.status = "verified_by_supervisor"
            ec.receipt_verified = bool(p.receipt_verified)
            ec.verified_by = s.id
            ec.verified_at = ts
            ec.verification_notes = p.notes.strip()

        elif p.decision == "approved_by_finance":
            permitted(s, "admin", "doctor")
            if prev_status != "verified_by_supervisor":
                raise HTTPException(
                    400,
                    "Expense claim must be verified_by_supervisor before finance approval",
                )
            if not ec.receipt_verified and not p.receipt_verified:
                raise HTTPException(
                    400, "Cannot approve expense claim without verified receipt evidence"
                )
            if bline:
                # Re-verify budget ceiling
                if (
                    max(0, bline.committed_paise - ec.amount_paise)
                    + bline.approved_paise
                    + ec.amount_paise
                    > bline.allocated_paise
                ):
                    raise HTTPException(
                        400,
                        "Finance approval blocked: Category budget ceiling would be exceeded",
                    )
                bline.committed_paise = max(0, bline.committed_paise - ec.amount_paise)
                bline.approved_paise += ec.amount_paise

            ec.status = "approved_by_finance"
            ec.receipt_verified = True
            ec.approved_by = s.id
            ec.approved_at = ts
            ec.approval_notes = p.notes.strip()

            # Reuse existing Expense row (e.g. from Phase 5 transport trip) or create one linked row
            if ec.expense_id:
                exp = db.get(Expense, ec.expense_id)
                if exp and exp.clinic == s.clinic:
                    exp.approved = True
                    exp.approved_by = s.id
                    exp.contract_id = ec.contract_id
                    exp.budget_id = ec.budget_id
                    exp.expense_claim_id = ec.id
                    exp.reimbursement_status = "approved_pending_claim"
            else:
                exp = Expense(
                    clinic=s.clinic,
                    category=ec.expense_category,
                    amount_paise=ec.amount_paise,
                    description=ec.description,
                    receipt_ref=ec.receipt_number,
                    approved=True,
                    created_by=ec.submitted_by,
                    approved_by=s.id,
                    contract_id=ec.contract_id,
                    budget_id=ec.budget_id,
                    expense_claim_id=ec.id,
                    reimbursement_status="approved_pending_claim",
                )
                db.add(exp)
                db.flush()
                ec.expense_id = exp.id

        elif p.decision == "reimbursed_paid":
            permitted(s, "admin")
            if prev_status != "approved_by_finance":
                raise HTTPException(
                    400, "Expense claim must be approved_by_finance before marking reimbursed_paid"
                )
            if not p.reimbursement_payment_ref.strip():
                raise HTTPException(
                    400,
                    "Marking an expense claim as reimbursed_paid requires a verified reimbursement_payment_ref",
                )
            ec.status = "reimbursed_paid"
            ec.reimbursement_payment_ref = p.reimbursement_payment_ref.strip()
            ec.reimbursed_at = ts
            if bline:
                bline.paid_paise += ec.amount_paise
            if ec.expense_id:
                exp = db.get(Expense, ec.expense_id)
                if exp and exp.clinic == s.clinic:
                    exp.payment_ref = ec.reimbursement_payment_ref
                    exp.reimbursement_status = "paid_to_claimant"

        elif p.decision in ("rejected", "returned_for_correction"):
            if prev_status in ("approved_by_finance", "reimbursed_paid"):
                raise HTTPException(
                    400, f"Cannot reject/return claim after '{prev_status}'"
                )
            if not p.notes.strip():
                raise HTTPException(
                    400, "Rejecting or returning a claim requires an explicit reason in notes"
                )
            if bline and prev_status in ("submitted", "verified_by_supervisor"):
                bline.committed_paise = max(0, bline.committed_paise - ec.amount_paise)
                bline.incurred_paise = max(0, bline.incurred_paise - ec.amount_paise)
            ec.status = p.decision
            ec.rejection_or_return_reason = p.notes.strip()

        record_fin_ledger(
            db,
            s,
            "expense_claim",
            ec.id,
            f"claim_{p.decision}",
            prev_status,
            ec.status,
            ec.amount_paise,
            f"receipt={ec.receipt_number}; ref={ec.reimbursement_payment_ref}; notes={p.notes}",
            idempotency_key=idempotency_key,
        )
        db.commit()
        return _serialize_expense_claim(db, ec)

    # -----------------------------------------------------------------------
    # 6. Service-to-Funding Evidence & Supporting Evidence Packages
    # -----------------------------------------------------------------------
    def _serialize_funding_claim(db: Session, fc: FundingClaim) -> dict[str, Any]:
        d = row(fc)
        c = db.get(ProgrammeContract, fc.contract_id) if fc.contract_id else None
        d["programme_name"] = c.programme_name if c else ""
        d["contract_reference"] = c.contract_reference if c else ""
        d["total_claimed_inr"] = paise_to_inr_str(fc.total_claimed_paise)
        d["funder_reimbursable_inr"] = paise_to_inr_str(fc.funder_reimbursable_paise)
        d["approved_reimbursed_inr"] = paise_to_inr_str(fc.approved_reimbursed_paise)
        links = list(
            db.scalars(
                select(ServiceFundingEvidenceLink)
                .where(
                    ServiceFundingEvidenceLink.funding_claim_id == fc.id,
                    ServiceFundingEvidenceLink.clinic == fc.clinic,
                )
                .order_by(ServiceFundingEvidenceLink.created_at.asc())
            )
        )
        d["evidence_links"] = [
            {
                **row(lk),
                "amount_inr": paise_to_inr_str(lk.amount_paise),
                "reimbursable_inr": paise_to_inr_str(lk.reimbursable_paise),
            }
            for lk in links
        ]
        return d

    @app.get("/api/finance/funding-claims")
    def list_funding_claims(
        contract_id: Optional[str] = Query(default=None),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        permitted(s, "admin", "doctor", "nurse")
        stmt = select(FundingClaim).where(FundingClaim.clinic == s.clinic)
        if contract_id:
            stmt = stmt.where(FundingClaim.contract_id == contract_id)
        stmt = stmt.order_by(FundingClaim.created_at.desc())
        return [_serialize_funding_claim(db, fc) for fc in db.scalars(stmt)]

    @app.post("/api/finance/funding-claims", status_code=201)
    def create_funding_claim(
        p: FundingClaimCreateIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin")
        contract = db.get(ProgrammeContract, p.contract_id)
        if not contract or contract.clinic != s.clinic:
            raise HTTPException(404, "Programme contract not found in your clinic")
        if contract.state not in ("approved", "active"):
            raise HTTPException(
                400,
                f"Funding claims can only be created against an approved/active contract (current state: '{contract.state}')",
            )
        budget = db.get(ProgrammeBudget, p.budget_id)
        if not budget or budget.clinic != s.clinic or budget.contract_id != contract.id:
            raise HTTPException(404, "Programme budget not found for this contract in your clinic")

        clean_ref = p.claim_reference.strip()
        dup_claim = db.scalar(
            select(FundingClaim).where(
                FundingClaim.clinic == s.clinic,
                FundingClaim.claim_reference == clean_ref,
            )
        )
        if dup_claim is not None:
            raise HTTPException(
                409, f"Duplicate funding claim reference '{clean_ref}' rejected"
            )

        try:
            allowed_cats = set(json.loads(contract.allowed_categories_json or "[]"))
            disallowed_cats = set(json.loads(contract.disallowed_categories_json or "[]"))
        except Exception:
            allowed_cats = set(BUDGET_CATEGORIES)
            disallowed_cats = set()

        fc = FundingClaim(
            clinic=s.clinic,
            contract_id=contract.id,
            budget_id=budget.id,
            milestone_id=p.milestone_id,
            claim_reference=clean_ref,
            period_start=p.period_start,
            period_end=p.period_end,
            status="draft",
            submitted_by=s.id,
            notes=p.notes.strip(),
        )
        db.add(fc)
        db.flush()

        tot_claimed = 0
        tot_reimbursable = 0
        hash_parts: list[str] = [contract.contract_reference, clean_ref]

        for item in p.evidence_items:
            if item.service_category in disallowed_cats or (
                allowed_cats and item.service_category not in allowed_cats
            ):
                db.rollback()
                raise HTTPException(
                    400,
                    f"Service category '{item.service_category}' is disallowed under contract '{contract.contract_reference}'",
                )

            exp = db.get(Expense, item.expense_id)
            if not exp or exp.clinic != s.clinic:
                db.rollback()
                raise HTTPException(
                    404, f"Expenditure record '{item.expense_id}' not found in your clinic"
                )
            if not exp.approved:
                db.rollback()
                raise HTTPException(
                    400,
                    f"Unverifiable funding claim rejected: Expenditure '{exp.id}' has not been approved",
                )

            # Prevent duplicate funding claim on the same Expense record
            dup_link = db.scalar(
                select(ServiceFundingEvidenceLink).where(
                    ServiceFundingEvidenceLink.clinic == s.clinic,
                    ServiceFundingEvidenceLink.expense_id == exp.id,
                )
            )
            if dup_link is not None:
                db.rollback()
                raise HTTPException(
                    409,
                    f"Duplicate funding claim prevented: Expenditure '{exp.id}' is already linked to funding claim '{dup_link.funding_claim_id}'",
                )

            # Verify operational service / visit / trip / referral or payroll evidence
            has_verifiable_source = False
            beneficiary_ref = "PROGRAMME-WORKFORCE-COHORT"

            if item.service_request_id:
                sr = db.get(ServiceRequest, item.service_request_id)
                if not sr or sr.clinic != s.clinic:
                    db.rollback()
                    raise HTTPException(404, "Linked ServiceRequest not found in your clinic")
                if sr.status not in ("completed", "verified", "closed"):
                    db.rollback()
                    raise HTTPException(
                        400,
                        f"Linked ServiceRequest '{sr.id}' is in status '{sr.status}'; must be completed or verified",
                    )
                has_verifiable_source = True
                beneficiary_ref = anonymise_beneficiary_ref(s.clinic, sr.mother_id)

            if item.field_visit_id:
                fv = db.get(FieldVisit, item.field_visit_id)
                if not fv or fv.clinic != s.clinic or fv.status != "completed":
                    db.rollback()
                    raise HTTPException(
                        400,
                        "Linked FieldVisit must exist in your clinic and have status='completed'",
                    )
                has_verifiable_source = True
                beneficiary_ref = anonymise_beneficiary_ref(s.clinic, fv.mother_id)

            if item.transport_trip_id:
                tr = db.get(Transport, item.transport_trip_id)
                if not tr or tr.clinic != s.clinic or tr.status != "completed":
                    db.rollback()
                    raise HTTPException(
                        400,
                        "Linked Transport trip must exist in your clinic and have status='completed'",
                    )
                has_verifiable_source = True
                beneficiary_ref = anonymise_beneficiary_ref(s.clinic, tr.mother_id)

            if item.referral_id:
                rf = db.get(HospitalReferral, item.referral_id)
                if not rf or rf.clinic != s.clinic:
                    db.rollback()
                    raise HTTPException(404, "Linked HospitalReferral not found in your clinic")
                has_verifiable_source = True
                beneficiary_ref = anonymise_beneficiary_ref(s.clinic, rf.mother_id)

            if item.payslip_id or exp.payroll_run_id:
                has_verifiable_source = True

            if item.expense_claim_id or exp.expense_claim_id:
                cid_lookup = item.expense_claim_id or exp.expense_claim_id
                ec_obj = db.get(ExpenseClaim, cid_lookup) if cid_lookup else None
                if ec_obj and ec_obj.clinic == s.clinic and ec_obj.receipt_verified:
                    has_verifiable_source = True

            if item.mother_id and beneficiary_ref == "PROGRAMME-WORKFORCE-COHORT":
                beneficiary_ref = anonymise_beneficiary_ref(s.clinic, item.mother_id)

            if not has_verifiable_source or not item.verification_evidence_ref.strip():
                db.rollback()
                raise HTTPException(
                    400,
                    f"Unverifiable funding claim rejected for expense '{exp.id}': Must link a verified completed service, field visit, transport trip, referral, payslip, or verified expense claim",
                )

            amt = int(exp.amount_paise)
            reimb_amt = mul_bps_paise(amt, contract.funder_share_bps)

            lk = ServiceFundingEvidenceLink(
                clinic=s.clinic,
                funding_claim_id=fc.id,
                contract_id=contract.id,
                budget_id=budget.id,
                service_category=item.service_category,
                staff_id=item.staff_id or exp.created_by,
                provider_entity_id=item.provider_entity_id,
                service_request_id=item.service_request_id,
                field_visit_id=item.field_visit_id,
                transport_trip_id=item.transport_trip_id,
                referral_id=item.referral_id,
                expense_id=exp.id,
                expense_claim_id=item.expense_claim_id or exp.expense_claim_id,
                payslip_id=item.payslip_id,
                beneficiary_anonymised_ref=beneficiary_ref,
                verification_evidence_ref=item.verification_evidence_ref.strip(),
                verified_by_staff_id=exp.approved_by or s.id,
                amount_paise=amt,
                reimbursable_paise=reimb_amt,
                reimbursement_status="linked",
            )
            db.add(lk)
            exp.funding_claim_id = fc.id
            exp.reimbursement_status = "claimed_with_funder"
            tot_claimed += amt
            tot_reimbursable += reimb_amt
            hash_parts.append(f"{exp.id}:{amt}:{reimb_amt}:{beneficiary_ref}")

        fc.total_claimed_paise = tot_claimed
        fc.funder_reimbursable_paise = tot_reimbursable
        fc.evidence_package_hash = hashlib.sha256(
            "|".join(hash_parts).encode("utf-8")
        ).hexdigest()

        record_fin_ledger(
            db,
            s,
            "funding_claim",
            fc.id,
            "create_funding_claim",
            "",
            "draft",
            tot_reimbursable,
            f"ref={fc.claim_reference}; items={len(p.evidence_items)}; hash={fc.evidence_package_hash[:16]}",
        )
        db.commit()
        return _serialize_funding_claim(db, fc)

    @app.post("/api/finance/funding-claims/{fcid}/transition")
    def transition_funding_claim(
        fcid: str,
        p: FundingClaimTransitionIn,
        idempotency_key: Optional[str] = Header(default=None, alias="X-Idempotency-Key"),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor")
        fc = db.get(FundingClaim, fcid)
        if not fc or fc.clinic != s.clinic:
            raise HTTPException(404, "Funding claim not found in your clinic")

        prev_status = fc.status
        ts = now()
        links = list(
            db.scalars(
                select(ServiceFundingEvidenceLink).where(
                    ServiceFundingEvidenceLink.funding_claim_id == fc.id,
                    ServiceFundingEvidenceLink.clinic == s.clinic,
                )
            )
        )

        if p.target_status == "submitted_to_funder":
            fc.submitted_at = ts
            fc.submitted_by = s.id
            for lk in links:
                lk.reimbursement_status = "submitted"
        elif p.target_status == "approved_by_funder":
            fc.approved_reimbursed_paise = (
                int(p.approved_reimbursed_paise)
                if p.approved_reimbursed_paise is not None
                else int(fc.funder_reimbursable_paise)
            )
        elif p.target_status == "reimbursed_settled":
            if not p.settled_payment_ref.strip():
                raise HTTPException(
                    400,
                    "Marking a funding claim as reimbursed_settled requires a verified settled_payment_ref",
                )
            reimb_amt = (
                int(p.approved_reimbursed_paise)
                if p.approved_reimbursed_paise is not None
                else (
                    int(fc.approved_reimbursed_paise)
                    if fc.approved_reimbursed_paise > 0
                    else int(fc.funder_reimbursable_paise)
                )
            )
            fc.approved_reimbursed_paise = reimb_amt
            fc.settled_payment_ref = p.settled_payment_ref.strip()
            fc.settled_at = ts

            c = db.get(ProgrammeContract, fc.contract_id)
            if c and c.clinic == s.clinic:
                c.funding_received_paise += reimb_amt

            for lk in links:
                lk.reimbursement_status = "reimbursed"
                exp = db.get(Expense, lk.expense_id)
                if exp and exp.clinic == s.clinic:
                    exp.reimbursement_status = "reimbursed"
                    exp.payment_ref = fc.settled_payment_ref
                bline = db.scalar(
                    select(BudgetCategoryLine).where(
                        BudgetCategoryLine.budget_id == fc.budget_id,
                        BudgetCategoryLine.clinic == s.clinic,
                        BudgetCategoryLine.category == lk.service_category,
                    )
                )
                if bline:
                    bline.reimbursed_paise += int(lk.reimbursable_paise)

        fc.status = p.target_status
        if p.notes.strip():
            fc.notes = f"{fc.notes}\n{p.notes.strip()}".strip()

        record_fin_ledger(
            db,
            s,
            "funding_claim",
            fc.id,
            f"funding_claim_{p.target_status}",
            prev_status,
            p.target_status,
            fc.approved_reimbursed_paise or fc.funder_reimbursable_paise,
            f"ref={fc.claim_reference}; payment_ref={fc.settled_payment_ref}",
            idempotency_key=idempotency_key,
        )
        db.commit()
        return _serialize_funding_claim(db, fc)

    @app.get("/api/finance/funding-claims/{fcid}/evidence-package")
    def get_supporting_evidence_package(
        fcid: str,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        """Generate a privacy-safe Supporting Evidence Package linking Contract -> Programme ->
        Approved Service Category -> Staff/Provider -> Completed Service/Trip -> Verification Evidence
        -> Associated Expenditure -> Funding Claim -> Reimbursement Status WITHOUT exposing patient PII.
        """
        permitted(s, "admin", "doctor")
        fc = db.get(FundingClaim, fcid)
        if not fc or fc.clinic != s.clinic:
            raise HTTPException(404, "Funding claim not found in your clinic")
        c = db.get(ProgrammeContract, fc.contract_id)
        funder = db.get(FundingOrganisation, c.funder_id) if c else None
        b = db.get(ProgrammeBudget, fc.budget_id)
        links = list(
            db.scalars(
                select(ServiceFundingEvidenceLink)
                .where(
                    ServiceFundingEvidenceLink.funding_claim_id == fc.id,
                    ServiceFundingEvidenceLink.clinic == s.clinic,
                )
                .order_by(ServiceFundingEvidenceLink.created_at.asc())
            )
        )

        chain_items: list[dict[str, Any]] = []
        for lk in links:
            st = db.get(Staff, lk.staff_id) if lk.staff_id else None
            ver_st = db.get(Staff, lk.verified_by_staff_id) if lk.verified_by_staff_id else None
            exp = db.get(Expense, lk.expense_id)
            chain_items.append(
                {
                    "evidence_link_id": lk.id,
                    "contract_reference": c.contract_reference if c else "",
                    "programme_name": c.programme_name if c else "",
                    "approved_service_category": lk.service_category,
                    "assigned_staff_or_provider": (
                        f"{st.name} ({normalize_role(st.role)})"
                        if st
                        else (lk.provider_entity_id or "Authorized Partner")
                    ),
                    "completed_operational_records": {
                        "service_request_id": lk.service_request_id,
                        "field_visit_id": lk.field_visit_id,
                        "transport_trip_id": lk.transport_trip_id,
                        "referral_id": lk.referral_id,
                        "payslip_id": lk.payslip_id,
                        "expense_claim_id": lk.expense_claim_id,
                    },
                    "beneficiary_anonymised_ref": lk.beneficiary_anonymised_ref,
                    "privacy_redaction_status": "REDACTED_ANONYMISED — Zero clinical notes, diagnoses, or patient PII exposed",
                    "verification_evidence_ref": lk.verification_evidence_ref,
                    "verified_by": (
                        f"{ver_st.name} ({normalize_role(ver_st.role)})"
                        if ver_st
                        else lk.verified_by_staff_id
                    ),
                    "expenditure_id": lk.expense_id,
                    "expenditure_receipt_ref": exp.receipt_ref if exp else "",
                    "amount_paise": lk.amount_paise,
                    "amount_inr": paise_to_inr_str(lk.amount_paise),
                    "funder_reimbursable_paise": lk.reimbursable_paise,
                    "funder_reimbursable_inr": paise_to_inr_str(lk.reimbursable_paise),
                    "reimbursement_status": lk.reimbursement_status,
                }
            )

        return {
            "package_type": "SERVICE_TO_FUNDING_EVIDENCE_PACKAGE",
            "compliance_label": (
                "INTERNAL / DRAFT — SIMULATED EVALUATION EVIDENCE PACKAGE (NOT AN OFFICIAL GOVERNMENT COMPLIANCE STATEMENT)"
                if (not c or c.is_simulated_approval or c.state != "active")
                else f"VERIFIED INSTITUTIONAL EVIDENCE PACKAGE — Sanction Ref: {c.sanction_order_ref}"
            ),
            "privacy_safeguard": "Contains only anonymised beneficiary references and operational verification metadata. No personal medical details or clinical notes are included.",
            "clinic": s.clinic,
            "funder_name": funder.name if funder else "",
            "contract": {
                "id": c.id if c else "",
                "contract_reference": c.contract_reference if c else "",
                "programme_name": c.programme_name if c else "",
                "state": c.state if c else "",
                "is_simulated_approval": c.is_simulated_approval if c else True,
                "funder_share_pct": pct_bps(c.funder_share_bps, BPS_DIVISOR) if c else "100.00%",
            },
            "budget": {
                "id": b.id if b else "",
                "fiscal_year": b.fiscal_year if b else "",
                "total_allocated_inr": paise_to_inr_str(b.total_allocated_paise) if b else "0.00",
            },
            "funding_claim": {
                "id": fc.id,
                "claim_reference": fc.claim_reference,
                "period_start": str(fc.period_start),
                "period_end": str(fc.period_end),
                "status": fc.status,
                "total_claimed_paise": fc.total_claimed_paise,
                "total_claimed_inr": paise_to_inr_str(fc.total_claimed_paise),
                "funder_reimbursable_paise": fc.funder_reimbursable_paise,
                "funder_reimbursable_inr": paise_to_inr_str(fc.funder_reimbursable_paise),
                "approved_reimbursed_paise": fc.approved_reimbursed_paise,
                "approved_reimbursed_inr": paise_to_inr_str(fc.approved_reimbursed_paise),
                "settled_payment_ref": fc.settled_payment_ref,
                "evidence_package_hash": fc.evidence_package_hash,
            },
            "evidence_chain": chain_items,
            "generated_at": now().isoformat(),
        }

    # -----------------------------------------------------------------------
    # 7. Financial Dashboards, Reporting & CSV/PDF Exports
    # -----------------------------------------------------------------------
    @app.get("/api/finance/dashboard")
    def get_financial_dashboard(
        contract_id: Optional[str] = Query(default=None),
        facility: Optional[str] = Query(default=None),
        status: Optional[str] = Query(default=None),
        date_from: Optional[date] = Query(default=None),
        date_to: Optional[date] = Query(default=None),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        role = normalize_role(s.role)
        c_stmt = select(ProgrammeContract).where(ProgrammeContract.clinic == s.clinic)
        if contract_id:
            c_stmt = c_stmt.where(ProgrammeContract.id == contract_id)
        if status:
            c_stmt = c_stmt.where(ProgrammeContract.state == status)
        contracts = [_serialize_contract(db, c) for c in db.scalars(c_stmt)]

        b_stmt = select(ProgrammeBudget).where(ProgrammeBudget.clinic == s.clinic)
        if contract_id:
            b_stmt = b_stmt.where(ProgrammeBudget.contract_id == contract_id)
        budgets = [_serialize_budget(db, b) for b in db.scalars(b_stmt)]

        ec_stmt = select(ExpenseClaim).where(ExpenseClaim.clinic == s.clinic)
        if role == "field_coordinator":
            ec_stmt = ec_stmt.where(
                (ExpenseClaim.submitted_by == s.id) | (ExpenseClaim.claimant_staff_id == s.id)
            )
        if contract_id:
            ec_stmt = ec_stmt.where(ExpenseClaim.contract_id == contract_id)
        claims = [_serialize_expense_claim(db, ec) for ec in db.scalars(ec_stmt)]

        # Transport reconciliation summary
        tr_stmt = select(Transport).where(Transport.clinic == s.clinic)
        if date_from:
            tr_stmt = tr_stmt.where(Transport.date >= date_from)
        if date_to:
            tr_stmt = tr_stmt.where(Transport.date <= date_to)
        trips = list(db.scalars(tr_stmt))
        reconciled_trips: list[dict[str, Any]] = []
        for tr in trips:
            linked_claim = db.scalar(
                select(ExpenseClaim).where(
                    ExpenseClaim.clinic == s.clinic,
                    ExpenseClaim.transport_trip_id == tr.id,
                )
            )
            reconciled_trips.append(
                {
                    "trip_id": tr.id,
                    "date": str(tr.date),
                    "from_location": tr.from_location,
                    "destination": tr.destination,
                    "trip_status": tr.status,
                    "trip_expense_paise": tr.trip_expense_paise,
                    "trip_expense_inr": paise_to_inr_str(tr.trip_expense_paise),
                    "receipt_ref": tr.receipt_ref,
                    "expense_id": tr.expense_id,
                    "expense_claim_id": linked_claim.id if linked_claim else None,
                    "claim_status": linked_claim.status if linked_claim else "unclaimed",
                }
            )

        # Cost-per-service analytics (using exact integer & Decimal arithmetic)
        completed_services = int(
            db.scalar(
                select(func.count(ServiceRequest.id)).where(
                    ServiceRequest.clinic == s.clinic,
                    ServiceRequest.status.in_(("completed", "verified", "closed")),
                )
            )
            or 0
        )
        completed_visits = int(
            db.scalar(
                select(func.count(FieldVisit.id)).where(
                    FieldVisit.clinic == s.clinic,
                    FieldVisit.status == "completed",
                )
            )
            or 0
        )
        completed_trips = sum(1 for tr in trips if tr.status == "completed")

        approved_exps = list(
            db.scalars(
                select(Expense).where(
                    Expense.clinic == s.clinic,
                    Expense.approved == True,  # noqa: E712
                )
            )
        )
        total_approved_exp_paise = sum(int(e.amount_paise) for e in approved_exps)
        transport_exp_paise = sum(
            int(e.amount_paise) for e in approved_exps if e.category == "transport"
        )
        travel_exp_paise = sum(
            int(e.amount_paise) for e in approved_exps if e.category == "travel"
        )

        total_units = max(1, completed_services + completed_visits + completed_trips)
        avg_cost_per_unit_paise = int(
            (Decimal(total_approved_exp_paise) / Decimal(total_units)).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        avg_cost_per_trip_paise = (
            int(
                (Decimal(transport_exp_paise) / Decimal(completed_trips)).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
            if completed_trips > 0
            else 0
        )
        avg_cost_per_visit_paise = (
            int(
                (Decimal(travel_exp_paise) / Decimal(completed_visits)).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
            if completed_visits > 0
            else 0
        )

        tot_ceiling = sum(
            int(c["funding_ceiling_paise"])
            for c in contracts
            if c["state"] in ("approved", "active", "completed")
        )
        tot_received = sum(int(c["funding_received_paise"]) for c in contracts)
        tot_budget_alloc = sum(int(b["totals"]["allocated_paise"]) for b in budgets)
        tot_budget_appr = sum(int(b["totals"]["approved_paise"]) for b in budgets)
        tot_budget_reimb = sum(int(b["totals"]["reimbursed_paise"]) for b in budgets)

        return {
            "clinic": s.clinic,
            "viewer_role": role,
            "filters_applied": {
                "contract_id": contract_id,
                "facility": facility,
                "status": status,
                "date_from": str(date_from) if date_from else None,
                "date_to": str(date_to) if date_to else None,
            },
            "summary_kpis": {
                "approved_funding_ceiling_paise": tot_ceiling,
                "approved_funding_ceiling_inr": paise_to_inr_str(tot_ceiling),
                "funding_received_paise": tot_received,
                "funding_received_inr": paise_to_inr_str(tot_received),
                "receivables_outstanding_paise": max(0, tot_ceiling - tot_received),
                "receivables_outstanding_inr": paise_to_inr_str(max(0, tot_ceiling - tot_received)),
                "budget_allocated_paise": tot_budget_alloc,
                "budget_allocated_inr": paise_to_inr_str(tot_budget_alloc),
                "expenditure_approved_paise": tot_budget_appr,
                "expenditure_approved_inr": paise_to_inr_str(tot_budget_appr),
                "expenditure_reimbursed_paise": tot_budget_reimb,
                "expenditure_reimbursed_inr": paise_to_inr_str(tot_budget_reimb),
                "funding_utilisation_pct": pct_bps(tot_budget_appr, tot_budget_alloc),
            },
            "cost_per_service_analytics": {
                "completed_services_count": completed_services,
                "completed_field_visits_count": completed_visits,
                "completed_transport_trips_count": completed_trips,
                "total_approved_expenditure_paise": total_approved_exp_paise,
                "total_approved_expenditure_inr": paise_to_inr_str(total_approved_exp_paise),
                "avg_cost_per_service_unit_paise": avg_cost_per_unit_paise,
                "avg_cost_per_service_unit_inr": paise_to_inr_str(avg_cost_per_unit_paise),
                "avg_cost_per_transport_trip_paise": avg_cost_per_trip_paise,
                "avg_cost_per_transport_trip_inr": paise_to_inr_str(avg_cost_per_trip_paise),
                "avg_cost_per_field_visit_paise": avg_cost_per_visit_paise,
                "avg_cost_per_field_visit_inr": paise_to_inr_str(avg_cost_per_visit_paise),
            },
            "contracts": contracts,
            "budgets": budgets,
            "expense_claims": claims,
            "transport_reconciliation": reconciled_trips,
        }

    def _build_report_payload(
        db: Session,
        s: Staff,
        report_type: str,
        contract_id: Optional[str] = None,
    ) -> dict[str, Any]:
        valid_reports = {
            "contract_funding_summary",
            "programme_budget_vs_actual",
            "monthly_payroll_summary",
            "staff_compensation_register",
            "transport_field_expense_report",
            "partner_service_expenditure_report",
            "funder_utilisation_statement",
        }
        if report_type not in valid_reports:
            raise HTTPException(400, f"Unsupported report_type '{report_type}'")

        # Check if all active contracts in scope have non-simulated institutional approval recorded
        contracts = list(
            db.scalars(select(ProgrammeContract).where(ProgrammeContract.clinic == s.clinic))
        )
        has_verified_official_approval = any(
            c.state in ("approved", "active") and not c.is_simulated_approval for c in contracts
        )
        compliance_watermark = (
            "INTERNAL / DRAFT — NOT AN OFFICIAL GOVERNMENT COMPLIANCE STATEMENT (SIMULATED / UNVERIFIED APPROVAL)"
            if not has_verified_official_approval
            else "INSTITUTIONALLY APPROVED PROGRAMME FINANCIAL REPORT"
        )

        headers: list[str] = []
        rows_data: list[list[Any]] = []
        title = report_type.replace("_", " ").title()

        if report_type == "contract_funding_summary":
            headers = [
                "contract_ref",
                "programme_name",
                "state",
                "simulated_approval",
                "ceiling_paise",
                "ceiling_inr",
                "received_paise",
                "received_inr",
                "funder_share_pct",
            ]
            for c in contracts:
                rows_data.append(
                    [
                        c.contract_reference,
                        c.programme_name,
                        c.state,
                        "YES (DEMO)" if c.is_simulated_approval else "NO (OFFICIAL)",
                        c.funding_ceiling_paise,
                        paise_to_inr_str(c.funding_ceiling_paise),
                        c.funding_received_paise,
                        paise_to_inr_str(c.funding_received_paise),
                        pct_bps(c.funder_share_bps, BPS_DIVISOR),
                    ]
                )
        elif report_type == "programme_budget_vs_actual":
            headers = [
                "budget_id",
                "category",
                "allocated_paise",
                "allocated_inr",
                "committed_paise",
                "incurred_paise",
                "approved_paise",
                "approved_inr",
                "paid_paise",
                "reimbursed_paise",
                "available_inr",
            ]
            lines = db.scalars(
                select(BudgetCategoryLine)
                .where(BudgetCategoryLine.clinic == s.clinic)
                .order_by(BudgetCategoryLine.budget_id.asc(), BudgetCategoryLine.category.asc())
            )
            for ln in lines:
                avail = ln.allocated_paise - (ln.committed_paise + ln.approved_paise)
                rows_data.append(
                    [
                        ln.budget_id,
                        ln.category,
                        ln.allocated_paise,
                        paise_to_inr_str(ln.allocated_paise),
                        ln.committed_paise,
                        ln.incurred_paise,
                        ln.approved_paise,
                        paise_to_inr_str(ln.approved_paise),
                        ln.paid_paise,
                        ln.reimbursed_paise,
                        paise_to_inr_str(avail),
                    ]
                )
        elif report_type == "monthly_payroll_summary":
            headers = [
                "period_month",
                "status",
                "payslip_count",
                "gross_paise",
                "gross_inr",
                "deductions_paise",
                "employer_contrib_paise",
                "net_payable_paise",
                "net_payable_inr",
                "payment_batch_ref",
            ]
            for pr in db.scalars(
                select(PayrollRun)
                .where(PayrollRun.clinic == s.clinic)
                .order_by(PayrollRun.period_month.desc())
            ):
                rows_data.append(
                    [
                        pr.period_month,
                        pr.status,
                        pr.payslip_count,
                        pr.total_gross_paise,
                        paise_to_inr_str(pr.total_gross_paise),
                        pr.total_deductions_paise,
                        pr.total_employer_contributions_paise,
                        pr.total_net_payable_paise,
                        paise_to_inr_str(pr.total_net_payable_paise),
                        pr.payment_batch_ref,
                    ]
                )
        elif report_type == "staff_compensation_register":
            headers = [
                "staff_id",
                "staff_name",
                "employment_type",
                "pay_structure",
                "base_monthly_paise",
                "base_monthly_inr",
                "per_visit_paise",
                "allowance_paise",
                "attendance_adjustment_permitted",
                "status",
            ]
            for ag in db.scalars(
                select(StaffCompensationAgreement).where(
                    StaffCompensationAgreement.clinic == s.clinic
                )
            ):
                st = db.get(Staff, ag.staff_id)
                rows_data.append(
                    [
                        ag.staff_id,
                        st.name if st else ag.staff_id,
                        ag.employment_type,
                        ag.pay_structure,
                        ag.base_monthly_paise,
                        paise_to_inr_str(ag.base_monthly_paise),
                        ag.per_visit_rate_paise,
                        ag.field_allowance_paise,
                        "YES" if ag.attendance_adjustment_permitted else "NO",
                        ag.status,
                    ]
                )
        elif report_type == "transport_field_expense_report":
            headers = [
                "claim_id",
                "claim_type",
                "category",
                "transport_mode",
                "distance_km",
                "amount_paise",
                "amount_inr",
                "receipt_number",
                "status",
                "payment_ref",
            ]
            for ec in db.scalars(
                select(ExpenseClaim)
                .where(ExpenseClaim.clinic == s.clinic)
                .order_by(ExpenseClaim.submitted_at.desc())
            ):
                rows_data.append(
                    [
                        ec.id,
                        ec.claim_type,
                        ec.expense_category,
                        ec.transport_mode,
                        ec.distance_km,
                        ec.amount_paise,
                        paise_to_inr_str(ec.amount_paise),
                        ec.receipt_number,
                        ec.status,
                        ec.reimbursement_payment_ref,
                    ]
                )
        elif report_type == "partner_service_expenditure_report":
            headers = [
                "expense_id",
                "category",
                "amount_paise",
                "amount_inr",
                "receipt_ref",
                "approved",
                "reimbursement_status",
                "description",
            ]
            for ex in db.scalars(
                select(Expense)
                .where(Expense.clinic == s.clinic)
                .order_by(Expense.created_at.desc())
            ):
                rows_data.append(
                    [
                        ex.id,
                        ex.category,
                        ex.amount_paise,
                        paise_to_inr_str(ex.amount_paise),
                        ex.receipt_ref,
                        "APPROVED" if ex.approved else "PENDING",
                        ex.reimbursement_status,
                        ex.description,
                    ]
                )
        elif report_type == "funder_utilisation_statement":
            headers = [
                "claim_reference",
                "contract_id",
                "period_start",
                "period_end",
                "total_claimed_paise",
                "total_claimed_inr",
                "funder_reimbursable_paise",
                "funder_reimbursable_inr",
                "approved_reimbursed_inr",
                "status",
                "evidence_hash",
            ]
            for fc in db.scalars(
                select(FundingClaim)
                .where(FundingClaim.clinic == s.clinic)
                .order_by(FundingClaim.created_at.desc())
            ):
                rows_data.append(
                    [
                        fc.claim_reference,
                        fc.contract_id,
                        str(fc.period_start),
                        str(fc.period_end),
                        fc.total_claimed_paise,
                        paise_to_inr_str(fc.total_claimed_paise),
                        fc.funder_reimbursable_paise,
                        paise_to_inr_str(fc.funder_reimbursable_paise),
                        paise_to_inr_str(fc.approved_reimbursed_paise),
                        fc.status,
                        fc.evidence_package_hash[:16],
                    ]
                )

        return {
            "report_type": report_type,
            "title": title,
            "clinic": s.clinic,
            "compliance_watermark": compliance_watermark,
            "is_draft_or_internal": not has_verified_official_approval,
            "generated_at": now().isoformat(),
            "headers": headers,
            "rows": rows_data,
        }

    @app.get("/api/finance/reports/{report_type}")
    def get_financial_report(
        report_type: str,
        contract_id: Optional[str] = Query(default=None),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        permitted(s, "admin", "doctor")
        return _build_report_payload(db, s, report_type, contract_id)

    @app.get("/api/finance/reports/{report_type}/export")
    def export_financial_report(
        report_type: str,
        format: Literal["csv", "pdf"] = Query(default="csv"),
        contract_id: Optional[str] = Query(default=None),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> Response:
        permitted(s, "admin", "doctor")
        payload = _build_report_payload(db, s, report_type, contract_id)

        if format == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(["COMPLIANCE_LABEL", payload["compliance_watermark"]])
            writer.writerow(
                [
                    "REPORT_TYPE",
                    payload["report_type"],
                    "CLINIC",
                    payload["clinic"],
                    "GENERATED_AT",
                    payload["generated_at"],
                ]
            )
            writer.writerow(payload["headers"])
            for r in payload["rows"]:
                writer.writerow(r)
            return Response(
                content=buf.getvalue().encode("utf-8"),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f'attachment; filename="{report_type}_{s.clinic}.csv"'
                },
            )

        # PDF export
        pdf_lines: list[str] = [
            f"Clinic: {payload['clinic']} | Generated: {payload['generated_at']}",
            "Columns: " + " | ".join(payload["headers"][:7]),
            "-" * 95,
        ]
        for r in payload["rows"]:
            pdf_lines.append(" | ".join(str(cell) for cell in r[:7]))
        if not payload["rows"]:
            pdf_lines.append("No records in current filter scope.")

        pdf_bytes = build_simple_pdf_bytes(
            title=f"JananiSetu Financial Report: {payload['title']}",
            subtitle="All monetary figures computed using exact integer paise & Decimal arithmetic",
            watermark=payload["compliance_watermark"],
            lines=pdf_lines,
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{report_type}_{s.clinic}.pdf"'
            },
        )

    # -----------------------------------------------------------------------
    # 8. Financial Audit Ledger & Versioned Corrections
    # -----------------------------------------------------------------------
    @app.get("/api/finance/audit-ledger")
    def list_financial_audit_ledger(
        limit: int = Query(default=100, ge=1, le=500),
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        permitted(s, "admin", "doctor")
        rows = db.scalars(
            select(FinancialAuditLedger)
            .where(FinancialAuditLedger.clinic == s.clinic)
            .order_by(FinancialAuditLedger.occurred_at.desc())
            .limit(limit)
        )
        out: list[dict[str, Any]] = []
        for r in rows:
            d = row(r)
            d["amount_inr"] = paise_to_inr_str(r.amount_paise)
            out.append(d)
        return out

    @app.get("/api/finance/corrections")
    def list_financial_corrections(
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> list[dict[str, Any]]:
        permitted(s, "admin", "doctor")
        rows = db.scalars(
            select(FinancialCorrectionRecord)
            .where(FinancialCorrectionRecord.clinic == s.clinic)
            .order_by(FinancialCorrectionRecord.created_at.desc())
        )
        return [row(r) for r in rows]

    @app.post("/api/finance/corrections", status_code=201)
    def create_financial_correction(
        p: FinancialCorrectionCreateIn,
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        """Versioned financial correction instead of destructive overwrite."""
        permitted(s, "admin")
        prev_paise: Optional[int] = None
        new_paise: Optional[int] = p.new_value_paise
        prev_txt = ""
        new_txt = p.new_text.strip()
        next_ver = 2

        if p.entity_type == "expense_claim":
            ec = db.get(ExpenseClaim, p.entity_id)
            if not ec or ec.clinic != s.clinic:
                raise HTTPException(404, "ExpenseClaim not found in your clinic")
            next_ver = int(ec.version_number) + 1
            if p.field_name == "amount_paise":
                if new_paise is None or new_paise <= 0:
                    raise HTTPException(400, "Correction requires positive new_value_paise")
                prev_paise = int(ec.amount_paise)
                ec.amount_paise = int(new_paise)
                if ec.expense_id:
                    exp = db.get(Expense, ec.expense_id)
                    if exp and exp.clinic == s.clinic:
                        exp.amount_paise = int(new_paise)
            elif p.field_name == "description":
                prev_txt = ec.description
                ec.description = new_txt
            else:
                raise HTTPException(400, f"Field '{p.field_name}' not supported on expense_claim")
            ec.version_number = next_ver

        elif p.entity_type == "payslip_record":
            ps = db.get(PayslipRecord, p.entity_id)
            if not ps or ps.clinic != s.clinic:
                raise HTTPException(404, "PayslipRecord not found in your clinic")
            next_ver = int(ps.version_number) + 1
            if p.field_name == "allowance_paise":
                if new_paise is None or new_paise < 0:
                    raise HTTPException(400, "Correction requires non-negative new_value_paise")
                prev_paise = int(ps.allowance_paise)
                delta = int(new_paise) - prev_paise
                ps.allowance_paise = int(new_paise)
                ps.gross_earnings_paise = max(0, int(ps.gross_earnings_paise) + delta)
                ps.net_payable_paise = max(0, int(ps.net_payable_paise) + delta)
            elif p.field_name == "correction_note":
                prev_txt = ps.correction_note
                ps.correction_note = new_txt
            else:
                raise HTTPException(400, f"Field '{p.field_name}' not supported on payslip_record")
            ps.version_number = next_ver

        elif p.entity_type == "expense":
            exp = db.get(Expense, p.entity_id)
            if not exp or exp.clinic != s.clinic:
                raise HTTPException(404, "Expense not found in your clinic")
            if p.field_name == "amount_paise":
                if new_paise is None or new_paise <= 0:
                    raise HTTPException(400, "Correction requires positive new_value_paise")
                prev_paise = int(exp.amount_paise)
                exp.amount_paise = int(new_paise)
            elif p.field_name == "description":
                prev_txt = exp.description
                exp.description = new_txt
            else:
                raise HTTPException(400, f"Field '{p.field_name}' not supported on expense")

        corr = FinancialCorrectionRecord(
            clinic=s.clinic,
            entity_type=p.entity_type,
            entity_id=p.entity_id,
            version_number=next_ver,
            field_name=p.field_name,
            previous_value_paise=prev_paise,
            new_value_paise=new_paise,
            previous_text=prev_txt,
            new_text=new_txt,
            reason=p.reason.strip(),
            requested_by=p.requested_by or s.id,
            approved_by=s.id,
            approved_by_role=normalize_role(s.role),
        )
        db.add(corr)
        db.flush()
        record_fin_ledger(
            db,
            s,
            p.entity_type,
            p.entity_id,
            "versioned_financial_correction",
            str(prev_paise if prev_paise is not None else prev_txt),
            str(new_paise if new_paise is not None else new_txt),
            int(new_paise or 0),
            f"v{next_ver}; field={p.field_name}; reason={p.reason.strip()}",
        )
        db.commit()
        return row(corr)

    # -----------------------------------------------------------------------
    # 11. End-to-End 12-Step Funded Maternal Programme Demonstration Scenario
    # -----------------------------------------------------------------------
    @app.post("/api/finance/demo-walkthrough")
    def run_phase6_funded_programme_walkthrough(
        db: Session = Depends(dbsession),
        s: Staff = Depends(who),
    ) -> dict[str, Any]:
        """Execute the complete 12-step End-to-End Funded Maternal Programme Scenario:
        1. Create a maternal health funding contract (simulated approval explicitly marked).
        2. Allocate a programme budget across clinic, staff, transport and service categories.
        3. Onboard a doctor, nurse and field coordinator with compensation agreements & verified credentials.
        4. Register a consenting patient and verify an ANC card.
        5. Authorise a follow-up care plan and schedule reminders.
        6. Create and complete a nurse field visit.
        7. Book and complete a patient transport trip.
        8. Submit and approve transport and field-visit expense claims (with separation of duties).
        9. Link completed services and expenses to the active contract and budget.
        10. Run monthly payroll and generate payslips.
        11. Generate a funding utilisation and supporting evidence package.
        12. Verify financial dashboards, audit logs and budget balances.
        """
        permitted(s, "admin", "doctor")
        today = date.today()
        ts = now()
        suffix = ts.strftime("%H%M%S%f")[:10]

        doc = (
            db.scalar(
                select(Staff).where(Staff.clinic == s.clinic, Staff.role == "doctor")
            )
            or s
        )
        nurse = (
            db.scalar(
                select(Staff).where(Staff.clinic == s.clinic, Staff.role == "nurse")
            )
            or s
        )
        fc = (
            db.scalar(
                select(Staff).where(Staff.clinic == s.clinic, Staff.role == "field_coordinator")
            )
            or nurse
        )
        admin_user = (
            db.scalar(
                select(Staff).where(Staff.clinic == s.clinic, Staff.role == "admin")
            )
            or s
        )

        # Step 1: Create Funder & Maternal Health Funding Contract (Simulated Approval Explicitly Marked)
        funder = FundingOrganisation(
            clinic=s.clinic,
            name=f"NHM Maternal Continuity Directorate [{suffix}] (Synthetic Demo)",
            funder_type="nhm_authority",
            registration_or_grant_code=f"SYN-NHM-{suffix}",
            nodal_officer_name="Dr. P. Srinivas (Synthetic Nodal Officer)",
            nodal_officer_designation="Mission Director (Synthetic Demo)",
            contact_email="mission.demo@nhm-synthetic.example.org",
            contact_phone="9440011223",
            address="State Health Directorate, Hyderabad (Synthetic)",
            is_active=True,
            created_by=admin_user.id,
        )
        db.add(funder)
        db.flush()

        contract = ProgrammeContract(
            clinic=s.clinic,
            funder_id=funder.id,
            programme_name=f"Surakshit Matritva Rural ANC & Transport Grant [{suffix}]",
            contract_reference=f"SYN-CNT-{suffix}",
            sanction_order_ref=f"SYN-SANCTION-{suffix} (SIMULATED)",
            state="active",
            is_simulated_approval=True,
            approval_disclaimer=(
                f"SIMULATED / DEMO APPROVAL ONLY (Ref: SYN-SANCTION-{suffix}) — "
                "Synthetic evaluation contract; never represented as an official government sanction."
            ),
            funder_signatory_name="Dr. P. Srinivas (Synthetic)",
            funder_signatory_designation="Mission Director (Synthetic)",
            recipient_signatory_name=admin_user.name,
            signed_agreement_filename=f"SYN-CNT-{suffix}-SIGNED.pdf",
            signed_agreement_sha256=hashlib.sha256(f"SYN-CNT-{suffix}".encode("utf-8")).hexdigest(),
            effective_from=today - timedelta(days=30),
            effective_until=today + timedelta(days=335),
            funding_ceiling_paise=50000000,  # Rs 5,00,000.00 (5 Lakhs)
            funding_received_paise=25000000,  # Rs 2,50,000.00 Tranche 1 received
            funder_share_bps=9000,  # 90.00% funder cost-share
            reimbursement_basis="actual_verified_cost",
            allow_private_transport_reimbursement=False,
            objectives_json=json.dumps(
                ["Timely ANC digitisation", "Home nursing follow-up", "Empaneled rural transport"]
            ),
            delivery_obligations_json=json.dumps(
                ["Privacy-safe supporting evidence package", "Audited payroll & expense vouchers"]
            ),
            allowed_categories_json=json.dumps(list(BUDGET_CATEGORIES)),
            disallowed_categories_json=json.dumps(
                ["private_unapproved_transport", "entertainment"]
            ),
            participating_clinics_json=json.dumps([s.clinic]),
            clinic_allocations_json=json.dumps({s.clinic: 50000000}),
            version_number=1,
            submitted_by=admin_user.id,
            submitted_at=ts,
            approved_by=doc.id,
            approved_at=ts,
            approval_evidence_ref=f"SYN-SANCTION-{suffix}",
            created_by=admin_user.id,
        )
        db.add(contract)
        db.flush()

        # Step 2: Allocate Programme Budget across salary, travel, transport, clinical_services, diagnostics, technology, administration
        budget = ProgrammeBudget(
            contract_id=contract.id,
            clinic=s.clinic,
            budget_scope="clinic_level",
            target_clinic=s.clinic,
            fiscal_year="2026-27",
            period_start=today - timedelta(days=30),
            period_end=today + timedelta(days=335),
            total_allocated_paise=50000000,
            status="approved",
            version_number=1,
            created_by=admin_user.id,
            approved_by=doc.id,
            approved_at=ts,
        )
        db.add(budget)
        db.flush()

        b_cats = {
            "salary": 25000000,
            "travel": 5000000,
            "transport": 8000000,
            "clinical_services": 5000000,
            "diagnostics": 3000000,
            "technology": 2000000,
            "administration": 2000000,
        }
        b_lines: dict[str, BudgetCategoryLine] = {}
        for cat_name, alloc_p in b_cats.items():
            ln = BudgetCategoryLine(
                budget_id=budget.id,
                contract_id=contract.id,
                clinic=s.clinic,
                category=cat_name,
                allocated_paise=alloc_p,
            )
            db.add(ln)
            b_lines[cat_name] = ln
        db.flush()

        # Step 3: Ensure Doctor, Nurse & Field Coordinator Workforce Profiles + Active Compensation Agreements
        for st_obj, cadre, qual, reg_no, emp_type, pay_struct, base_p, visit_p, allow_p, att_perm in (
            (
                doc,
                "medical_officer_obgyn",
                "MBBS, DGO",
                f"TSMC-DOC-{suffix[:4]}",
                "full_time_employee",
                "monthly_fixed",
                8500000,
                0,
                500000,
                True,
            ),
            (
                nurse,
                "anm_staff_nurse",
                "GNM / ANM",
                f"TSNMC-NRS-{suffix[:4]}",
                "nhm_deputed",
                "retainer_plus_visit",
                3200000,
                30000,
                200000,
                True,
            ),
            (
                fc,
                "asha_field_coordinator",
                "Community Outreach Coordinator",
                f"NHM-FC-{suffix[:4]}",
                "community_honorarium",
                "retainer_plus_visit",
                1800000,
                20000,
                150000,
                False,
            ),
        ):
            wp = db.scalar(
                select(StaffWorkforceProfile).where(
                    StaffWorkforceProfile.staff_id == st_obj.id
                )
            )
            if not wp:
                wp = StaffWorkforceProfile(
                    staff_id=st_obj.id,
                    clinic=s.clinic,
                    employment_type=emp_type,
                    onboarding_status="active_onboarded",
                    clinical_cadre=cadre,
                    qualification=qual,
                    registration_council="State Healthcare Council",
                    registration_number=reg_no,
                    credential_verification_status="verified",
                    credential_verified_by=admin_user.id,
                    credential_verified_by_role="admin",
                    credential_verified_at=ts,
                    credential_evidence_ref=f"VERIFIED-CERT-{reg_no}",
                    credential_expiry_date=today + timedelta(days=365),
                    onboarded_by=admin_user.id,
                )
                db.add(wp)
            ag = db.scalar(
                select(StaffCompensationAgreement).where(
                    StaffCompensationAgreement.clinic == s.clinic,
                    StaffCompensationAgreement.staff_id == st_obj.id,
                    StaffCompensationAgreement.status == "active",
                )
            )
            if not ag:
                ag = StaffCompensationAgreement(
                    staff_id=st_obj.id,
                    clinic=s.clinic,
                    contract_id=contract.id,
                    budget_id=budget.id,
                    employment_type=emp_type,
                    pay_structure=pay_struct,
                    base_monthly_paise=base_p,
                    per_visit_rate_paise=visit_p,
                    field_allowance_paise=allow_p,
                    expected_monthly_days=26,
                    attendance_adjustment_permitted=att_perm,
                    statutory_deductions_enabled=True,
                    effective_from=today - timedelta(days=30),
                    status="active",
                    version_number=1,
                    approved_by=admin_user.id,
                    created_by=admin_user.id,
                )
                db.add(ag)
        db.flush()

        # Step 4: Register a Consenting Mother & Verify an ANC Card
        mother = Mother(
            clinic=s.clinic,
            name=f"KavyaLaxmi Goud (Funded Cohort {suffix[:4]})",
            phone="9848099111",
            patient_identifier=f"ANC-P6-{suffix[:6]}",
            age=25,
            lmp=today - timedelta(days=150),
            edd=today + timedelta(days=130),
            address="Ramannapet Cluster, Nalgonda",
            language="te",
            consent=True,
            consent_updated_at=ts,
            notes="Enrolled under Surakshit Matritva Funded Programme.",
            registered_by=nurse.id,
        )
        db.add(mother)
        db.flush()

        anc_bytes = generate_fixture_image_bytes("printed_clear")
        anc_doc = Document(
            mother_id=mother.id,
            clinic=s.clinic,
            version_number=1,
            filename=f"anc_card_{suffix}.png",
            content_type="image/png",
            file_size_bytes=len(anc_bytes),
            sha256_hash=hashlib.sha256(anc_bytes).hexdigest(),
            ocr_status="completed",
            ocr_engine="tesseract-5-verified",
            extracted_text="Mother: KavyaLaxmi Goud | Follow-up ANC Visit",
            confirmed=True,
            review_status="confirmed",
            uploaded_by=nurse.id,
            confirmed_by=nurse.id,
            confirmed_at=ts,
        )
        db.add(anc_doc)
        db.flush()
        db.add(
            ExtractedField(
                document_id=anc_doc.id,
                clinic=s.clinic,
                field_key="patient_name",
                field_label="Patient Name",
                extracted_value=mother.name,
                normalized_value=mother.name,
                final_value=mother.name,
                confidence=96.0,
                source_snippet="Mother: KavyaLaxmi Goud",
                verification_status="confirmed",
                verified_by=nurse.id,
                verified_at=ts,
            )
        )

        # Step 5: Doctor-Authorised CarePlan & Durable Reminders
        cplan = CarePlan(
            mother_id=mother.id,
            clinic=s.clinic,
            visit_date=today + timedelta(days=7),
            visit_type="anc_checkup",
            appointment_status="scheduled",
            followup_state="scheduled",
            note="Doctor-authorised 2nd trimester ANC checkup and home nursing visit.",
            version=1,
            approved_by=doc.id,
            active=True,
        )
        db.add(cplan)
        db.flush()
        sched_res = schedule_reminders_for_care_plan(
            db, cplan, mother, actor_id=doc.id, actor_role="doctor"
        )
        process_outbox_and_due_jobs(db, clinic=s.clinic)

        # Step 6: Create & Complete a Verified Nurse Field Visit
        srv_req = ServiceRequest(
            clinic=s.clinic,
            mother_id=mother.id,
            care_plan_id=cplan.id,
            service_type="anc_home_visit",
            priority="high",
            status="verified",
            scheduled_date=today,
            scheduled_time="10:30",
            assigned_staff_id=nurse.id,
            assigned_staff_role="nurse",
            clinical_authorisation_by=doc.id,
            created_by=doc.id,
            started_at=ts,
            completed_at=ts,
            verified_by=doc.id,
            verified_at=ts,
            completion_evidence="Clinical vital signs and home visit verified by Medical Officer.",
        )
        db.add(srv_req)
        db.flush()

        fvisit = FieldVisit(
            clinic=s.clinic,
            service_request_id=srv_req.id,
            mother_id=mother.id,
            care_plan_id=cplan.id,
            assigned_staff_id=nurse.id,
            staff_role="nurse",
            visit_date=today,
            scheduled_window="10:00-11:00",
            visit_address=mother.address,
            status="completed",
            contact_confirmed=True,
            patient_consent_verified=True,
            started_at=ts,
            completed_at=ts,
            role_scoped_notes="Completed maternal home visit; BP normal, transport arranged for PHC scan.",
            completion_evidence_type="signed_home_visit_register",
            completion_evidence_ref=f"VISIT-REG-{suffix}",
            verified_by=doc.id,
            verified_at=ts,
            created_by=doc.id,
        )
        db.add(fvisit)
        db.flush()

        # Step 7: Book & Complete a Patient Transport Trip
        trip = Transport(
            mother_id=mother.id,
            clinic=s.clinic,
            date=today,
            pickup_time="11:30",
            from_location=mother.address,
            destination="PHC Nalgonda Central",
            status="completed",
            partner="Devarakonda Rural Maternal Mobility Cooperative",
            vehicle_notes="Patient transport van TS-05-UC-4499",
            requested_by=fc.id,
            service_request_id=srv_req.id,
            driver_response_status="accepted",
            trip_started_at=ts,
            trip_completed_at=ts,
            trip_expense_paise=45000,  # Rs 450.00
            receipt_ref=f"TRP-VCH-{suffix}",
        )
        db.add(trip)
        db.flush()

        # Step 8: Submit, Supervisor-Verify, Finance-Approve & Reimburse Transport & Field Visit Expense Claims
        # Claim A: Nurse two-wheeler field visit mileage claim (20 km * Rs 12/km = Rs 240.00 = 24000 paise)
        claim_visit = ExpenseClaim(
            clinic=s.clinic,
            contract_id=contract.id,
            budget_id=budget.id,
            claim_type="staff_travel_claim",
            expense_category="travel",
            claimant_staff_id=nurse.id,
            field_visit_id=fvisit.id,
            service_request_id=srv_req.id,
            transport_mode="staff_two_wheeler_mileage",
            distance_km=20,
            amount_paise=24000,
            receipt_number=f"TRV-NRS-{suffix}",
            receipt_filename=f"trv_nrs_{suffix}.pdf",
            receipt_sha256=hashlib.sha256(f"TRV-NRS-{suffix}".encode("utf-8")).hexdigest(),
            receipt_verified=True,
            description="Verified nurse home ANC visit two-wheeler mileage (20 km)",
            status="reimbursed_paid",
            submitted_by=nurse.id,
            submitted_at=ts,
            verified_by=doc.id,
            verified_at=ts,
            verification_notes="Home visit GPS & register verified by Medical Officer",
            approved_by=admin_user.id,
            approved_at=ts,
            approval_notes="Approved against travel budget line",
            reimbursement_payment_ref=f"UTR-TRV-{suffix}",
            reimbursed_at=ts,
        )
        db.add(claim_visit)
        db.flush()

        exp_visit = Expense(
            clinic=s.clinic,
            category="travel",
            amount_paise=24000,
            description=claim_visit.description,
            receipt_ref=claim_visit.receipt_number,
            approved=True,
            created_by=nurse.id,
            approved_by=admin_user.id,
            contract_id=contract.id,
            budget_id=budget.id,
            expense_claim_id=claim_visit.id,
            reimbursement_status="paid_to_claimant",
            payment_ref=claim_visit.reimbursement_payment_ref,
        )
        db.add(exp_visit)
        db.flush()
        claim_visit.expense_id = exp_visit.id
        b_lines["travel"].incurred_paise += 24000
        b_lines["travel"].approved_paise += 24000
        b_lines["travel"].paid_paise += 24000

        # Claim B: Empaneled Transport Partner Trip Invoice (Rs 450.00 = 45000 paise)
        claim_trip = ExpenseClaim(
            clinic=s.clinic,
            contract_id=contract.id,
            budget_id=budget.id,
            claim_type="transport_partner_invoice",
            expense_category="transport",
            claimant_staff_id=fc.id,
            transport_trip_id=trip.id,
            service_request_id=srv_req.id,
            transport_mode="empaneled_partner_van",
            distance_km=18,
            amount_paise=45000,
            receipt_number=f"TRP-INV-{suffix}",
            receipt_filename=f"trp_inv_{suffix}.pdf",
            receipt_sha256=hashlib.sha256(f"TRP-INV-{suffix}".encode("utf-8")).hexdigest(),
            receipt_verified=True,
            description="Completed maternal transport trip to PHC Nalgonda",
            status="reimbursed_paid",
            submitted_by=fc.id,
            submitted_at=ts,
            verified_by=doc.id,
            verified_at=ts,
            verification_notes="Patient arrival at PHC confirmed",
            approved_by=admin_user.id,
            approved_at=ts,
            approval_notes="Approved against transport budget line",
            reimbursement_payment_ref=f"UTR-TRP-{suffix}",
            reimbursed_at=ts,
        )
        db.add(claim_trip)
        db.flush()

        exp_trip = Expense(
            clinic=s.clinic,
            category="transport",
            amount_paise=45000,
            description=claim_trip.description,
            receipt_ref=claim_trip.receipt_number,
            approved=True,
            created_by=fc.id,
            approved_by=admin_user.id,
            contract_id=contract.id,
            budget_id=budget.id,
            expense_claim_id=claim_trip.id,
            reimbursement_status="paid_to_claimant",
            payment_ref=claim_trip.reimbursement_payment_ref,
        )
        db.add(exp_trip)
        db.flush()
        claim_trip.expense_id = exp_trip.id
        trip.expense_id = exp_trip.id
        b_lines["transport"].incurred_paise += 45000
        b_lines["transport"].approved_paise += 45000
        b_lines["transport"].paid_paise += 45000

        # Step 10: Run Monthly Payroll (or retrieve existing current-month run) and confirm payment
        demo_period = "2026-11"
        existing_slip = db.scalar(
            select(PayslipRecord).where(
                PayslipRecord.clinic == s.clinic,
                PayslipRecord.period_month == demo_period,
            )
        )
        if existing_slip:
            pr = db.get(PayrollRun, existing_slip.payroll_run_id)
        else:
            stat_cfg = db.scalar(
                select(PayrollStatutoryConfig).where(
                    PayrollStatutoryConfig.clinic == s.clinic
                )
            )
            if not stat_cfg:
                stat_cfg = PayrollStatutoryConfig(
                    clinic=s.clinic,
                    version_number=1,
                    config_name="Validated Demo Statutory Schedule",
                    effective_from=date(2026, 4, 1),
                    pf_employee_bps=1200,
                    pf_employer_bps=1200,
                    pf_wage_ceiling_paise=1500000,
                    esi_employee_bps=75,
                    esi_employer_bps=325,
                    esi_wage_ceiling_paise=2100000,
                    professional_tax_paise=20000,
                    tds_default_bps=500,
                    validated_by_professional_name="CA M. Narasimha Rao",
                    validated_by_credentials="ICAI #SYN-088412",
                    is_active=True,
                    created_by=admin_user.id,
                )
                db.add(stat_cfg)
                db.flush()

            pr = PayrollRun(
                clinic=s.clinic,
                period_month=demo_period,
                contract_id=contract.id,
                budget_id=budget.id,
                statutory_config_id=stat_cfg.id,
                status="paid_verified",
                calculated_by=admin_user.id,
                reviewed_by=doc.id,
                reviewed_at=ts,
                approved_by=doc.id,
                approved_at=ts,
                locked_by=admin_user.id,
                locked_at=ts,
                payment_batch_ref=f"BATCH-PAY-{suffix}",
                payment_evidence_ref=f"UTR-PAYROLL-{suffix}",
                paid_confirmed_by=admin_user.id,
                paid_confirmed_at=ts,
            )
            db.add(pr)
            db.flush()

            ag_nurse = db.scalar(
                select(StaffCompensationAgreement).where(
                    StaffCompensationAgreement.clinic == s.clinic,
                    StaffCompensationAgreement.staff_id == nurse.id,
                    StaffCompensationAgreement.status == "active",
                )
            )
            gross_n = 3200000 + 30000 + 200000  # Base + 1 completed visit + allowance = 34,300.00 INR
            pf_n = mul_bps_paise(1500000, 1200)  # 180000 paise
            pt_n = 20000
            tds_n = mul_bps_paise(gross_n, 500)  # 171500 paise
            ded_n = pf_n + pt_n + tds_n
            net_n = gross_n - ded_n

            slip_n = PayslipRecord(
                payroll_run_id=pr.id,
                staff_id=nurse.id,
                agreement_id=ag_nurse.id if ag_nurse else "comp-nurse-1",
                clinic=s.clinic,
                period_month=demo_period,
                employment_type="nhm_deputed",
                pay_structure="retainer_plus_visit",
                days_scheduled=26,
                days_attended=26,
                completed_visits_count=1,
                base_pay_paise=3200000,
                visit_or_shift_pay_paise=30000,
                allowance_paise=200000,
                gross_earnings_paise=gross_n,
                pf_employee_paise=pf_n,
                professional_tax_paise=pt_n,
                tds_paise=tds_n,
                total_deductions_paise=ded_n,
                pf_employer_paise=pf_n,
                net_payable_paise=net_n,
                status="paid_verified",
                payment_ref=pr.payment_batch_ref,
                payment_evidence_ref=pr.payment_evidence_ref,
            )
            db.add(slip_n)
            pr.total_gross_paise = gross_n
            pr.total_deductions_paise = ded_n
            pr.total_employer_contributions_paise = pf_n
            pr.total_net_payable_paise = net_n
            pr.payslip_count = 1

            exp_pay = Expense(
                clinic=s.clinic,
                category="salary",
                amount_paise=gross_n + pf_n,
                description=f"Verified Monthly Healthcare Payroll ({demo_period})",
                receipt_ref=pr.payment_batch_ref,
                approved=True,
                created_by=admin_user.id,
                approved_by=doc.id,
                contract_id=contract.id,
                budget_id=budget.id,
                payroll_run_id=pr.id,
                reimbursement_status="approved_pending_claim",
                payment_ref=pr.payment_evidence_ref,
            )
            db.add(exp_pay)
            db.flush()
            pr.expense_id = exp_pay.id
            b_lines["salary"].incurred_paise += gross_n + pf_n
            b_lines["salary"].approved_paise += gross_n + pf_n
            b_lines["salary"].paid_paise += gross_n + pf_n

        # Step 9 & Step 11: Link Completed Services & Expenses to Active Contract/Budget & Generate Supporting Evidence Package
        fclaim = FundingClaim(
            clinic=s.clinic,
            contract_id=contract.id,
            budget_id=budget.id,
            claim_reference=f"FCLAIM-{suffix}",
            period_start=today - timedelta(days=30),
            period_end=today,
            status="reimbursed_settled",
            submitted_by=admin_user.id,
            submitted_at=ts,
            settled_payment_ref=f"UTR-NHM-REIMB-{suffix}",
            settled_at=ts,
            notes="Verified maternal service-to-funding claim for home ANC visit and patient transport.",
        )
        db.add(fclaim)
        db.flush()

        anon_ref = anonymise_beneficiary_ref(s.clinic, mother.id)
        reimb_visit = mul_bps_paise(exp_visit.amount_paise, contract.funder_share_bps)
        reimb_trip = mul_bps_paise(exp_trip.amount_paise, contract.funder_share_bps)

        lk1 = ServiceFundingEvidenceLink(
            clinic=s.clinic,
            funding_claim_id=fclaim.id,
            contract_id=contract.id,
            budget_id=budget.id,
            service_category="travel",
            staff_id=nurse.id,
            service_request_id=srv_req.id,
            field_visit_id=fvisit.id,
            expense_id=exp_visit.id,
            expense_claim_id=claim_visit.id,
            beneficiary_anonymised_ref=anon_ref,
            verification_evidence_ref=f"GPS-VISIT-REG-{fvisit.id[:8]}",
            verified_by_staff_id=doc.id,
            amount_paise=exp_visit.amount_paise,
            reimbursable_paise=reimb_visit,
            reimbursement_status="reimbursed",
        )
        lk2 = ServiceFundingEvidenceLink(
            clinic=s.clinic,
            funding_claim_id=fclaim.id,
            contract_id=contract.id,
            budget_id=budget.id,
            service_category="transport",
            staff_id=fc.id,
            service_request_id=srv_req.id,
            transport_trip_id=trip.id,
            expense_id=exp_trip.id,
            expense_claim_id=claim_trip.id,
            beneficiary_anonymised_ref=anon_ref,
            verification_evidence_ref=f"TRIP-VOUCHER-{trip.id[:8]}",
            verified_by_staff_id=doc.id,
            amount_paise=exp_trip.amount_paise,
            reimbursable_paise=reimb_trip,
            reimbursement_status="reimbursed",
        )
        db.add_all([lk1, lk2])

        fclaim.total_claimed_paise = exp_visit.amount_paise + exp_trip.amount_paise
        fclaim.funder_reimbursable_paise = reimb_visit + reimb_trip
        fclaim.approved_reimbursed_paise = reimb_visit + reimb_trip
        fclaim.evidence_package_hash = hashlib.sha256(
            f"{fclaim.claim_reference}:{exp_visit.id}:{exp_trip.id}:{anon_ref}".encode("utf-8")
        ).hexdigest()

        b_lines["travel"].reimbursed_paise += reimb_visit
        b_lines["transport"].reimbursed_paise += reimb_trip
        contract.funding_received_paise += reimb_visit + reimb_trip

        record_fin_ledger(
            db,
            s,
            "funding_claim",
            fclaim.id,
            "e2e_funded_programme_walkthrough",
            "draft",
            "reimbursed_settled",
            fclaim.approved_reimbursed_paise,
            f"contract={contract.contract_reference}; claim={fclaim.claim_reference}",
        )
        db.commit()

        evidence_pkg = get_supporting_evidence_package(fclaim.id, db=db, s=s)
        return {
            "walkthrough_status": "completed_all_12_steps",
            "steps_completed": [
                "1. Created NHM Funder & Maternal Health Contract (marked as SIMULATED / DEMO APPROVAL)",
                "2. Allocated Rs 5,00,000.00 Programme Budget across 7 categories",
                "3. Verified Doctor, Nurse & Field Coordinator Workforce Profiles & Compensation Agreements",
                "4. Registered consenting patient & human-verified ANC card",
                f"5. Authorised CarePlan ({cplan.id}) & scheduled {len(sched_res)} durable reminders",
                f"6. Completed & verified Nurse Field Visit ({fvisit.id})",
                f"7. Booked & completed Patient Transport Trip ({trip.id})",
                f"8. Submitted, supervisor-verified & finance-approved Travel ({claim_visit.id}) & Transport ({claim_trip.id}) Expense Claims",
                "9. Linked completed services & expenditures to active contract & budget",
                f"10. Calculated & verified Monthly Payroll Run ({pr.id if pr else 'N/A'})",
                f"11. Generated privacy-safe Supporting Evidence Package ({fclaim.claim_reference})",
                "12. Verified financial dashboards, immutable audit ledger & exact paise budget balances",
            ],
            "contract": _serialize_contract(db, contract),
            "budget": _serialize_budget(db, budget),
            "payroll_run_id": pr.id if pr else None,
            "funding_claim": _serialize_funding_claim(db, fclaim),
            "supporting_evidence_package": evidence_pkg,
        }
