"""JananiSetu — Maternal Healthcare Service & Care-Coordination Platform (Phase 3).

IMPORTANT HEALTHCARE BOUNDARY:
 Assistive administrative care-coordination only. This application NEVER performs autonomous
 diagnosis, prescriptions, clinical risk scoring, or AI-generated treatment decisions.
 All clinical care plans and appointment schedules must be authored by licensed doctors.
 Raw OCR output is never automatically published into patient records or care plans.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Literal, Optional

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.anc_fixtures import (
    FIXTURE_SPECS,
    ensure_fixtures_on_disk,
    evaluate_fixtures_benchmark,
    generate_fixture_image_bytes,
    generate_fixture_pdf_bytes,
)
from app.celery_app import check_worker_and_queue_health
from app.config import ROOT_DIR, get_settings
from app.database import ensure_schema_and_migrate_legacy, seed_default_accounts_if_empty
from app.followup_engine import (
    ALLOWED_FOLLOWUP_TRANSITIONS,
    ALL_FOLLOWUP_STATES,
    cancel_obsolete_reminders,
    evaluate_overdue_acknowledgements,
    get_or_create_clinic_comm_config,
    operator_retry_dead_letter_job,
    parse_offsets_hours,
    process_delivery_callback,
    process_inbound_reply,
    process_outbox_and_due_jobs,
    schedule_reminders_for_care_plan,
    transition_care_plan_state,
)
from app.messaging import (
    APPROVED_TEMPLATES,
    DELIVERY_STATUS_RANKS,
    get_messaging_adapter,
    get_messaging_providers_status,
    mask_phone,
    render_approved_template,
    validate_privacy_safe_content,
    verify_webhook_signature,
)
from app.models import (
    AdminChangeProposal,
    Base,
    CaregiverConsent,
    CarePlan,
    ClinicCommConfig,
    ContactAttempt,
    Document,
    DocumentVersion,
    Event,
    Expense,
    ExtractedField,
    FieldSourceLocation,
    Message,
    Mother,
    OcrJob,
    ReminderJob,
    RevokedToken,
    Staff,
    Task,
    TransactionalOutbox,
    Transport,
    VerificationDecision,
    WebhookEvent,
    now,
    uid,
)
from app.ocr_engine import (
    DATE_FIELD_KEYS,
    DocumentValidationError,
    run_anc_ocr_pipeline,
    validate_and_inspect_upload,
)
from app.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    normalize_role,
    validate_password_strength,
    verify_password,
)

logger = logging.getLogger("jananisetu")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

ROOT = ROOT_DIR
settings = get_settings()
DATA = Path(os.getenv("JANANI_DATA_DIR", str(settings.data_dir)))
DATA.mkdir(parents=True, exist_ok=True)
DB = os.getenv("JANANI_DB_URL", os.getenv("DATABASE_URL", f"sqlite:///{DATA / 'janani.db'}"))
if DB.startswith("postgres://"):
    DB = DB.replace("postgres://", "postgresql+psycopg://", 1)
elif DB.startswith("postgresql://"):
    DB = DB.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(
    DB,
    connect_args={"check_same_thread": False} if DB.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

# Security requirement: Never silently modify production schemas on startup.
# In non-production (dev/test), ensure tables exist for local convenience.
if not settings.is_production:
    ensure_schema_and_migrate_legacy(engine)
    ensure_fixtures_on_disk(DATA / "fixtures")

app = FastAPI(
    title="JananiSetu – Care Operations Platform",
    version="0.3.0",
    description=(
        "Maternal care coordination and human-verified ANC card digitisation platform. "
        "Synthetic data only. No autonomous diagnosis, risk scoring, or clinical advice."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = ROOT / "app" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
FRONTEND_DIST = STATIC_DIR / "dist"
if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------------------------------------------------------------------------
# Structured Exception Handling
# ---------------------------------------------------------------------------
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error": {
                "code": exc.status_code,
                "message": str(exc.detail),
                "path": request.url.path,
            },
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    summary = "; ".join(
        f"{'.'.join(str(loc) for loc in e.get('loc', []) if loc != 'body')}: {e.get('msg', 'invalid')}"
        for e in errors
    )
    return JSONResponse(
        status_code=422,
        content={
            "detail": summary or "Validation error",
            "errors": [
                {
                    "loc": [str(x) for x in e.get("loc", [])],
                    "msg": e.get("msg", ""),
                    "type": e.get("type", ""),
                }
                for e in errors
            ],
        },
    )


# ---------------------------------------------------------------------------
# Database & Hardened Security Dependencies
# ---------------------------------------------------------------------------
def dbsession():
    with SessionLocal() as db:
        yield db


def _extract_token_string(
    authorization: Optional[str],
    cookie_token: Optional[str],
) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if cookie_token:
        return cookie_token.strip()
    return None


def _extract_staff_from_request(
    db: Session,
    authorization: Optional[str],
    x_staff_id: Optional[str],
    cookie_token: Optional[str],
) -> Optional[Staff]:
    cur_settings = get_settings()
    token = _extract_token_string(authorization, cookie_token)

    if token:
        payload = decode_access_token(token)
        staff_id = payload.get("sub")
        if not staff_id:
            raise HTTPException(401, "Token missing subject identity")

        # Check token revocation list (JTI)
        jti = payload.get("jti")
        if jti and db.get(RevokedToken, str(jti)) is not None:
            raise HTTPException(401, "Token has been revoked. Please sign in again.")

        staff = db.get(Staff, staff_id)
        if not staff or not staff.is_active:
            raise HTTPException(401, "Staff account not found or deactivated")

        # Check token_version for password-change / global session revocation
        token_tv = payload.get("tv")
        if token_tv is not None and int(token_tv) != int(staff.token_version or 1):
            raise HTTPException(401, "Session invalidated due to credential update")

        return staff

    if x_staff_id:
        # Phase 3 Security Hardening: Never allow X-Staff-ID in production or when disabled
        if cur_settings.is_production or not cur_settings.allow_legacy_header:
            raise HTTPException(
                401,
                "Legacy X-Staff-ID header authentication is disabled. Use Bearer JWT token.",
            )
        staff = db.get(Staff, x_staff_id)
        if not staff or not staff.is_active:
            raise HTTPException(401, "Unknown or inactive staff ID")
        return staff

    return None


def who(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_staff_id: Optional[str] = Header(default=None),
    x_requested_with: Optional[str] = Header(default=None),
    x_csrf_token: Optional[str] = Header(default=None),
    janani_access_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(dbsession),
) -> Staff:
    staff = _extract_staff_from_request(db, authorization, x_staff_id, janani_access_token)
    if not staff:
        raise HTTPException(
            401, "Authentication required. Provide Bearer token or valid session credentials."
        )
    # Anti-CSRF protection: If request is authenticated solely via cookie (no Bearer header)
    # on state-changing methods (POST, PUT, PATCH, DELETE), reject cross-site submissions.
    if not (authorization and authorization.lower().startswith("bearer ")) and janani_access_token:
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            sec_fetch_site = (request.headers.get("sec-fetch-site") or "").lower()
            if sec_fetch_site == "cross-site":
                raise HTTPException(
                    403, "CSRF verification failed: Cross-site cookie authentication is disallowed"
                )
            origin = (request.headers.get("origin") or "").strip()
            referer = (request.headers.get("referer") or "").strip()
            trusted_origins = set(get_settings().cors_origins)

            origin_trusted = (
                any(origin.startswith(to.rstrip("/")) for to in trusted_origins if to)
                if origin
                else False
            )
            referer_trusted = (
                any(referer.startswith(to.rstrip("/")) for to in trusted_origins if to)
                if referer
                else False
            )

            # Strict guard 1: If Origin is provided, it MUST be in trusted_origins
            if origin and not origin_trusted:
                raise HTTPException(403, "CSRF verification failed: Untrusted Origin header")

            # Strict guard 2: If Referer is provided, it MUST be in trusted_origins
            if referer and not referer_trusted:
                raise HTTPException(403, "CSRF verification failed: Untrusted Referer header")

            # Strict guard 3: Must have an explicit anti-CSRF custom header OR a trusted same-origin Origin/Referer
            has_custom_header = bool(
                (x_requested_with and x_requested_with.lower() in ("xmlhttprequest", "fetch"))
                or (x_csrf_token and len(x_csrf_token) >= 8)
            )
            if not (has_custom_header or origin_trusted or referer_trusted):
                raise HTTPException(
                    403,
                    "CSRF verification failed: State-changing cookie requests require valid Origin/Referer or custom anti-CSRF header",
                )
    return staff


def optional_who(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_staff_id: Optional[str] = Header(default=None),
    x_requested_with: Optional[str] = Header(default=None),
    x_csrf_token: Optional[str] = Header(default=None),
    janani_access_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(dbsession),
) -> Optional[Staff]:
    try:
        return _extract_staff_from_request(db, authorization, x_staff_id, janani_access_token)
    except HTTPException:
        if authorization or x_staff_id:
            raise
        return None


def permitted(staff: Staff, *roles: str) -> None:
    expanded_roles = set(roles)
    if "field_coordinator" in expanded_roles or "asha" in expanded_roles:
        expanded_roles.update({"field_coordinator", "asha"})
    if staff.role not in expanded_roles and normalize_role(staff.role) not in expanded_roles:
        raise HTTPException(
            403,
            f"Insufficient role '{staff.role}'. Permitted roles: {', '.join(sorted(expanded_roles))}",
        )


def audit(
    db: Session,
    s: Staff,
    action: str,
    entity: str,
    obj_id: str,
    detail: str = "",
) -> None:
    db.add(
        Event(
            clinic=s.clinic,
            actor=s.id,
            actor_role=normalize_role(s.role),
            action=action,
            entity=entity,
            entity_id=obj_id,
            detail=detail,
        )
    )


def row(obj: Any, exclude: set[str] | None = None) -> dict[str, Any]:
    excluded = exclude or {"password_hash", "stored_path", "preview_path"}
    result: dict[str, Any] = {}
    for c in obj.__table__.columns:
        if c.name in excluded:
            continue
        v = getattr(obj, c.name)
        result[c.name] = v.isoformat() if isinstance(v, (date, datetime)) else v
    if isinstance(obj, Staff):
        result["normalized_role"] = normalize_role(obj.role)
    if isinstance(obj, Expense):
        result["amount_rupees"] = round((obj.amount_paise or 0) / 100, 2)
    return result


def mother_for(db: Session, staff: Staff, mid: str) -> Mother:
    m = db.get(Mother, mid)
    if not m or m.clinic != staff.clinic:
        raise HTTPException(404, "Mother not found in your clinic")
    return m


def document_for(db: Session, staff: Staff, did: str) -> tuple[Document, Mother]:
    d = db.get(Document, did)
    if not d or d.clinic != staff.clinic:
        raise HTTPException(404, "Document not found in your clinic")
    m = mother_for(db, staff, d.mother_id)
    return d, m


def _private_storage_dir(clinic: str) -> Path:
    base_dir = Path(os.getenv("JANANI_DATA_DIR", str(DATA))) / "private_storage" / clinic
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


# ---------------------------------------------------------------------------
# Pydantic Request Schemas
# ---------------------------------------------------------------------------
RoleType = Literal["admin", "doctor", "nurse", "field_coordinator", "asha"]


class LoginIn(BaseModel):
    identifier: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=1, max_length=128)
    clinic: Optional[str] = Field(default=None, max_length=80)


class RegisterClinicIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=160)
    password: str = Field(min_length=8, max_length=128)
    role: RoleType = "admin"
    clinic: str = Field(default="demo-clinic", min_length=2, max_length=80)
    phone: str = Field(default="", max_length=24)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class StaffIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    role: RoleType
    email: Optional[str] = Field(default=None, max_length=160)
    password: Optional[str] = Field(default=None, max_length=128)
    phone: str = Field(default="", max_length=24)
    clinic: Optional[str] = Field(default=None, max_length=80)


class StaffUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    role: Optional[RoleType] = None
    phone: Optional[str] = Field(default=None, max_length=24)
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)


class MotherIn(BaseModel):
    name: str = Field(min_length=2, max_length=140)
    phone: str = Field(min_length=8, max_length=20)
    patient_identifier: str = Field(default="", max_length=80)
    language: Literal["en", "te", "hi"] = "te"
    consent: bool = False
    age: Optional[int] = Field(default=None, ge=14, le=60)
    edd: Optional[date] = None
    lmp: Optional[date] = None
    address: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=2000)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = re.sub(r"[\s\-\(\)]", "", v.strip())
        if not re.match(r"^\+?[0-9]{8,15}$", cleaned):
            raise ValueError("Phone must contain 8 to 15 digits")
        return cleaned


class MotherUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=140)
    phone: Optional[str] = Field(default=None, min_length=8, max_length=20)
    patient_identifier: Optional[str] = Field(default=None, max_length=80)
    language: Optional[Literal["en", "te", "hi"]] = None
    consent: Optional[bool] = None
    age: Optional[int] = Field(default=None, ge=14, le=60)
    edd: Optional[date] = None
    lmp: Optional[date] = None
    address: Optional[str] = Field(default=None, max_length=300)
    notes: Optional[str] = Field(default=None, max_length=2000)


class ConsentIn(BaseModel):
    consent: bool


class PlanIn(BaseModel):
    visit_date: date
    visit_type: Literal[
        "anc_checkup", "follow_up", "ultrasound_review", "lab_review", "postnatal", "other"
    ] = "anc_checkup"
    note: str = Field(default="", max_length=1500)


class AppointmentStatusIn(BaseModel):
    appointment_status: Literal["scheduled", "completed", "missed", "rescheduled", "cancelled"]
    follow_up_notes: str = Field(default="", max_length=1500)
    create_followup_task: bool = False


class ReminderIn(BaseModel):
    mother_id: str


class ReplyIn(BaseModel):
    mother_id: str
    body: str = Field(min_length=1, max_length=2000)


class TaskIn(BaseModel):
    mother_id: str
    care_plan_id: Optional[str] = None
    category: Literal[
        "missed_visit",
        "contact_attempt",
        "patient_reply",
        "unacknowledged_reminder_followup",
        "flagged_message_review",
        "transport",
        "home_visit",
        "document_followup",
        "other",
    ] = "contact_attempt"
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    due_date: Optional[date] = None
    detail: str = Field(default="", max_length=1500)
    assigned_to: str = ""


class StatusIn(BaseModel):
    status: Literal["open", "in_progress", "resolved", "cancelled"]
    assigned_to: Optional[str] = None
    priority: Optional[Literal["low", "medium", "high", "urgent"]] = None
    due_date: Optional[date] = None
    completion_notes: Optional[str] = Field(default=None, max_length=1500)


class TransportIn(BaseModel):
    mother_id: str
    date: date
    pickup_time: str = Field(default="09:00", max_length=20)
    from_location: str = Field(min_length=2, max_length=200)
    destination: str = Field(min_length=2, max_length=200)
    partner: str = Field(default="not assigned", max_length=160)
    vehicle_notes: str = Field(default="", max_length=500)


class TransportStatus(BaseModel):
    status: Literal["requested", "assigned", "in_transit", "completed", "cancelled"]
    partner: Optional[str] = Field(default=None, max_length=160)
    pickup_time: Optional[str] = Field(default=None, max_length=20)
    vehicle_notes: Optional[str] = Field(default=None, max_length=500)


class ExpenseIn(BaseModel):
    category: Literal["salary", "travel", "transport", "diagnostics", "technology", "other"]
    amount_rupees: int = Field(gt=0, le=10_000_000)
    description: str = Field(default="", max_length=500)
    receipt_ref: str = Field(default="", max_length=120)


class ApprovalIn(BaseModel):
    approved: bool


class FieldDecisionIn(BaseModel):
    decision: Literal["accepted", "corrected", "rejected", "illegible_manual"]
    final_value: Optional[str] = Field(default=None, max_length=1000)
    reviewer_note: str = Field(default="", max_length=1000)


class BulkFieldDecisionItem(BaseModel):
    field_key: str
    decision: Literal["accepted", "corrected", "rejected", "illegible_manual"]
    final_value: Optional[str] = Field(default=None, max_length=1000)
    reviewer_note: str = Field(default="", max_length=1000)


class ConfirmIn(BaseModel):
    corrected_text: str = Field(default="", max_length=10000)
    structured_fields: Optional[dict[str, Any]] = None
    field_decisions: Optional[list[BulkFieldDecisionItem]] = None


class ChangeProposalDecisionIn(BaseModel):
    decision: Literal["approved", "rejected"]
    review_note: str = Field(default="", max_length=1000)


class FollowupTransitionIn(BaseModel):
    target_state: str = Field(min_length=2, max_length=50)
    reason: str = Field(default="", max_length=500)


class WorkerRunIn(BaseModel):
    force_due: bool = True
    simulate_failure: bool = False
    evaluate_overdue: bool = False


class OperatorRetryIn(BaseModel):
    channel_override: Optional[str] = Field(default=None, max_length=40)


class SimulateCallbackIn(BaseModel):
    event_id: str = Field(min_length=2, max_length=120)
    delivery_status: Literal["queued", "sent", "delivered", "read", "acknowledged", "failed"]
    failure_code: str = Field(default="", max_length=60)
    failure_reason: str = Field(default="", max_length=300)


class ClinicianMessageReviewIn(BaseModel):
    clinical_review_note: str = Field(min_length=2, max_length=1500)
    resolve_related_task: bool = True


class ContactAttemptIn(BaseModel):
    channel: Literal["phone_call", "home_visit", "whatsapp_followup", "asha_liaison"] = "phone_call"
    outcome: Literal[
        "reached_confirmed",
        "no_answer",
        "busy",
        "wrong_number",
        "reschedule_requested",
        "escalated_to_supervisor",
        "unreachable",
    ]
    notes: str = Field(default="", max_length=1500)


class TaskEscalateIn(BaseModel):
    escalated_to: Optional[str] = Field(default=None, max_length=36)
    escalation_reason: str = Field(min_length=3, max_length=1000)


class CaregiverIn(BaseModel):
    caregiver_name: str = Field(min_length=2, max_length=140)
    caregiver_phone: str = Field(min_length=8, max_length=20)
    relationship_type: Literal["spouse", "mother", "mother_in_law", "sister", "other"] = "spouse"
    language: Literal["en", "te", "hi"] = "te"
    consent_granted: bool = True
    allow_admin_reminders: bool = True

    @field_validator("caregiver_phone")
    @classmethod
    def validate_cg_phone(cls, v: str) -> str:
        cleaned = re.sub(r"[\s\-\(\)]", "", v.strip())
        if not re.match(r"^\+?[0-9]{8,15}$", cleaned):
            raise ValueError("Caregiver phone must contain 8 to 15 digits")
        return cleaned


class CaregiverUpdateIn(BaseModel):
    caregiver_name: Optional[str] = Field(default=None, min_length=2, max_length=140)
    caregiver_phone: Optional[str] = Field(default=None, min_length=8, max_length=20)
    relationship_type: Optional[str] = Field(default=None, max_length=60)
    language: Optional[Literal["en", "te", "hi"]] = None
    consent_granted: Optional[bool] = None
    allow_admin_reminders: Optional[bool] = None


class CaregiverMessageIn(BaseModel):
    custom_body: Optional[str] = Field(default=None, max_length=1000)


class ClinicCommConfigIn(BaseModel):
    timezone: str = Field(default="Asia/Kolkata", max_length=40)
    reminder_offsets_hours: list[int] = Field(default_factory=lambda: [-48, -24, 0])
    ack_deadline_hours: int = Field(default=12, ge=1, le=168)
    default_channel: Literal["local-simulator", "whatsapp-cloud", "sms-gateway"] = "local-simulator"
    whatsapp_template_en: str = Field(default="janani_anc_reminder_en", max_length=80)
    whatsapp_template_te: str = Field(default="janani_anc_reminder_te", max_length=80)
    whatsapp_template_hi: str = Field(default="janani_anc_reminder_hi", max_length=80)
    max_retry_attempts: int = Field(default=3, ge=1, le=10)
    retry_base_seconds: int = Field(default=60, ge=5, le=3600)
    enable_caregiver_reminders: bool = True


# ---------------------------------------------------------------------------
# Health & System Status
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict[str, Any]:
    cur_settings = get_settings()
    dialect = engine.dialect.name
    return {
        "status": "ok",
        "version": "0.3.0",
        "environment": cur_settings.env,
        "database_dialect": dialect,
        "legacy_header_auth_enabled": cur_settings.allow_legacy_header,
        "demo_mode_enabled": cur_settings.enable_demo_mode,
        "ocr_engine": "tesseract-5",
        "external_ocr_enabled": cur_settings.external_ocr_enabled,
        "messaging": "simulated",
        "clinical_advice": False,
        "autonomous_diagnosis": False,
        "risk_scoring": False,
    }


# ---------------------------------------------------------------------------
# Authentication & Session Endpoints
# ---------------------------------------------------------------------------
_FAILED_LOGIN_ATTEMPTS: dict[str, list[float]] = {}


def _check_login_rate_limit(
    key: str, db: Optional[Session] = None, max_attempts: int = 10, window_sec: float = 60.0
) -> None:
    now_dt = datetime.now(timezone.utc)
    now_ts = now_dt.timestamp()
    attempts = [ts for ts in _FAILED_LOGIN_ATTEMPTS.get(key, []) if now_ts - ts < window_sec]
    _FAILED_LOGIN_ATTEMPTS[key] = attempts
    mem_count = len(attempts)

    db_count = 0
    if db is not None:
        try:
            cutoff = now_dt - timedelta(seconds=window_sec)
            db_count = (
                db.scalar(
                    select(func.count(Event.id)).where(
                        Event.action == "failed_login",
                        Event.entity_id == key[:60],
                        Event.occurred >= cutoff,
                    )
                )
                or 0
            )
        except Exception as exc:
            logging.warning("Database login rate check error: %s", exc)

    if max(mem_count, db_count) >= max_attempts:
        raise HTTPException(
            429,
            "Too many failed login attempts. Please wait 60 seconds before trying again.",
        )


def _record_failed_login(key: str, db: Optional[Session] = None) -> None:
    now_dt = datetime.now(timezone.utc)
    now_ts = now_dt.timestamp()
    _FAILED_LOGIN_ATTEMPTS.setdefault(key, []).append(now_ts)
    if db is not None:
        try:
            ev = Event(
                clinic="system",
                actor="unauthenticated",
                actor_role="guest",
                action="failed_login",
                entity="auth_rate_limit",
                entity_id=key[:60],
                occurred=now_dt,
                detail=f"rate_key={key[:120]}",
            )
            db.add(ev)
            db.commit()
        except Exception as exc:
            db.rollback()
            logging.warning("Database login rate record error: %s", exc)


def _clear_failed_login(key: str, db: Optional[Session] = None) -> None:
    _FAILED_LOGIN_ATTEMPTS.pop(key, None)
    if db is not None:
        try:
            db.execute(
                delete(Event).where(
                    Event.action == "failed_login",
                    Event.entity_id == key[:60],
                )
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            logging.warning("Database login rate clear error: %s", exc)


@app.post("/api/auth/login")
def login(
    p: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(dbsession),
) -> dict[str, Any]:
    cur_settings = get_settings()
    ident = p.identifier.strip()
    client_ip = request.client.host if request.client else "127.0.0.1"
    rate_key = f"{client_ip}:{ident.lower()}"
    _check_login_rate_limit(rate_key, db=db)

    stmt = select(Staff).where(
        (func.lower(Staff.email) == ident.lower())
        | (Staff.id == ident)
        | (func.lower(Staff.name) == ident.lower())
    )
    if p.clinic:
        stmt = stmt.where(Staff.clinic == p.clinic)
    candidates = list(db.scalars(stmt))
    if not candidates:
        _record_failed_login(rate_key, db=db)
        raise HTTPException(401, "Invalid credentials")

    matched_staff: Optional[Staff] = None
    for candidate in candidates:
        if verify_password(p.password, candidate.password_hash):
            matched_staff = candidate
            break

    if not matched_staff:
        _record_failed_login(rate_key, db=db)
        raise HTTPException(401, "Invalid credentials")
    if not matched_staff.is_active:
        raise HTTPException(403, "Staff account is deactivated")

    _clear_failed_login(rate_key, db=db)

    token = create_access_token(
        subject=matched_staff.id,
        role=matched_staff.role,
        clinic=matched_staff.clinic,
        name=matched_staff.name,
        token_version=matched_staff.token_version or 1,
    )
    audit(db, matched_staff, "login", "staff", matched_staff.id, f"clinic={matched_staff.clinic}")
    db.commit()

    response.set_cookie(
        key="janani_access_token",
        value=token,
        httponly=True,
        secure=cur_settings.is_production,
        samesite="lax",
        max_age=cur_settings.access_token_expire_minutes * 60,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "staff": row(matched_staff),
    }


@app.post("/api/auth/register")
def register_account(
    p: RegisterClinicIn,
    response: Response,
    x_bootstrap_token: Optional[str] = Header(default=None),
    db: Session = Depends(dbsession),
    caller: Optional[Staff] = Depends(optional_who),
) -> dict[str, Any]:
    cur_settings = get_settings()
    validate_password_strength(p.password)

    target_clinic = p.clinic.strip() or "demo-clinic"
    existing_admin = db.scalar(
        select(Staff).where(Staff.clinic == target_clinic, Staff.role == "admin")
    )

    if existing_admin is not None:
        if not caller:
            raise HTTPException(
                401,
                "Clinic already has an administrator. Authenticate as clinic admin to register staff.",
            )
        permitted(caller, "admin")
        if caller.clinic != target_clinic:
            raise HTTPException(403, "Cannot register staff for a different clinic")
    elif cur_settings.is_production and not caller:
        # In production, unauthenticated bootstrap requires configured bootstrap token if set
        if cur_settings.bootstrap_token and x_bootstrap_token != cur_settings.bootstrap_token:
            raise HTTPException(403, "Valid bootstrap token required for production clinic registration")
        if p.role != "admin":
            raise HTTPException(403, "Initial clinic bootstrap account must be an administrator")

    email_norm = p.email.strip().lower()
    dup = db.scalar(select(Staff).where(func.lower(Staff.email) == email_norm))
    if dup:
        raise HTTPException(409, "A staff member with this email already exists")

    new_staff = Staff(
        name=p.name.strip(),
        email=email_norm,
        role=p.role,
        clinic=target_clinic,
        phone=p.phone.strip(),
        password_hash=hash_password(p.password),
        is_active=True,
        token_version=1,
    )
    db.add(new_staff)
    db.flush()
    actor = caller or new_staff
    audit(
        db,
        actor,
        "register_staff",
        "staff",
        new_staff.id,
        f"role={new_staff.role}; clinic={target_clinic}",
    )
    db.commit()

    token = create_access_token(
        subject=new_staff.id,
        role=new_staff.role,
        clinic=new_staff.clinic,
        name=new_staff.name,
        token_version=new_staff.token_version,
    )
    if not caller:
        response.set_cookie(
            key="janani_access_token",
            value=token,
            httponly=True,
            secure=cur_settings.is_production,
            samesite="lax",
            max_age=cur_settings.access_token_expire_minutes * 60,
        )
    return {
        "access_token": token,
        "token_type": "bearer",
        "staff": row(new_staff),
    }


@app.get("/api/auth/me")
def auth_me(s: Staff = Depends(who)) -> dict[str, Any]:
    return row(s)


@app.post("/api/auth/logout")
def logout(
    response: Response,
    authorization: Optional[str] = Header(default=None),
    janani_access_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, str]:
    token_str = _extract_token_string(authorization, janani_access_token)
    if token_str:
        try:
            payload = decode_access_token(token_str)
            jti = payload.get("jti")
            if jti and db.get(RevokedToken, str(jti)) is None:
                db.add(
                    RevokedToken(
                        jti=str(jti),
                        staff_id=s.id,
                        clinic=s.clinic,
                        reason="logout",
                    )
                )
        except Exception:
            pass
    audit(db, s, "logout", "staff", s.id)
    db.commit()
    response.delete_cookie("janani_access_token")
    return {"status": "logged_out"}


@app.post("/api/auth/change-password")
def change_password(
    p: PasswordChangeIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, str]:
    if not verify_password(p.current_password, s.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    validate_password_strength(p.new_password)
    s.password_hash = hash_password(p.new_password)
    s.token_version = (s.token_version or 1) + 1
    audit(db, s, "password_change", "staff", s.id)
    db.commit()
    return {"status": "password_updated"}


@app.post("/api/auth/seed-demo")
def seed_demo_endpoint(db: Session = Depends(dbsession)) -> dict[str, Any]:
    cur_settings = get_settings()
    if cur_settings.is_production or not cur_settings.enable_demo_mode:
        raise HTTPException(
            403, "Demonstration account seeding is disabled in production"
        )
    seed_default_accounts_if_empty(db)
    staff_rows = [row(x) for x in db.scalars(select(Staff).order_by(Staff.clinic, Staff.role))]
    return {
        "seeded": True,
        "demo_password": "Janani@2026",
        "staff": staff_rows,
    }


@app.get("/api/auth/demo-accounts")
def get_demo_accounts(
    seed: bool = Query(default=False),
    db: Session = Depends(dbsession),
) -> dict[str, Any]:
    cur_settings = get_settings()
    if cur_settings.is_production or not cur_settings.enable_demo_mode:
        raise HTTPException(
            403, "Demonstration account disclosure is disabled in production"
        )
    if seed:
        seed_default_accounts_if_empty(db)
    staff_rows = [
        row(x)
        for x in db.scalars(
            select(Staff)
            .where(Staff.is_active == True)
            .order_by(Staff.clinic, Staff.role)
        )
    ]
    return {
        "demo_password_hint": "Janani@2026",
        "accounts": staff_rows,
    }


# ---------------------------------------------------------------------------
# Staff Registration & Management (Authenticated & Clinic-Scoped)
# ---------------------------------------------------------------------------
@app.get("/api/staff")
def staff_list(
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> list[dict[str, Any]]:
    return [
        row(x)
        for x in db.scalars(
            select(Staff).where(Staff.clinic == s.clinic).order_by(Staff.name)
        )
    ]


@app.post("/api/staff")
def create_staff(
    p: StaffIn,
    db: Session = Depends(dbsession),
    caller: Optional[Staff] = Depends(optional_who),
) -> dict[str, Any]:
    cur_settings = get_settings()
    if caller:
        permitted(caller, "admin")
        target_clinic = caller.clinic
    else:
        if cur_settings.is_production:
            raise HTTPException(401, "Authentication required to create staff in production")
        target_clinic = (p.clinic or "demo-clinic").strip()
        existing_admin = db.scalar(
            select(Staff).where(Staff.clinic == target_clinic, Staff.role == "admin")
        )
        if existing_admin is not None:
            raise HTTPException(
                401,
                "Clinic already initialized with an administrator. Authenticate as admin to add staff.",
            )

    email_val = p.email.strip().lower() if p.email else None
    if email_val:
        dup = db.scalar(select(Staff).where(func.lower(Staff.email) == email_val))
        if dup:
            raise HTTPException(409, "Email already registered")

    if p.password is not None:
        validate_password_strength(p.password)
        raw_password = p.password
    elif cur_settings.is_production:
        raise HTTPException(422, "Password is required when creating staff in production")
    else:
        raw_password = "Janani@2026"

    s = Staff(
        name=p.name.strip(),
        role=p.role,
        email=email_val,
        clinic=target_clinic,
        phone=p.phone.strip(),
        password_hash=hash_password(raw_password),
        is_active=True,
        token_version=1,
    )
    db.add(s)
    db.flush()
    audit(
        db,
        caller or s,
        "create_staff",
        "staff",
        s.id,
        f"role={s.role}; clinic={s.clinic}",
    )
    db.commit()
    return row(s)


@app.patch("/api/staff/{sid}")
def update_staff(
    sid: str,
    p: StaffUpdateIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin")
    target = db.get(Staff, sid)
    if not target or target.clinic != s.clinic:
        raise HTTPException(404, "Staff member not found in your clinic")

    if p.name is not None:
        target.name = p.name.strip()
    if p.role is not None:
        target.role = p.role
    if p.phone is not None:
        target.phone = p.phone.strip()
    if p.is_active is not None:
        if target.is_active and not p.is_active:
            target.token_version = (target.token_version or 1) + 1
        target.is_active = p.is_active
    if p.password is not None:
        validate_password_strength(p.password)
        target.password_hash = hash_password(p.password)
        target.token_version = (target.token_version or 1) + 1

    audit(
        db,
        s,
        "update_staff",
        "staff",
        target.id,
        f"role={target.role}; active={target.is_active}",
    )
    db.commit()
    return row(target)


# ---------------------------------------------------------------------------
# Patient Registration & Consent (Mothers)
# ---------------------------------------------------------------------------
@app.get("/api/mothers")
def mothers(
    q: Optional[str] = Query(default=None, description="Search by name or phone"),
    consent: Optional[bool] = Query(default=None),
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> list[dict[str, Any]]:
    stmt = select(Mother).where(Mother.clinic == s.clinic)
    if consent is not None:
        stmt = stmt.where(Mother.consent == consent)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where((Mother.name.ilike(pattern)) | (Mother.phone.ilike(pattern)))
    stmt = stmt.order_by(Mother.created_at.desc())

    mothers_list = list(db.scalars(stmt))
    active_plans = {
        cp.mother_id: cp
        for cp in db.scalars(
            select(CarePlan).where(CarePlan.clinic == s.clinic, CarePlan.active == True)
        )
    }
    output: list[dict[str, Any]] = []
    for m in mothers_list:
        d = row(m)
        cp = active_plans.get(m.id)
        d["next_visit_date"] = cp.visit_date.isoformat() if cp else None
        d["appointment_status"] = cp.appointment_status if cp else None
        output.append(d)
    return output


@app.get("/api/mothers/{mid}")
def get_mother_detail(
    mid: str,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    m = mother_for(db, s, mid)
    d = row(m)
    d["plans"] = [
        row(p)
        for p in db.scalars(
            select(CarePlan).where(CarePlan.mother_id == mid).order_by(CarePlan.version.desc())
        )
    ]
    d["tasks"] = [
        row(t)
        for t in db.scalars(
            select(Task).where(Task.mother_id == mid).order_by(Task.created_at.desc())
        )
    ]
    d["documents"] = [
        row(doc)
        for doc in db.scalars(
            select(Document)
            .where(Document.mother_id == mid)
            .order_by(Document.version_number.desc(), Document.created_at.desc())
        )
    ]
    d["change_proposals"] = [
        row(cp)
        for cp in db.scalars(
            select(AdminChangeProposal)
            .where(AdminChangeProposal.mother_id == mid)
            .order_by(AdminChangeProposal.created_at.desc())
        )
    ]
    d["transport"] = [
        row(tr)
        for tr in db.scalars(
            select(Transport).where(Transport.mother_id == mid).order_by(Transport.date.desc())
        )
    ]
    d["caregivers"] = [
        row(cg)
        for cg in db.scalars(
            select(CaregiverConsent)
            .where(CaregiverConsent.mother_id == mid, CaregiverConsent.clinic == s.clinic)
            .order_by(CaregiverConsent.updated_at.desc())
        )
    ]
    d["reminder_jobs"] = [
        row(rj)
        for rj in db.scalars(
            select(ReminderJob)
            .where(ReminderJob.mother_id == mid, ReminderJob.clinic == s.clinic)
            .order_by(ReminderJob.scheduled_for.asc())
        )
    ]
    return d


@app.post("/api/mothers")
def create_mother(
    p: MotherIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "nurse", "doctor", "field_coordinator")
    data = p.model_dump()
    m = Mother(
        **data,
        clinic=s.clinic,
        registered_by=s.id,
        consent_updated_at=now() if p.consent else None,
    )
    db.add(m)
    db.flush()
    audit(db, s, "create", "mother", m.id, f"consent={m.consent}; clinic={s.clinic}")
    db.commit()
    return row(m)


@app.patch("/api/mothers/{mid}")
def update_mother(
    mid: str,
    p: MotherUpdateIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "nurse", "doctor", "field_coordinator")
    m = mother_for(db, s, mid)
    updates = p.model_dump(exclude_unset=True)
    consent_changed = "consent" in updates and updates["consent"] != m.consent
    if consent_changed:
        m.consent_updated_at = now()
        audit(db, s, "consent_change", "mother", mid, str(updates["consent"]))
    for k, v in updates.items():
        setattr(m, k, v)
    if consent_changed:
        if not m.consent:
            cancel_obsolete_reminders(
                db,
                clinic=m.clinic,
                mother_id=m.id,
                reason="mother_consent_withdrawn",
                actor_id=s.id,
                actor_role=normalize_role(s.role),
            )
        else:
            active_plan = db.scalar(
                select(CarePlan).where(CarePlan.mother_id == m.id, CarePlan.active.is_(True))
            )
            if active_plan:
                schedule_reminders_for_care_plan(
                    db, active_plan, m, actor_id=s.id, actor_role=normalize_role(s.role)
                )
    audit(db, s, "update", "mother", mid, ",".join(updates.keys()))
    db.commit()
    return row(m)


@app.patch("/api/mothers/{mid}/consent")
def change_consent(
    mid: str,
    p: ConsentIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "nurse", "doctor", "field_coordinator")
    m = mother_for(db, s, mid)
    m.consent = p.consent
    m.consent_updated_at = now()
    cancelled_jobs = 0
    if not p.consent:
        cancelled_jobs = cancel_obsolete_reminders(
            db,
            clinic=m.clinic,
            mother_id=m.id,
            reason="mother_consent_withdrawn",
            actor_id=s.id,
            actor_role=normalize_role(s.role),
        )
    else:
        active_plan = db.scalar(
            select(CarePlan).where(CarePlan.mother_id == m.id, CarePlan.active.is_(True))
        )
        if active_plan:
            schedule_reminders_for_care_plan(
                db, active_plan, m, actor_id=s.id, actor_role=normalize_role(s.role)
            )
    audit(
        db,
        s,
        "consent_change",
        "mother",
        mid,
        f"consent={p.consent}; cancelled_jobs={cancelled_jobs}",
    )
    db.commit()
    out = row(m)
    out["cancelled_reminder_jobs"] = cancelled_jobs
    return out


# ---------------------------------------------------------------------------
# Doctor-Authorised Care Plans & Appointment Scheduling
# ---------------------------------------------------------------------------
@app.get("/api/mothers/{mid}/plans")
def plans(
    mid: str,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> list[dict[str, Any]]:
    mother_for(db, s, mid)
    return [
        row(p)
        for p in db.scalars(
            select(CarePlan).where(CarePlan.mother_id == mid).order_by(CarePlan.version.desc())
        )
    ]


@app.post("/api/mothers/{mid}/plans")
def add_plan(
    mid: str,
    p: PlanIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "doctor")
    m = mother_for(db, s, mid)
    all_existing = list(db.scalars(select(CarePlan).where(CarePlan.mother_id == mid)))
    version = max([q.version for q in all_existing], default=0) + 1
    new = CarePlan(
        mother_id=mid,
        clinic=m.clinic,
        visit_date=p.visit_date,
        visit_type=p.visit_type,
        appointment_status="scheduled",
        followup_state="scheduled",
        note=p.note,
        approved_by=s.id,
        version=version,
        active=True,
    )
    db.add(new)
    db.flush()

    cancelled_prior_jobs = 0
    for q in all_existing:
        if q.active and q.id != new.id:
            q.active = False
            q.superseded_by_plan_id = new.id
            if q.followup_state not in ("closed", "visit_confirmed"):
                q.followup_state = "rescheduled_by_authorised_staff"
                q.appointment_status = "rescheduled"
            cancelled_prior_jobs += cancel_obsolete_reminders(
                db,
                clinic=m.clinic,
                care_plan_id=q.id,
                reason=f"superseded_by_plan_v{version}",
                actor_id=s.id,
                actor_role="doctor",
            )

    scheduled_jobs = schedule_reminders_for_care_plan(
        db, new, m, actor_id=s.id, actor_role="doctor"
    )

    audit(
        db,
        s,
        "approve_care_plan",
        "care_plan",
        new.id,
        (
            f"version {version}; visit_date={p.visit_date}; "
            f"cancelled_obsolete_jobs={cancelled_prior_jobs}; scheduled_jobs={len(scheduled_jobs)}"
        ),
    )
    db.commit()
    out = row(new)
    out["cancelled_obsolete_jobs"] = cancelled_prior_jobs
    out["scheduled_reminder_jobs_count"] = len(scheduled_jobs)
    return out


@app.get("/api/appointments")
def list_appointments(
    active_only: bool = Query(default=True),
    status: Optional[str] = Query(default=None),
    overdue_only: bool = Query(default=False),
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> list[dict[str, Any]]:
    valid_mothers = {
        m.id: m
        for m in db.scalars(select(Mother).where(Mother.clinic == s.clinic))
    }
    if not valid_mothers:
        return []

    stmt = select(CarePlan).where(CarePlan.mother_id.in_(valid_mothers.keys()))
    if active_only:
        stmt = stmt.where(CarePlan.active == True)
    if status:
        stmt = stmt.where(CarePlan.appointment_status == status)
    if overdue_only:
        stmt = stmt.where(
            CarePlan.visit_date < date.today(),
            CarePlan.appointment_status == "scheduled",
        )
    stmt = stmt.order_by(CarePlan.visit_date.asc())

    result: list[dict[str, Any]] = []
    for cp in db.scalars(stmt):
        m = valid_mothers.get(cp.mother_id)
        d = row(cp)
        d["mother_name"] = m.name if m else ""
        d["mother_phone"] = m.phone if m else ""
        d["mother_consent"] = m.consent if m else False
        d["is_overdue"] = bool(
            cp.active and cp.visit_date < date.today() and cp.appointment_status == "scheduled"
        )
        result.append(d)
    return result


@app.patch("/api/plans/{pid}/status")
@app.patch("/api/appointments/{pid}")
def update_appointment_status(
    pid: str,
    p: AppointmentStatusIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "doctor", "nurse", "admin", "field_coordinator")
    cp = db.get(CarePlan, pid)
    if not cp or cp.clinic != s.clinic:
        raise HTTPException(404, "Care plan / appointment not found in your clinic")
    m = mother_for(db, s, cp.mother_id)

    cp.appointment_status = p.appointment_status
    if p.follow_up_notes:
        cp.follow_up_notes = p.follow_up_notes

    if p.appointment_status == "missed" and p.create_followup_task:
        followup_task = Task(
            mother_id=m.id,
            clinic=s.clinic,
            category="missed_visit",
            priority="high",
            due_date=date.today(),
            status="open",
            detail=f"Follow up on missed appointment scheduled for {cp.visit_date}. {p.follow_up_notes}".strip(),
            created_by=s.id,
        )
        db.add(followup_task)

    audit(
        db,
        s,
        "appointment_status_change",
        "care_plan",
        cp.id,
        f"status={p.appointment_status}",
    )
    db.commit()
    return row(cp)


# ---------------------------------------------------------------------------
# Reminders & Messaging Simulation
# ---------------------------------------------------------------------------
@app.post("/api/reminders/send")
def send_reminder(
    p: ReminderIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "nurse", "field_coordinator", "asha", "doctor")
    m = mother_for(db, s, p.mother_id)
    if not m.consent:
        raise HTTPException(400, "No communication consent")
    plan = db.scalar(
        select(CarePlan).where(CarePlan.mother_id == m.id, CarePlan.active == True)
    )
    if not plan:
        raise HTTPException(400, "No doctor-approved active plan")
    templates = {
        "en": f"Reminder: your clinic visit is scheduled for {plan.visit_date}. Contact clinic staff to change it.",
        "te": f"క్లినిక్ సందర్శన గుర్తుచేయడం: {plan.visit_date}. మార్పుల కోసం క్లినిక్ సిబ్బందిని సంప్రదించండి.",
        "hi": f"याद दिलाना: आपकी क्लिनिक विज़िट {plan.visit_date} को है। बदलाव के लिए स्टाफ से संपर्क करें।",
    }
    msg = Message(
        mother_id=m.id,
        clinic=s.clinic,
        direction="outbound",
        body=templates.get(m.language, templates["en"]),
        status="simulated",
        provider="local-simulator",
    )
    db.add(msg)
    db.flush()
    audit(db, s, "simulate_reminder", "message", msg.id)
    db.commit()
    return row(msg)


@app.post("/api/messages/reply")
def simulate_reply(
    p: ReplyIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "nurse", "doctor", "field_coordinator", "asha")
    m = mother_for(db, s, p.mother_id)
    msg = Message(
        mother_id=m.id,
        clinic=s.clinic,
        direction="inbound",
        body=p.body,
        status="received",
    )
    db.add(msg)
    db.flush()
    task = Task(
        mother_id=m.id,
        clinic=s.clinic,
        category="patient_reply",
        priority="high",
        detail=f"Review message {msg.id}: {p.body[:120]}",
        created_by=s.id,
    )
    db.add(task)
    db.flush()
    audit(db, s, "receive_reply", "message", msg.id)
    db.commit()
    return row(msg)


@app.get("/api/messages")
def messages(
    mother_id: Optional[str] = Query(default=None),
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> list[dict[str, Any]]:
    valid_mothers = {
        m.id: m.name
        for m in db.scalars(select(Mother).where(Mother.clinic == s.clinic))
    }
    if not valid_mothers:
        return []
    stmt = select(Message).where(Message.mother_id.in_(valid_mothers.keys()))
    if mother_id:
        if mother_id not in valid_mothers:
            raise HTTPException(404, "Mother not found in your clinic")
        stmt = stmt.where(Message.mother_id == mother_id)
    stmt = stmt.order_by(Message.sent_at.desc())

    out: list[dict[str, Any]] = []
    for msg in db.scalars(stmt):
        d = row(msg)
        d["mother_name"] = valid_mothers.get(msg.mother_id, "")
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Follow-up Task Assignment & Completion
# ---------------------------------------------------------------------------
@app.post("/api/tasks")
def add_task(
    p: TaskIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "doctor", "nurse", "field_coordinator", "asha")
    m = mother_for(db, s, p.mother_id)
    if p.assigned_to:
        assignee = db.get(Staff, p.assigned_to)
        if assignee and assignee.clinic != s.clinic:
            raise HTTPException(400, "Cannot assign task to staff member from another clinic")

    t = Task(
        **p.model_dump(),
        clinic=m.clinic,
        created_by=s.id,
    )
    db.add(t)
    db.flush()
    audit(db, s, "create", "task", t.id, f"category={t.category}; assigned_to={t.assigned_to}")
    db.commit()
    return row(t)


@app.get("/api/tasks")
def tasks(
    status: Optional[str] = Query(default=None),
    assigned_to: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> list[dict[str, Any]]:
    valid_mothers = {
        m.id: m.name
        for m in db.scalars(select(Mother).where(Mother.clinic == s.clinic))
    }
    if not valid_mothers:
        return []
    clinic_staff = {
        st.id: st.name
        for st in db.scalars(select(Staff).where(Staff.clinic == s.clinic))
    }

    stmt = select(Task).where(Task.mother_id.in_(valid_mothers.keys()))
    if status:
        stmt = stmt.where(Task.status == status)
    if assigned_to:
        stmt = stmt.where(Task.assigned_to == assigned_to)
    if priority:
        stmt = stmt.where(Task.priority == priority)
    stmt = stmt.order_by(Task.created_at.desc())

    out: list[dict[str, Any]] = []
    for t in db.scalars(stmt):
        d = row(t)
        d["mother_name"] = valid_mothers.get(t.mother_id, "")
        d["assigned_to_name"] = clinic_staff.get(t.assigned_to, t.assigned_to or "Unassigned")
        out.append(d)
    return out


@app.patch("/api/tasks/{tid}")
def update_task(
    tid: str,
    p: StatusIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "doctor", "nurse", "field_coordinator", "asha")
    t = db.get(Task, tid)
    if not t or t.clinic != s.clinic:
        raise HTTPException(404, "Task not found in your clinic")
    mother_for(db, s, t.mother_id)

    if p.assigned_to is not None:
        if p.assigned_to:
            assignee = db.get(Staff, p.assigned_to)
            if assignee and assignee.clinic != s.clinic:
                raise HTTPException(400, "Cannot assign task to staff from another clinic")
        t.assigned_to = p.assigned_to
    if p.priority is not None:
        t.priority = p.priority
    if p.due_date is not None:
        t.due_date = p.due_date
    if p.completion_notes is not None:
        t.completion_notes = p.completion_notes

    t.status = p.status
    if p.status == "resolved":
        t.completed_at = now()

    audit(db, s, "status_change", "task", t.id, p.status)
    db.commit()
    return row(t)


# ---------------------------------------------------------------------------
# Transport Coordination
# ---------------------------------------------------------------------------
@app.post("/api/transport")
def add_transport(
    p: TransportIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "doctor", "nurse", "field_coordinator", "asha")
    m = mother_for(db, s, p.mother_id)

    # Clinical Safety & Regulatory Guard:
    # JananiSetu coordinates scheduled routine maternal transit only.
    # It does NOT operate or autonomously dispatch government 108/102 emergency ambulances.
    partner_clean = p.partner.strip().lower()
    notes_clean = p.vehicle_notes.strip().lower()
    if any(k in partner_clean or k in notes_clean for k in ("108 emergency", "102 emergency", "ambulance dispatch", "emergency 108 fleet", "emergency ambulance")):
        if "external protocol" not in partner_clean and "escalation" not in partner_clean and "external protocol" not in notes_clean:
            raise HTTPException(
                400,
                "Clinical Safety Guard: JananiSetu does not provide autonomous 108/102 ambulance dispatch. Emergency cases must follow the clinically approved external telephone escalation protocol (Call 108/102 directly). In-app transport is restricted to scheduled maternal transit or empaneled non-emergency transport partners.",
            )

    t = Transport(
        **p.model_dump(),
        clinic=m.clinic,
        requested_by=s.id,
    )
    db.add(t)
    db.flush()
    audit(db, s, "request", "transport", t.id, f"date={t.date}; partner={t.partner}")
    db.commit()
    return row(t)


@app.get("/api/transport")
def transport(
    status: Optional[str] = Query(default=None),
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> list[dict[str, Any]]:
    valid_mothers = {
        m.id: m
        for m in db.scalars(select(Mother).where(Mother.clinic == s.clinic))
    }
    if not valid_mothers:
        return []
    stmt = select(Transport).where(Transport.mother_id.in_(valid_mothers.keys()))
    if status:
        stmt = stmt.where(Transport.status == status)
    stmt = stmt.order_by(Transport.date.desc())

    out: list[dict[str, Any]] = []
    for tr in db.scalars(stmt):
        m = valid_mothers.get(tr.mother_id)
        d = row(tr)
        d["mother_name"] = m.name if m else ""
        d["mother_phone"] = m.phone if m else ""
        out.append(d)
    return out


@app.patch("/api/transport/{tid}")
def transport_status(
    tid: str,
    p: TransportStatus,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "doctor", "nurse", "field_coordinator", "asha")
    t = db.get(Transport, tid)
    if not t or t.clinic != s.clinic:
        raise HTTPException(404, "Transport not found in your clinic")
    mother_for(db, s, t.mother_id)
    t.status = p.status
    if p.partner is not None:
        t.partner = p.partner
    if p.pickup_time is not None:
        t.pickup_time = p.pickup_time
    if p.vehicle_notes is not None:
        t.vehicle_notes = p.vehicle_notes
    audit(db, s, "status_change", "transport", tid, f"status={p.status}; partner={t.partner}")
    db.commit()
    return row(t)


# ---------------------------------------------------------------------------
# Operational Expenditure Tracking (Clinic-Scoped, Admin-Authorised)
# ---------------------------------------------------------------------------
@app.post("/api/expenses")
def add_expense(
    p: ExpenseIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin")
    e = Expense(
        clinic=s.clinic,
        category=p.category,
        amount_paise=p.amount_rupees * 100,
        description=p.description,
        receipt_ref=p.receipt_ref,
        created_by=s.id,
    )
    db.add(e)
    db.flush()
    audit(db, s, "record", "expense", e.id, f"amount_paise={e.amount_paise}; category={e.category}")
    db.commit()
    return row(e)


@app.get("/api/expenses")
def expenses(
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> list[dict[str, Any]]:
    permitted(s, "admin")
    return [
        row(e)
        for e in db.scalars(
            select(Expense)
            .where(Expense.clinic == s.clinic)
            .order_by(Expense.created_at.desc())
        )
    ]


@app.patch("/api/expenses/{eid}")
def approve_expense(
    eid: str,
    p: ApprovalIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin")
    e = db.get(Expense, eid)
    if not e or e.clinic != s.clinic:
        raise HTTPException(404, "Expense not found in your clinic")
    e.approved = p.approved
    e.approved_by = s.id if p.approved else ""
    audit(db, s, "approval", "expense", eid, str(p.approved))
    db.commit()
    return row(e)


# ---------------------------------------------------------------------------
# Phase 3: Real ANC Card Extraction, Evidence-Linked Verification & Versioning
# ---------------------------------------------------------------------------
def _serialize_document_full(db: Session, doc: Document, m: Mother) -> dict[str, Any]:
    """Assemble full evidence-linked verification payload for a document."""
    d = row(doc)
    d["mother_name"] = m.name
    d["mother_phone"] = m.phone

    ocr_job = db.scalar(
        select(OcrJob)
        .where(OcrJob.document_id == doc.id)
        .order_by(OcrJob.started_at.desc())
    )
    if ocr_job:
        job_dict = row(ocr_job, exclude={"raw_tokens_json"})
        try:
            job_dict["missing_fields"] = json.loads(ocr_job.missing_fields_json or "[]")
        except Exception:
            job_dict["missing_fields"] = []
        try:
            job_dict["conflicts"] = json.loads(ocr_job.conflicts_json or "[]")
        except Exception:
            job_dict["conflicts"] = []
        d["ocr_job"] = job_dict
    else:
        d["ocr_job"] = None

    fields_rows = list(
        db.scalars(
            select(ExtractedField)
            .where(ExtractedField.document_id == doc.id)
            .order_by(ExtractedField.id)
        )
    )
    locs_by_field: dict[str, list[dict[str, Any]]] = {}
    for loc in db.scalars(
        select(FieldSourceLocation).where(FieldSourceLocation.document_id == doc.id)
    ):
        locs_by_field.setdefault(loc.extracted_field_id, []).append(row(loc))

    serialized_fields: list[dict[str, Any]] = []
    for ef in fields_rows:
        ef_dict = row(ef)
        try:
            ef_dict["conflicting_values"] = json.loads(ef.conflicting_values_json or "[]")
        except Exception:
            ef_dict["conflicting_values"] = []
        ef_dict["source_locations"] = locs_by_field.get(ef.id, [])
        serialized_fields.append(ef_dict)
    d["fields"] = serialized_fields

    # Version history for this mother
    mother_docs = list(
        db.scalars(
            select(Document)
            .where(Document.mother_id == m.id, Document.clinic == doc.clinic)
            .order_by(Document.version_number.desc(), Document.created_at.desc())
        )
    )
    d["versions"] = [
        {
            "id": md.id,
            "version_number": md.version_number,
            "filename": md.filename,
            "ocr_status": md.ocr_status,
            "confirmed": md.confirmed,
            "review_status": md.review_status,
            "confirmed_by": md.confirmed_by,
            "confirmed_at": md.confirmed_at.isoformat() if md.confirmed_at else None,
            "created_at": md.created_at.isoformat() if md.created_at else None,
        }
        for md in mother_docs
    ]

    # Version comparison against mother's confirmed profile and prior confirmed version
    prev_ver = db.scalar(
        select(DocumentVersion)
        .where(
            DocumentVersion.mother_id == m.id,
            DocumentVersion.document_id != doc.id,
            DocumentVersion.confirmed_at.is_not(None),
        )
        .order_by(DocumentVersion.version_number.desc())
    )
    prev_snapshot: dict[str, Any] = {}
    if prev_ver and prev_ver.confirmed_snapshot_json:
        try:
            prev_snapshot = json.loads(prev_ver.confirmed_snapshot_json)
        except Exception:
            prev_snapshot = {}

    mother_current_map = {
        "patient_name": m.name,
        "patient_identifier": m.patient_identifier or None,
        "contact_phone": m.phone,
        "lmp_date": m.lmp.isoformat() if m.lmp else None,
        "edd_date": m.edd.isoformat() if m.edd else None,
        "address": m.address or None,
    }

    comparisons: list[dict[str, Any]] = []
    for ef in fields_rows:
        candidate_val = ef.final_value or ef.normalized_value or ef.extracted_value
        curr_mother_val = mother_current_map.get(ef.field_key)
        prior_doc_val = prev_snapshot.get(ef.field_key)
        baseline_val = prior_doc_val if prior_doc_val is not None else curr_mother_val
        changed = bool(
            baseline_val
            and candidate_val
            and str(baseline_val).strip() != str(candidate_val).strip()
        )
        comparisons.append(
            {
                "field_key": ef.field_key,
                "field_label": ef.field_label,
                "current_patient_record": curr_mother_val,
                "previous_confirmed_version": prior_doc_val,
                "document_extracted": ef.extracted_value,
                "document_normalized": ef.normalized_value,
                "document_final": ef.final_value,
                "differs_from_confirmed": changed,
            }
        )
    d["version_comparison"] = comparisons

    d["change_proposals"] = [
        row(cp)
        for cp in db.scalars(
            select(AdminChangeProposal)
            .where(AdminChangeProposal.document_id == doc.id)
            .order_by(AdminChangeProposal.created_at.desc())
        )
    ]
    d["decisions"] = [
        row(vd)
        for vd in db.scalars(
            select(VerificationDecision)
            .where(VerificationDecision.document_id == doc.id)
            .order_by(VerificationDecision.decided_at.desc())
        )
    ]
    return d


def _ingest_document_and_run_ocr(
    db: Session,
    s: Staff,
    m: Mother,
    filename: str,
    content_type: str,
    contents: bytes,
    use_external_provider: bool = False,
    simulate_ocr_failure: bool = False,
) -> dict[str, Any]:
    try:
        norm_ct, sha256_hex = validate_and_inspect_upload(filename, content_type, contents)
    except DocumentValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    # Determine next version_number for this mother
    existing_docs = list(
        db.scalars(
            select(Document)
            .where(Document.mother_id == m.id)
            .order_by(Document.version_number.desc(), Document.created_at.desc())
        )
    )
    next_version = (max([d.version_number for d in existing_docs], default=0)) + 1
    supersedes_id = existing_docs[0].id if existing_docs else None

    # Load previous confirmed snapshot for cross-version comparison
    prev_confirmed_ver = db.scalar(
        select(DocumentVersion)
        .where(
            DocumentVersion.mother_id == m.id,
            DocumentVersion.confirmed_at.is_not(None),
        )
        .order_by(DocumentVersion.version_number.desc())
    )
    prev_confirmed_fields: dict[str, Any] = {}
    if prev_confirmed_ver and prev_confirmed_ver.confirmed_snapshot_json:
        try:
            prev_confirmed_fields = json.loads(prev_confirmed_ver.confirmed_snapshot_json)
        except Exception:
            prev_confirmed_fields = {}

    mother_snapshot = {
        "name": m.name,
        "patient_identifier": m.patient_identifier,
        "phone": m.phone,
        "lmp": m.lmp.isoformat() if m.lmp else None,
        "edd": m.edd.isoformat() if m.edd else None,
        "address": m.address,
    }

    try:
        ocr_res = run_anc_ocr_pipeline(
            contents=contents,
            content_type=norm_ct,
            existing_mother=mother_snapshot,
            previous_confirmed_fields=prev_confirmed_fields,
            request_external_provider=use_external_provider,
            mother_consent=m.consent,
            simulate_ocr_failure=simulate_ocr_failure,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    doc = Document(
        mother_id=m.id,
        clinic=m.clinic,
        version_number=next_version,
        supersedes_document_id=supersedes_id,
        filename=Path(filename or "scan.png").name[:160],
        content_type=norm_ct,
        file_size_bytes=len(contents),
        sha256_hash=sha256_hex,
        image_width=ocr_res.image_width,
        image_height=ocr_res.image_height,
        page_count=ocr_res.page_count,
        ocr_status=ocr_res.ocr_status,
        ocr_engine=ocr_res.ocr_engine,
        ocr_error=ocr_res.error_message,
        extracted_text=(
            ocr_res.extracted_text[:10000]
            if ocr_res.extracted_text
            else f"[OCR status: {ocr_res.ocr_status}. {ocr_res.error_message or 'Manual transcription required.'}]"
        ),
        confirmed=False,
        review_status="pending_review",
        uploaded_by=s.id,
    )
    db.add(doc)
    db.flush()

    # Store raw binary and rendered PNG preview in private clinic-scoped storage
    priv_dir = _private_storage_dir(m.clinic)
    raw_file = priv_dir / f"{doc.id}.bin"
    preview_file = priv_dir / f"{doc.id}_preview.png"
    raw_file.write_bytes(contents)
    if ocr_res.preview_png_bytes:
        preview_file.write_bytes(ocr_res.preview_png_bytes)

    # Also keep legacy path in DATA / 'scans' for backward compatibility
    legacy_scans = Path(os.getenv("JANANI_DATA_DIR", str(DATA))) / "scans"
    legacy_scans.mkdir(parents=True, exist_ok=True)
    (legacy_scans / f"{doc.id}.img").write_bytes(contents)

    doc.stored_path = f"{m.clinic}/{doc.id}.bin"
    doc.preview_path = f"{m.clinic}/{doc.id}_preview.png"

    ocr_job = OcrJob(
        document_id=doc.id,
        clinic=m.clinic,
        engine=ocr_res.ocr_engine,
        external_provider_used=False,
        status="failed" if ocr_res.ocr_status == "failed" else "succeeded",
        completed_at=now(),
        duration_ms=ocr_res.duration_ms,
        word_count=ocr_res.word_count,
        mean_confidence=ocr_res.mean_confidence,
        missing_fields_json=json.dumps(ocr_res.missing_fields),
        conflicts_json=json.dumps(ocr_res.conflicts),
        error_message=ocr_res.error_message,
        raw_tokens_json=json.dumps(ocr_res.raw_tokens[:500]),
    )
    db.add(ocr_job)
    db.flush()

    for cand in ocr_res.fields:
        ef = ExtractedField(
            document_id=doc.id,
            ocr_job_id=ocr_job.id,
            clinic=m.clinic,
            field_key=cand.field_key,
            field_label=cand.field_label,
            extracted_value=cand.extracted_value,
            normalized_value=cand.normalized_value,
            confidence=cand.confidence,
            uncertainty_flag=cand.uncertainty_flag,
            uncertainty_reason=cand.uncertainty_reason[:255],
            conflict_detected=cand.conflict_detected,
            conflicting_values_json=json.dumps(cand.conflicting_values),
            source_page=cand.source_page,
            bbox_x=cand.bbox_x,
            bbox_y=cand.bbox_y,
            bbox_w=cand.bbox_w,
            bbox_h=cand.bbox_h,
            source_snippet=cand.source_snippet,
            verification_status="unreviewed",
            final_value=None,
        )
        db.add(ef)
        db.flush()

        for tok in cand.tokens:
            db.add(
                FieldSourceLocation(
                    extracted_field_id=ef.id,
                    document_id=doc.id,
                    clinic=m.clinic,
                    page_number=int(tok.get("page", 1)),
                    x=int(tok.get("x", 0)),
                    y=int(tok.get("y", 0)),
                    width=int(tok.get("w", 10)),
                    height=int(tok.get("h", 10)),
                    token_text=str(tok.get("text", ""))[:200],
                    token_confidence=float(tok.get("conf", 0.0)),
                )
            )

    doc_ver = DocumentVersion(
        mother_id=m.id,
        document_id=doc.id,
        clinic=m.clinic,
        version_number=next_version,
        previous_document_id=supersedes_id,
        confirmed_snapshot_json="{}",
        diff_summary_json=json.dumps(ocr_res.conflicts),
        created_by=s.id,
    )
    db.add(doc_ver)
    audit(
        db,
        s,
        "upload_ocr_unconfirmed",
        "document",
        doc.id,
        f"v{next_version}; status={ocr_res.ocr_status}; engine={ocr_res.ocr_engine}",
    )
    db.commit()
    return _serialize_document_full(db, doc, m)


@app.post("/api/mothers/{mid}/documents")
async def upload(
    mid: str,
    file: UploadFile = File(...),
    use_external_provider: bool = Query(default=False),
    simulate_ocr_failure: bool = Query(default=False),
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "nurse", "doctor", "field_coordinator", "asha")
    m = mother_for(db, s, mid)
    contents = await file.read(5_000_001)
    return _ingest_document_and_run_ocr(
        db=db,
        s=s,
        m=m,
        filename=file.filename or "scan.png",
        content_type=file.content_type or "",
        contents=contents,
        use_external_provider=use_external_provider,
        simulate_ocr_failure=simulate_ocr_failure,
    )


@app.post("/api/mothers/{mid}/documents/fixture/{fixture_id}")
def upload_synthetic_fixture(
    mid: str,
    fixture_id: str,
    format: Literal["png", "pdf"] = Query(default="png"),
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "nurse", "doctor", "field_coordinator", "asha")
    m = mother_for(db, s, mid)
    if fixture_id not in FIXTURE_SPECS:
        raise HTTPException(404, f"Unknown synthetic fixture '{fixture_id}'")

    if format == "pdf":
        raw_bytes = generate_fixture_pdf_bytes(fixture_id)
        fname = f"{fixture_id}.pdf"
        ctype = "application/pdf"
    else:
        raw_bytes = generate_fixture_image_bytes(fixture_id)
        fname = f"{fixture_id}.png"
        ctype = "image/png"

    return _ingest_document_and_run_ocr(
        db=db,
        s=s,
        m=m,
        filename=fname,
        content_type=ctype,
        contents=raw_bytes,
    )


@app.get("/api/documents/fixtures")
def list_synthetic_fixtures(s: Staff = Depends(who)) -> list[dict[str, Any]]:
    return [
        {
            "id": fid,
            "title": spec["title"],
            "description": spec["description"],
            "ground_truth": spec["ground_truth"],
        }
        for fid, spec in FIXTURE_SPECS.items()
    ]


@app.get("/api/documents/fixtures/evaluate")
def run_fixture_benchmark_endpoint(s: Staff = Depends(who)) -> dict[str, Any]:
    permitted(s, "admin", "doctor", "nurse")
    return evaluate_fixtures_benchmark()


@app.get("/api/mothers/{mid}/documents")
def documents(
    mid: str,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> list[dict[str, Any]]:
    m = mother_for(db, s, mid)
    docs = list(
        db.scalars(
            select(Document)
            .where(Document.mother_id == mid)
            .order_by(Document.version_number.desc(), Document.created_at.desc())
        )
    )
    return [_serialize_document_full(db, d, m) for d in docs]


@app.get("/api/documents")
def all_clinic_documents(
    confirmed: Optional[bool] = Query(default=None),
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> list[dict[str, Any]]:
    valid_mothers = {
        m.id: m
        for m in db.scalars(select(Mother).where(Mother.clinic == s.clinic))
    }
    if not valid_mothers:
        return []
    stmt = select(Document).where(Document.mother_id.in_(valid_mothers.keys()))
    if confirmed is not None:
        stmt = stmt.where(Document.confirmed == confirmed)
    stmt = stmt.order_by(Document.created_at.desc())

    out: list[dict[str, Any]] = []
    for d in db.scalars(stmt):
        m = valid_mothers.get(d.mother_id)
        if m:
            out.append(_serialize_document_full(db, d, m))
    return out


@app.get("/api/documents/{did}")
def get_document_detail(
    did: str,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    doc, m = document_for(db, s, did)
    return _serialize_document_full(db, doc, m)


@app.get("/api/documents/{did}/file")
def download_document_image(
    did: str,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> FileResponse:
    doc, m = document_for(db, s, did)
    priv_path = _private_storage_dir(m.clinic) / f"{doc.id}.bin"
    if priv_path.is_file():
        return FileResponse(
            priv_path,
            media_type=doc.content_type or "application/octet-stream",
            filename=doc.filename,
        )
    legacy_path = Path(os.getenv("JANANI_DATA_DIR", str(DATA))) / "scans" / f"{doc.id}.img"
    if legacy_path.is_file():
        return FileResponse(
            legacy_path,
            media_type=doc.content_type or "image/png",
            filename=doc.filename,
        )
    raise HTTPException(404, "Document file not found on disk")


@app.get("/api/documents/{did}/preview")
def download_document_preview(
    did: str,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> FileResponse:
    doc, m = document_for(db, s, did)
    preview_path = _private_storage_dir(m.clinic) / f"{doc.id}_preview.png"
    if preview_path.is_file():
        return FileResponse(
            preview_path,
            media_type="image/png",
            filename=f"{doc.id}_preview.png",
        )
    return download_document_image(did, db, s)


@app.patch("/api/documents/{did}/fields/{fid}")
def verify_single_field(
    did: str,
    fid: str,
    p: FieldDecisionIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "nurse", "doctor")
    doc, m = document_for(db, s, did)
    ef = db.get(ExtractedField, fid)
    if not ef or ef.document_id != doc.id or ef.clinic != s.clinic:
        raise HTTPException(404, "Extracted field not found on this document")

    if p.decision == "accepted":
        candidate = ef.normalized_value or ef.extracted_value
        if not candidate:
            raise HTTPException(
                422,
                "Cannot accept a missing or unparseable field without providing a corrected value",
            )
        if ef.field_key in DATE_FIELD_KEYS and not ef.normalized_value:
            raise HTTPException(
                422,
                f"Cannot accept invalid date '{ef.extracted_value}'; use 'corrected' with YYYY-MM-DD",
            )
        final_val: Optional[str] = candidate
    elif p.decision in ("corrected", "illegible_manual"):
        if not p.final_value or not p.final_value.strip():
            raise HTTPException(
                422, f"final_value is required when decision is '{p.decision}'"
            )
        final_val = p.final_value.strip()
        if ef.field_key in DATE_FIELD_KEYS:
            try:
                date.fromisoformat(final_val)
            except ValueError as exc:
                raise HTTPException(
                    422, f"Date field '{ef.field_key}' must use ISO format YYYY-MM-DD"
                ) from exc
    else:
        # rejected
        final_val = None

    ef.verification_status = p.decision
    ef.final_value = final_val
    ef.reviewer_note = p.reviewer_note
    ef.verified_by = s.id
    ef.verified_at = now()

    db.add(
        VerificationDecision(
            document_id=doc.id,
            extracted_field_id=ef.id,
            clinic=s.clinic,
            field_key=ef.field_key,
            decision=p.decision,
            extracted_value=ef.extracted_value,
            final_value=final_val,
            notes=p.reviewer_note,
            decided_by=s.id,
            decided_by_role=normalize_role(s.role),
        )
    )
    audit(
        db,
        s,
        "verify_document_field",
        "extracted_field",
        ef.id,
        f"field={ef.field_key}; decision={p.decision}; final={final_val}",
    )
    db.commit()
    return _serialize_document_full(db, doc, m)


@app.patch("/api/documents/{did}/confirm")
def confirm_document(
    did: str,
    p: ConfirmIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "nurse", "doctor")
    doc, m = document_for(db, s, did)

    fields_rows = {
        ef.field_key: ef
        for ef in db.scalars(select(ExtractedField).where(ExtractedField.document_id == doc.id))
    }

    # Apply any inline field_decisions submitted in the confirmation payload
    if p.field_decisions:
        for item in p.field_decisions:
            ef = fields_rows.get(item.field_key)
            if not ef:
                continue
            if item.decision == "accepted":
                candidate = item.final_value or ef.normalized_value or ef.extracted_value
                if not candidate:
                    raise HTTPException(
                        422,
                        f"Field '{item.field_key}' is missing/invalid and cannot be accepted without correction",
                    )
                if ef.field_key in DATE_FIELD_KEYS and not ef.normalized_value and not item.final_value:
                    raise HTTPException(
                        422,
                        f"Field '{item.field_key}' has an invalid date and must be corrected or rejected",
                    )
                final_val: Optional[str] = candidate
            elif item.decision in ("corrected", "illegible_manual"):
                if not item.final_value or not item.final_value.strip():
                    raise HTTPException(
                        422,
                        f"Field '{item.field_key}' requires a final_value for '{item.decision}'",
                    )
                final_val = item.final_value.strip()
            else:
                final_val = None

            ef.verification_status = item.decision
            ef.final_value = final_val
            ef.reviewer_note = item.reviewer_note
            ef.verified_by = s.id
            ef.verified_at = now()
            db.add(
                VerificationDecision(
                    document_id=doc.id,
                    extracted_field_id=ef.id,
                    clinic=s.clinic,
                    field_key=ef.field_key,
                    decision=item.decision,
                    extracted_value=ef.extracted_value,
                    final_value=final_val,
                    notes=item.reviewer_note,
                    decided_by=s.id,
                    decided_by_role=normalize_role(s.role),
                )
            )

    # Assemble confirmed administrative snapshot from verified fields
    confirmed_snapshot: dict[str, Any] = {}
    if p.structured_fields:
        confirmed_snapshot.update(p.structured_fields)

    for fkey, ef in fields_rows.items():
        if ef.verification_status in ("accepted", "corrected", "illegible_manual") and ef.final_value:
            confirmed_snapshot[fkey] = ef.final_value

    if p.corrected_text:
        doc.extracted_text = p.corrected_text
    doc.structured_fields = json.dumps(confirmed_snapshot)
    doc.confirmed = True
    doc.review_status = "confirmed"
    doc.confirmed_by = s.id
    doc.confirmed_at = now()

    # Update DocumentVersion snapshot
    doc_ver = db.scalar(
        select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
    )
    if doc_ver:
        doc_ver.confirmed_snapshot_json = json.dumps(confirmed_snapshot)
        doc_ver.confirmed_by = s.id
        doc_ver.confirmed_at = now()

    # Record document-level VerificationDecision
    db.add(
        VerificationDecision(
            document_id=doc.id,
            extracted_field_id=None,
            clinic=s.clinic,
            field_key="__document__",
            decision="document_confirmed",
            extracted_value=None,
            final_value=json.dumps(confirmed_snapshot),
            notes="Human confirmation recorded",
            decided_by=s.id,
            decided_by_role=normalize_role(s.role),
        )
    )

    # Generate Administrative Change Proposals when confirmed document fields differ
    # from the mother's existing profile OR contain a documented follow-up date.
    # IMPORTANT: Never automatically overwrite confirmed patient fields or doctor-authorised CarePlans!
    profile_field_mapping = {
        "patient_name": ("name", m.name),
        "patient_identifier": ("patient_identifier", m.patient_identifier or None),
        "contact_phone": ("phone", m.phone),
        "lmp_date": ("lmp", m.lmp.isoformat() if m.lmp else None),
        "edd_date": ("edd", m.edd.isoformat() if m.edd else None),
        "address": ("address", m.address or None),
    }

    for fkey, (_, current_val) in profile_field_mapping.items():
        new_val = confirmed_snapshot.get(fkey)
        if not new_val:
            continue
        if str(current_val or "").strip() != str(new_val).strip():
            existing_prop = db.scalar(
                select(AdminChangeProposal).where(
                    AdminChangeProposal.document_id == doc.id,
                    AdminChangeProposal.field_key == fkey,
                )
            )
            if not existing_prop:
                db.add(
                    AdminChangeProposal(
                        mother_id=m.id,
                        document_id=doc.id,
                        clinic=s.clinic,
                        field_key=fkey,
                        previous_value=str(current_val) if current_val else None,
                        proposed_value=str(new_val),
                        proposal_type="mother_profile_update",
                        status="pending",
                    )
                )

    # If follow_up_date was verified on the ANC card, create an appointment_schedule_note proposal
    # for doctor review — NEVER automatically create or overwrite a CarePlan!
    verified_followup = confirmed_snapshot.get("follow_up_date")
    if verified_followup:
        active_plan = db.scalar(
            select(CarePlan).where(CarePlan.mother_id == m.id, CarePlan.active == True)
        )
        current_plan_date = active_plan.visit_date.isoformat() if active_plan else None
        if current_plan_date != str(verified_followup).strip():
            existing_fp = db.scalar(
                select(AdminChangeProposal).where(
                    AdminChangeProposal.document_id == doc.id,
                    AdminChangeProposal.field_key == "follow_up_date",
                )
            )
            if not existing_fp:
                db.add(
                    AdminChangeProposal(
                        mother_id=m.id,
                        document_id=doc.id,
                        clinic=s.clinic,
                        field_key="follow_up_date",
                        previous_value=current_plan_date,
                        proposed_value=str(verified_followup).strip(),
                        proposal_type="appointment_schedule_note",
                        status="pending",
                    )
                )

    audit(
        db,
        s,
        "confirm_extraction",
        "document",
        did,
        f"v{doc.version_number}; confirmed_fields={len(confirmed_snapshot)}",
    )
    db.commit()
    return _serialize_document_full(db, doc, m)


@app.get("/api/mothers/{mid}/change-proposals")
def list_mother_change_proposals(
    mid: str,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> list[dict[str, Any]]:
    mother_for(db, s, mid)
    return [
        row(cp)
        for cp in db.scalars(
            select(AdminChangeProposal)
            .where(AdminChangeProposal.mother_id == mid, AdminChangeProposal.clinic == s.clinic)
            .order_by(AdminChangeProposal.created_at.desc())
        )
    ]


@app.post("/api/change-proposals/{pid}/decide")
def decide_change_proposal(
    pid: str,
    p: ChangeProposalDecisionIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "nurse", "doctor")
    prop = db.get(AdminChangeProposal, pid)
    if not prop or prop.clinic != s.clinic:
        raise HTTPException(404, "Administrative change proposal not found in your clinic")
    m = mother_for(db, s, prop.mother_id)

    prop.status = p.decision
    prop.reviewed_by = s.id
    prop.reviewed_by_role = normalize_role(s.role)
    prop.review_note = p.review_note
    prop.reviewed_at = now()

    if p.decision == "approved" and prop.proposal_type == "mother_profile_update":
        val = prop.proposed_value.strip()
        if prop.field_key == "patient_name":
            m.name = val
        elif prop.field_key == "patient_identifier":
            m.patient_identifier = val
        elif prop.field_key == "contact_phone":
            m.phone = val
        elif prop.field_key == "lmp_date":
            m.lmp = date.fromisoformat(val)
        elif prop.field_key == "edd_date":
            m.edd = date.fromisoformat(val)
        elif prop.field_key == "address":
            m.address = val
    elif p.decision == "approved" and prop.proposal_type == "appointment_schedule_note":
        # Healthcare restriction: Do NOT automatically overwrite or replace doctor-authorised CarePlans!
        # Instead, append an administrative note on Mother.notes so the licensed doctor can authorise a CarePlan.
        note_entry = (
            f"[Verified ANC Card v-doc {prop.document_id}: documented follow-up date {prop.proposed_value} "
            f"acknowledged by {s.name} ({normalize_role(s.role)})]"
        )
        m.notes = f"{m.notes}\n{note_entry}".strip()

    audit(
        db,
        s,
        f"change_proposal_{p.decision}",
        "admin_change_proposal",
        prop.id,
        f"field={prop.field_key}; value={prop.proposed_value}",
    )
    db.commit()
    return row(prop)


# ---------------------------------------------------------------------------
# Audit Logging, Analytics & Operational Reports
# ---------------------------------------------------------------------------
@app.get("/api/events")
def events(
    limit: int = Query(default=100, ge=1, le=500),
    entity: Optional[str] = Query(default=None),
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> list[dict[str, Any]]:
    permitted(s, "admin", "doctor")
    stmt = select(Event).where(Event.clinic == s.clinic)
    if entity:
        stmt = stmt.where(Event.entity == entity)
    stmt = stmt.order_by(Event.occurred.desc()).limit(limit)
    return [row(x) for x in db.scalars(stmt)]


@app.get("/api/analytics")
def analytics(
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    mids = select(Mother.id).where(Mother.clinic == s.clinic)
    total_mothers = db.scalar(select(func.count(Mother.id)).where(Mother.clinic == s.clinic)) or 0
    consented_mothers = (
        db.scalar(
            select(func.count(Mother.id)).where(
                Mother.clinic == s.clinic, Mother.consent == True
            )
        )
        or 0
    )
    overdue_plans = (
        db.scalar(
            select(func.count(CarePlan.id)).where(
                CarePlan.mother_id.in_(mids),
                CarePlan.active == True,
                CarePlan.visit_date < date.today(),
                CarePlan.appointment_status == "scheduled",
            )
        )
        or 0
    )
    upcoming_plans = (
        db.scalar(
            select(func.count(CarePlan.id)).where(
                CarePlan.mother_id.in_(mids),
                CarePlan.active == True,
                CarePlan.visit_date >= date.today(),
            )
        )
        or 0
    )
    active_plans = (
        db.scalar(
            select(func.count(CarePlan.id)).where(
                CarePlan.mother_id.in_(mids),
                CarePlan.active == True,
            )
        )
        or 0
    )
    open_tasks = (
        db.scalar(
            select(func.count(Task.id)).where(
                Task.mother_id.in_(mids),
                Task.status != "resolved",
                Task.status != "cancelled",
            )
        )
        or 0
    )
    total_messages = (
        db.scalar(select(func.count(Message.id)).where(Message.mother_id.in_(mids))) or 0
    )
    total_transport = (
        db.scalar(select(func.count(Transport.id)).where(Transport.mother_id.in_(mids))) or 0
    )

    tasks_list = list(db.scalars(select(Task).where(Task.mother_id.in_(mids))))
    tasks_by_status = {"open": 0, "in_progress": 0, "resolved": 0, "cancelled": 0}
    tasks_by_priority = {"low": 0, "medium": 0, "high": 0, "urgent": 0}
    for t in tasks_list:
        tasks_by_status[t.status] = tasks_by_status.get(t.status, 0) + 1
        tasks_by_priority[t.priority] = tasks_by_priority.get(t.priority, 0) + 1

    transport_list = list(db.scalars(select(Transport).where(Transport.mother_id.in_(mids))))
    transport_by_status = {
        "requested": 0,
        "assigned": 0,
        "in_transit": 0,
        "completed": 0,
        "cancelled": 0,
    }
    for tr in transport_list:
        transport_by_status[tr.status] = transport_by_status.get(tr.status, 0) + 1

    docs_list = list(db.scalars(select(Document).where(Document.mother_id.in_(mids))))
    docs_confirmed = sum(1 for d in docs_list if d.confirmed)
    docs_unconfirmed = len(docs_list) - docs_confirmed

    pending_proposals = (
        db.scalar(
            select(func.count(AdminChangeProposal.id)).where(
                AdminChangeProposal.clinic == s.clinic,
                AdminChangeProposal.status == "pending",
            )
        )
        or 0
    )

    expenses_list = list(db.scalars(select(Expense).where(Expense.clinic == s.clinic)))
    expenses_total_paise = sum(e.amount_paise for e in expenses_list)
    expenses_approved_paise = sum(e.amount_paise for e in expenses_list if e.approved)
    expenses_pending_paise = expenses_total_paise - expenses_approved_paise
    expenses_by_category: dict[str, int] = {}
    for e in expenses_list:
        expenses_by_category[e.category] = (
            expenses_by_category.get(e.category, 0) + e.amount_paise
        )

    staff_list_clinic = list(
        db.scalars(select(Staff).where(Staff.clinic == s.clinic, Staff.is_active == True))
    )
    staff_by_role = {"admin": 0, "doctor": 0, "nurse": 0, "field_coordinator": 0}
    for st in staff_list_clinic:
        nr = normalize_role(st.role)
        staff_by_role[nr] = staff_by_role.get(nr, 0) + 1

    # Phase 4: Follow-up state machine & reminder queue analytics
    plans_clinic = list(
        db.scalars(
            select(CarePlan).where(CarePlan.mother_id.in_(mids), CarePlan.active.is_(True))
        )
    )
    followup_states_breakdown: dict[str, int] = {}
    for cp in plans_clinic:
        st_key = cp.followup_state or "scheduled"
        followup_states_breakdown[st_key] = followup_states_breakdown.get(st_key, 0) + 1

    reminder_jobs_list = list(
        db.scalars(select(ReminderJob).where(ReminderJob.clinic == s.clinic))
    )
    reminder_jobs_by_status = {
        "pending": 0,
        "dispatched": 0,
        "sent": 0,
        "retrying": 0,
        "dead_letter": 0,
        "cancelled": 0,
    }
    for rj in reminder_jobs_list:
        reminder_jobs_by_status[rj.status] = reminder_jobs_by_status.get(rj.status, 0) + 1

    messages_list = list(
        db.scalars(select(Message).where(Message.mother_id.in_(mids)))
    )
    messages_by_status: dict[str, int] = {}
    flagged_messages_pending = 0
    for msg in messages_list:
        messages_by_status[msg.status] = messages_by_status.get(msg.status, 0) + 1
        if (
            msg.flagged_for_clinical_review
            and msg.clinical_review_status == "pending_clinician_review"
        ):
            flagged_messages_pending += 1

    caregivers_consented = (
        db.scalar(
            select(func.count(CaregiverConsent.id)).where(
                CaregiverConsent.clinic == s.clinic,
                CaregiverConsent.consent_granted.is_(True),
            )
        )
        or 0
    )
    contact_attempts_count = (
        db.scalar(
            select(func.count(ContactAttempt.id)).where(ContactAttempt.clinic == s.clinic)
        )
        or 0
    )

    return {
        "clinic": s.clinic,
        "registered_mothers": total_mothers,
        "consented_mothers": consented_mothers,
        "active_care_plans": active_plans,
        "upcoming_appointments": upcoming_plans,
        "overdue_plans": overdue_plans,
        "open_tasks": open_tasks,
        "messages": total_messages,
        "transport_requests": total_transport,
        "documents_total": len(docs_list),
        "documents_confirmed": docs_confirmed,
        "documents_unconfirmed": docs_unconfirmed,
        "pending_change_proposals": pending_proposals,
        "tasks_by_status": tasks_by_status,
        "tasks_by_priority": tasks_by_priority,
        "transport_by_status": transport_by_status,
        "expenses_total_paise": expenses_total_paise,
        "expenses_approved_paise": expenses_approved_paise,
        "expenses_pending_paise": expenses_pending_paise,
        "expenses_by_category": expenses_by_category,
        "staff_by_role": staff_by_role,
        "followup_states_breakdown": followup_states_breakdown,
        "reminder_jobs_by_status": reminder_jobs_by_status,
        "messages_by_status": messages_by_status,
        "flagged_messages_pending": flagged_messages_pending,
        "caregivers_consented": caregivers_consented,
        "contact_attempts_count": contact_attempts_count,
    }


# ---------------------------------------------------------------------------
# Phase 4: Durable Reminder Infrastructure, Closed-Loop State Machine,
# Signed Webhooks, Human Follow-up & Caregiver Permissions
# ---------------------------------------------------------------------------
@app.get("/api/worker/health")
def worker_and_queue_health(
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    health_data = check_worker_and_queue_health(db, s.clinic)
    health_data["messaging_providers"] = get_messaging_providers_status()
    return health_data


@app.get("/api/reminders/jobs")
def list_reminder_jobs(
    status: Optional[str] = Query(default=None),
    care_plan_id: Optional[str] = Query(default=None),
    mother_id: Optional[str] = Query(default=None),
    recipient_type: Optional[str] = Query(default=None),
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> list[dict[str, Any]]:
    stmt = select(ReminderJob).where(ReminderJob.clinic == s.clinic)
    if status:
        stmt = stmt.where(ReminderJob.status == status)
    if care_plan_id:
        stmt = stmt.where(ReminderJob.care_plan_id == care_plan_id)
    if mother_id:
        mother_for(db, s, mother_id)
        stmt = stmt.where(ReminderJob.mother_id == mother_id)
    if recipient_type:
        stmt = stmt.where(ReminderJob.recipient_type == recipient_type)
    stmt = stmt.order_by(ReminderJob.scheduled_for.asc(), ReminderJob.created_at.desc())

    mothers_map = {
        m.id: m for m in db.scalars(select(Mother).where(Mother.clinic == s.clinic))
    }
    plans_map = {
        cp.id: cp for cp in db.scalars(select(CarePlan).where(CarePlan.clinic == s.clinic))
    }
    caregivers_map = {
        cg.id: cg
        for cg in db.scalars(
            select(CaregiverConsent).where(CaregiverConsent.clinic == s.clinic)
        )
    }

    out: list[dict[str, Any]] = []
    for rj in db.scalars(stmt):
        d = row(rj)
        m = mothers_map.get(rj.mother_id)
        cp = plans_map.get(rj.care_plan_id)
        cg = caregivers_map.get(rj.caregiver_id) if rj.caregiver_id else None
        d["mother_name"] = m.name if m else ""
        d["mother_phone_masked"] = mask_phone(m.phone) if m else ""
        d["caregiver_name"] = cg.caregiver_name if cg else None
        d["visit_date"] = cp.visit_date.isoformat() if cp and cp.visit_date else None
        d["care_plan_followup_state"] = cp.followup_state if cp else None
        d["care_plan_active"] = cp.active if cp else False
        out.append(d)
    return out


@app.get("/api/reminders/outbox")
def list_transactional_outbox(
    status: Optional[str] = Query(default=None),
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> list[dict[str, Any]]:
    stmt = select(TransactionalOutbox).where(TransactionalOutbox.clinic == s.clinic)
    if status:
        stmt = stmt.where(TransactionalOutbox.status == status)
    stmt = stmt.order_by(TransactionalOutbox.created_at.desc()).limit(200)
    return [row(x) for x in db.scalars(stmt)]


@app.post("/api/reminders/schedule/{plan_id}")
def ensure_plan_reminders_scheduled(
    plan_id: str,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "doctor", "nurse", "field_coordinator")
    plan = db.get(CarePlan, plan_id)
    if not plan or plan.clinic != s.clinic:
        raise HTTPException(404, "Care plan not found in your clinic")
    if not plan.active:
        raise HTTPException(400, "Cannot schedule reminders for an inactive or superseded care plan")
    m = mother_for(db, s, plan.mother_id)
    jobs = schedule_reminders_for_care_plan(
        db, plan, m, actor_id=s.id, actor_role=normalize_role(s.role)
    )
    audit(
        db,
        s,
        "schedule_reminders",
        "care_plan",
        plan.id,
        f"jobs={len(jobs)}",
    )
    db.commit()
    return {
        "care_plan_id": plan.id,
        "scheduled_jobs_count": len(jobs),
        "jobs": [row(j) for j in jobs],
    }


@app.post("/api/reminders/worker/run")
def run_reminder_worker_cycle(
    p: WorkerRunIn = WorkerRunIn(),
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "doctor", "nurse", "field_coordinator")
    worker_res = process_outbox_and_due_jobs(
        db,
        clinic=s.clinic,
        force_due=p.force_due,
        simulate_failure=p.simulate_failure,
    )
    overdue_res = {"plans_escalated": 0, "tasks_created": 0}
    if p.evaluate_overdue:
        overdue_res = evaluate_overdue_acknowledgements(db, clinic=s.clinic)
    audit(
        db,
        s,
        "run_reminder_worker",
        "worker",
        s.clinic,
        f"sent={worker_res['jobs_sent']}; retrying={worker_res['jobs_retrying']}; dead_letter={worker_res['jobs_dead_lettered']}",
    )
    db.commit()
    return {
        **worker_res,
        **overdue_res,
    }


@app.post("/api/reminders/jobs/{jid}/retry")
def retry_dead_letter_reminder_job(
    jid: str,
    p: OperatorRetryIn = OperatorRetryIn(),
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "doctor", "nurse")
    job = db.get(ReminderJob, jid)
    if not job or job.clinic != s.clinic:
        raise HTTPException(404, "Reminder job not found in your clinic")
    if job.status not in ("dead_letter", "retrying"):
        raise HTTPException(
            400, f"Only dead_letter or retrying jobs can be operator-retried (current: {job.status})"
        )
    res = operator_retry_dead_letter_job(
        db,
        job,
        actor_id=s.id,
        actor_role=normalize_role(s.role),
        channel_override=p.channel_override,
    )
    db.commit()
    db.refresh(job)
    return {
        "job": row(job),
        "worker_result": res,
    }


@app.post("/api/reminders/jobs/{jid}/cancel")
def cancel_single_reminder_job(
    jid: str,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "doctor", "nurse")
    job = db.get(ReminderJob, jid)
    if not job or job.clinic != s.clinic:
        raise HTTPException(404, "Reminder job not found in your clinic")
    if job.status in ("sent", "cancelled"):
        raise HTTPException(400, f"Cannot cancel job in status '{job.status}'")
    job.status = "cancelled"
    job.cancelled_at = now()
    job.cancellation_reason = f"cancelled_by_staff:{s.id}"
    job.updated_at = now()
    audit(db, s, "cancel_reminder_job", "reminder_job", job.id)
    db.commit()
    return row(job)


@app.get("/api/appointments/state-machine")
def get_followup_state_machine_spec(s: Staff = Depends(who)) -> dict[str, Any]:
    return {
        "states": list(ALL_FOLLOWUP_STATES),
        "allowed_transitions": {
            k: sorted(list(v)) for k, v in ALLOWED_FOLLOWUP_TRANSITIONS.items()
        },
    }


@app.post("/api/appointments/{pid}/transition")
def transition_appointment_followup_state(
    pid: str,
    p: FollowupTransitionIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "doctor", "nurse", "field_coordinator")
    plan = db.get(CarePlan, pid)
    if not plan or plan.clinic != s.clinic:
        raise HTTPException(404, "Care plan not found in your clinic")
    mother_for(db, s, plan.mother_id)

    ok, detail = transition_care_plan_state(
        db,
        plan,
        p.target_state,
        actor_id=s.id,
        actor_role=normalize_role(s.role),
        reason=p.reason,
        allow_idempotent=True,
    )
    if not ok:
        raise HTTPException(409, detail)
    db.commit()
    out = row(plan)
    out["transition_detail"] = detail
    return out


@app.post("/api/reminders/evaluate-overdue")
def trigger_overdue_evaluation(
    as_of_iso: Optional[str] = Query(default=None),
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "doctor", "nurse", "field_coordinator")
    as_of_dt: Optional[datetime] = None
    if as_of_iso:
        try:
            normalized_iso = as_of_iso.strip().replace(" ", "+")
            if normalized_iso.endswith("Z"):
                normalized_iso = normalized_iso[:-1] + "+00:00"
            as_of_dt = datetime.fromisoformat(normalized_iso)
            if as_of_dt.tzinfo is None:
                as_of_dt = as_of_dt.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise HTTPException(422, "Invalid ISO datetime for as_of_iso") from exc
    res = evaluate_overdue_acknowledgements(db, clinic=s.clinic, as_of=as_of_dt)
    audit(
        db,
        s,
        "evaluate_overdue_acknowledgements",
        "clinic",
        s.clinic,
        f"escalated={res['plans_escalated']}; tasks_created={res['tasks_created']}",
    )
    db.commit()
    return res


# ---------------------------------------------------------------------------
# Signed Webhooks & Staff Inbox / Clinician Review
# ---------------------------------------------------------------------------
@app.get("/api/webhooks/whatsapp")
def verify_whatsapp_webhook_challenge(
    hub_mode: Optional[str] = Query(default=None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(default=None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(default=None, alias="hub.challenge"),
) -> Response:
    cur_settings = get_settings()
    if hub_mode == "subscribe" and hub_verify_token == cur_settings.whatsapp_verify_token:
        return Response(content=hub_challenge or "ok", media_type="text/plain")
    raise HTTPException(403, "Invalid WhatsApp webhook verification token")


@app.post("/api/webhooks/whatsapp")
async def receive_signed_whatsapp_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(default=None),
    db: Session = Depends(dbsession),
) -> dict[str, Any]:
    cur_settings = get_settings()
    raw_body = await request.body()
    if not verify_webhook_signature(raw_body, x_hub_signature_256, cur_settings.webhook_secret):
        raise HTTPException(
            401,
            "Invalid or missing X-Hub-Signature-256 webhook signature",
        )

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(400, "Invalid JSON webhook payload") from exc

    import hashlib as _hl

    payload_hash = _hl.sha256(raw_body).hexdigest()
    event_type = payload.get("event_type", "delivery_callback")
    event_id = str(payload.get("event_id") or f"evt.{payload_hash[:16]}")
    provider = str(payload.get("provider") or "whatsapp-cloud")

    if event_type == "inbound_message":
        res = process_inbound_reply(
            db,
            event_id=event_id,
            provider=provider,
            mother_id=payload.get("mother_id"),
            from_phone=payload.get("from_phone"),
            care_plan_id=payload.get("care_plan_id"),
            reply_text=str(payload.get("body") or payload.get("reply_text") or ""),
            raw_payload_hash=payload_hash,
        )
    else:
        res = process_delivery_callback(
            db,
            event_id=event_id,
            provider=provider,
            provider_message_id=payload.get("provider_message_id"),
            message_id=payload.get("message_id"),
            delivery_status=str(payload.get("delivery_status") or payload.get("status") or "delivered"),
            failure_code=str(payload.get("failure_code") or ""),
            failure_reason=str(payload.get("failure_reason") or ""),
            raw_payload_hash=payload_hash,
        )

    if not res.get("ok"):
        raise HTTPException(404, res.get("error", "Webhook target not found"))
    db.commit()
    return res


@app.post("/api/messages/{mid}/simulate-callback")
def simulate_message_delivery_callback(
    mid: str,
    p: SimulateCallbackIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "doctor", "nurse", "field_coordinator")
    msg = db.get(Message, mid)
    if not msg or msg.clinic != s.clinic:
        raise HTTPException(404, "Message not found in your clinic")
    res = process_delivery_callback(
        db,
        event_id=p.event_id,
        provider=msg.provider or "local-simulator",
        message_id=msg.id,
        provider_message_id=msg.provider_message_id,
        delivery_status=p.delivery_status,
        failure_code=p.failure_code,
        failure_reason=p.failure_reason,
    )
    if not res.get("ok"):
        raise HTTPException(400, res.get("error", "Failed to process callback"))
    db.commit()
    return res


@app.get("/api/messages/inbox")
def list_staff_inbox_messages(
    flagged_only: bool = Query(default=False),
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> list[dict[str, Any]]:
    mothers_map = {
        m.id: m.name for m in db.scalars(select(Mother).where(Mother.clinic == s.clinic))
    }
    if not mothers_map:
        return []
    stmt = select(Message).where(
        Message.clinic == s.clinic,
        Message.direction == "inbound",
    )
    if flagged_only:
        stmt = stmt.where(Message.flagged_for_clinical_review.is_(True))
    stmt = stmt.order_by(Message.sent_at.desc())

    out: list[dict[str, Any]] = []
    for msg in db.scalars(stmt):
        d = row(msg)
        d["mother_name"] = mothers_map.get(msg.mother_id, "")
        out.append(d)
    return out


@app.patch("/api/messages/{mid}/review")
def review_flagged_message(
    mid: str,
    p: ClinicianMessageReviewIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    # Healthcare boundary: Only licensed clinicians (doctors/nurses) may review flagged patient messages
    permitted(s, "doctor", "nurse")
    msg = db.get(Message, mid)
    if not msg or msg.clinic != s.clinic:
        raise HTTPException(404, "Message not found in your clinic")
    mother_for(db, s, msg.mother_id)

    msg.clinical_review_status = "reviewed_by_clinician"
    msg.clinical_review_note = p.clinical_review_note.strip()
    msg.reviewed_by = s.id
    msg.reviewed_at = now()

    if p.resolve_related_task:
        related_tasks = list(
            db.scalars(
                select(Task).where(
                    Task.mother_id == msg.mother_id,
                    Task.clinic == s.clinic,
                    Task.category.in_(("flagged_message_review", "patient_reply")),
                    Task.status.in_(("open", "in_progress")),
                )
            )
        )
        for t in related_tasks:
            t.status = "resolved"
            t.completed_at = now()
            t.completion_notes = f"Clinician protocol review completed by {s.name}: {p.clinical_review_note}"

    audit(
        db,
        s,
        "clinician_review_flagged_message",
        "message",
        msg.id,
        p.clinical_review_note[:160],
    )
    db.commit()
    return row(msg)


# ---------------------------------------------------------------------------
# Human Follow-Up Contact Attempts & Supervisor Escalation
# ---------------------------------------------------------------------------
@app.get("/api/tasks/{tid}/contact-attempts")
def list_task_contact_attempts(
    tid: str,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> list[dict[str, Any]]:
    t = db.get(Task, tid)
    if not t or t.clinic != s.clinic:
        raise HTTPException(404, "Task not found in your clinic")
    mother_for(db, s, t.mother_id)
    staff_map = {
        st.id: st.name for st in db.scalars(select(Staff).where(Staff.clinic == s.clinic))
    }
    out: list[dict[str, Any]] = []
    for ca in db.scalars(
        select(ContactAttempt)
        .where(ContactAttempt.task_id == tid, ContactAttempt.clinic == s.clinic)
        .order_by(ContactAttempt.attempted_at.desc())
    ):
        d = row(ca)
        d["staff_name"] = staff_map.get(ca.staff_id, ca.staff_id)
        out.append(d)
    return out


@app.post("/api/tasks/{tid}/contact-attempts")
def record_task_contact_attempt(
    tid: str,
    p: ContactAttemptIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "doctor", "nurse", "field_coordinator", "asha")
    t = db.get(Task, tid)
    if not t or t.clinic != s.clinic:
        raise HTTPException(404, "Task not found in your clinic")
    m = mother_for(db, s, t.mother_id)

    ca = ContactAttempt(
        task_id=t.id,
        mother_id=m.id,
        care_plan_id=t.care_plan_id,
        clinic=s.clinic,
        staff_id=s.id,
        staff_role=normalize_role(s.role),
        channel=p.channel,
        outcome=p.outcome,
        notes=p.notes.strip(),
    )
    db.add(ca)
    db.flush()

    if t.status == "open":
        t.status = "in_progress"

    plan: Optional[CarePlan] = None
    if t.care_plan_id:
        plan = db.get(CarePlan, t.care_plan_id)
    if not plan:
        plan = db.scalar(
            select(CarePlan).where(CarePlan.mother_id == m.id, CarePlan.active.is_(True))
        )

    if plan:
        if plan.followup_state in ("no_acknowledgement", "contact_required", "staff_assigned"):
            transition_care_plan_state(
                db,
                plan,
                "contact_attempted",
                actor_id=s.id,
                actor_role=normalize_role(s.role),
                reason=f"Contact attempt via {p.channel}: {p.outcome}",
            )
        if p.outcome == "reached_confirmed":
            transition_care_plan_state(
                db,
                plan,
                "acknowledged",
                actor_id=s.id,
                actor_role=normalize_role(s.role),
                reason="Confirmed via human follow-up outreach",
            )
            t.status = "resolved"
            t.completed_at = now()
            t.completion_notes = p.notes or "Patient reached and confirmed appointment."
        elif p.outcome == "unreachable":
            transition_care_plan_state(
                db,
                plan,
                "unreachable",
                actor_id=s.id,
                actor_role=normalize_role(s.role),
                reason=p.notes or "Marked unreachable after follow-up attempts",
            )

    audit(
        db,
        s,
        "record_contact_attempt",
        "task",
        t.id,
        f"channel={p.channel}; outcome={p.outcome}",
    )
    db.commit()
    out = row(ca)
    out["task_status"] = t.status
    out["care_plan_followup_state"] = plan.followup_state if plan else None
    return out


@app.post("/api/tasks/{tid}/escalate")
def escalate_task_to_supervisor(
    tid: str,
    p: TaskEscalateIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "doctor", "nurse", "field_coordinator", "asha")
    t = db.get(Task, tid)
    if not t or t.clinic != s.clinic:
        raise HTTPException(404, "Task not found in your clinic")
    mother_for(db, s, t.mother_id)

    supervisor_id = p.escalated_to
    if supervisor_id:
        sup = db.get(Staff, supervisor_id)
        if not sup or sup.clinic != s.clinic or normalize_role(sup.role) not in ("admin", "doctor", "nurse"):
            raise HTTPException(400, "Invalid supervisor target in your clinic")
    else:
        sup = db.scalar(
            select(Staff)
            .where(
                Staff.clinic == s.clinic,
                Staff.is_active.is_(True),
                Staff.role.in_(("admin", "doctor")),
            )
            .order_by(Staff.role.asc())
        )
        supervisor_id = sup.id if sup else s.id

    t.priority = "urgent"
    t.escalated_to = supervisor_id
    t.escalated_at = now()
    t.escalation_reason = p.escalation_reason.strip()
    t.assigned_to = supervisor_id or t.assigned_to

    audit(
        db,
        s,
        "escalate_task_to_supervisor",
        "task",
        t.id,
        f"escalated_to={supervisor_id}; reason={t.escalation_reason}",
    )
    db.commit()
    return row(t)


# ---------------------------------------------------------------------------
# Caregiver Permissions & Privacy-Guarded Administrative Reminders
# ---------------------------------------------------------------------------
@app.get("/api/mothers/{mid}/caregivers")
def list_mother_caregivers(
    mid: str,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> list[dict[str, Any]]:
    mother_for(db, s, mid)
    return [
        row(cg)
        for cg in db.scalars(
            select(CaregiverConsent)
            .where(CaregiverConsent.mother_id == mid, CaregiverConsent.clinic == s.clinic)
            .order_by(CaregiverConsent.updated_at.desc())
        )
    ]


@app.post("/api/mothers/{mid}/caregivers")
def add_mother_caregiver(
    mid: str,
    p: CaregiverIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "doctor", "nurse", "field_coordinator")
    m = mother_for(db, s, mid)
    ts = now()
    cg = CaregiverConsent(
        mother_id=m.id,
        clinic=s.clinic,
        caregiver_name=p.caregiver_name.strip(),
        caregiver_phone=p.caregiver_phone,
        relationship_type=p.relationship_type,
        language=p.language,
        consent_granted=p.consent_granted,
        allow_admin_reminders=p.allow_admin_reminders,
        granted_at=ts if p.consent_granted else None,
        revoked_at=None if p.consent_granted else ts,
        recorded_by=s.id,
        updated_at=ts,
    )
    db.add(cg)
    db.flush()

    if cg.consent_granted and cg.allow_admin_reminders:
        active_plan = db.scalar(
            select(CarePlan).where(CarePlan.mother_id == m.id, CarePlan.active.is_(True))
        )
        if active_plan:
            schedule_reminders_for_care_plan(
                db, active_plan, m, actor_id=s.id, actor_role=normalize_role(s.role)
            )

    audit(
        db,
        s,
        "register_caregiver_consent",
        "caregiver_consent",
        cg.id,
        f"mother={m.id}; consent={cg.consent_granted}; admin_reminders={cg.allow_admin_reminders}",
    )
    db.commit()
    return row(cg)


@app.patch("/api/caregivers/{cid}")
def update_caregiver_consent(
    cid: str,
    p: CaregiverUpdateIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "doctor", "nurse", "field_coordinator")
    cg = db.get(CaregiverConsent, cid)
    if not cg or cg.clinic != s.clinic:
        raise HTTPException(404, "Caregiver consent record not found in your clinic")
    m = mother_for(db, s, cg.mother_id)
    ts = now()

    updates = p.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(cg, k, v)
    cg.updated_at = ts

    cancelled_jobs = 0
    if not cg.consent_granted or not cg.allow_admin_reminders:
        cg.revoked_at = ts
        cancelled_jobs = cancel_obsolete_reminders(
            db,
            clinic=s.clinic,
            caregiver_id=cg.id,
            reason="caregiver_permission_revoked",
            actor_id=s.id,
            actor_role=normalize_role(s.role),
        )
    else:
        cg.granted_at = cg.granted_at or ts
        cg.revoked_at = None
        active_plan = db.scalar(
            select(CarePlan).where(CarePlan.mother_id == m.id, CarePlan.active.is_(True))
        )
        if active_plan:
            schedule_reminders_for_care_plan(
                db, active_plan, m, actor_id=s.id, actor_role=normalize_role(s.role)
            )

    audit(
        db,
        s,
        "update_caregiver_consent",
        "caregiver_consent",
        cg.id,
        f"consent={cg.consent_granted}; admin_reminders={cg.allow_admin_reminders}; cancelled_jobs={cancelled_jobs}",
    )
    db.commit()
    out = row(cg)
    out["cancelled_reminder_jobs"] = cancelled_jobs
    return out


@app.post("/api/caregivers/{cid}/send-reminder")
def send_caregiver_admin_reminder(
    cid: str,
    p: CaregiverMessageIn = CaregiverMessageIn(),
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "doctor", "nurse", "field_coordinator")
    cg = db.get(CaregiverConsent, cid)
    if not cg or cg.clinic != s.clinic:
        raise HTTPException(404, "Caregiver consent record not found in your clinic")
    m = mother_for(db, s, cg.mother_id)

    if not cg.consent_granted or not cg.allow_admin_reminders:
        raise HTTPException(
            403,
            "Caregiver permission is not granted or has been revoked. Cannot send caregiver reminders.",
        )

    plan = db.scalar(
        select(CarePlan).where(CarePlan.mother_id == m.id, CarePlan.active.is_(True))
    )
    if not plan:
        raise HTTPException(400, "No active doctor-authorised care plan for this mother")

    body = (
        p.custom_body.strip()
        if p.custom_body and p.custom_body.strip()
        else render_approved_template(
            "janani_caregiver_admin_reminder_v1",
            mother_name=m.name,
            clinic=s.clinic,
            visit_date=plan.visit_date,
            caregiver_name=cg.caregiver_name,
        )
    )

    safe, violation_reason = validate_privacy_safe_content(body, recipient_type="caregiver")
    if not safe:
        raise HTTPException(403, violation_reason)

    cfg = get_or_create_clinic_comm_config(db, s.clinic)
    adapter = get_messaging_adapter(cfg.default_channel)
    idem_key = f"manual-cg:{cg.id}:{plan.id}:{int(now().timestamp())}"
    send_res = adapter.send_template_message(
        to_phone=cg.caregiver_phone,
        template_name="janani_caregiver_admin_reminder_v1",
        language_code=cg.language or "en",
        rendered_body=body,
        idempotency_key=idem_key,
        recipient_type="caregiver",
    )
    if not send_res.ok:
        raise HTTPException(502, f"Messaging provider failed: {send_res.failure_reason}")

    msg = Message(
        mother_id=m.id,
        care_plan_id=plan.id,
        clinic=s.clinic,
        direction="outbound",
        recipient_type="caregiver",
        recipient_phone_masked=mask_phone(cg.caregiver_phone),
        template_name="janani_caregiver_admin_reminder_v1",
        body=body,
        status="sent",
        delivery_status_rank=DELIVERY_STATUS_RANKS["sent"],
        provider=send_res.provider,
        provider_message_id=send_res.provider_message_id,
        idempotency_key=idem_key,
    )
    db.add(msg)
    db.flush()
    audit(db, s, "send_caregiver_reminder", "message", msg.id, f"caregiver={cg.id}")
    db.commit()
    return row(msg)


# ---------------------------------------------------------------------------
# Clinic Communication & Scheduling Configuration
# ---------------------------------------------------------------------------
@app.get("/api/settings/communication")
def get_clinic_comm_settings(
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    cfg = get_or_create_clinic_comm_config(db, s.clinic)
    db.commit()
    d = row(cfg)
    d["reminder_offsets_hours"] = parse_offsets_hours(cfg)
    d["approved_templates"] = APPROVED_TEMPLATES
    d["providers_status"] = get_messaging_providers_status()
    return d


@app.put("/api/settings/communication")
def update_clinic_comm_settings(
    p: ClinicCommConfigIn,
    db: Session = Depends(dbsession),
    s: Staff = Depends(who),
) -> dict[str, Any]:
    permitted(s, "admin", "doctor")
    cfg = get_or_create_clinic_comm_config(db, s.clinic)
    cfg.timezone = p.timezone
    cfg.reminder_offsets_hours_json = json.dumps(sorted({int(x) for x in p.reminder_offsets_hours}))
    cfg.ack_deadline_hours = p.ack_deadline_hours
    cfg.default_channel = p.default_channel
    cfg.whatsapp_template_en = p.whatsapp_template_en
    cfg.whatsapp_template_te = p.whatsapp_template_te
    cfg.whatsapp_template_hi = p.whatsapp_template_hi
    cfg.max_retry_attempts = p.max_retry_attempts
    cfg.retry_base_seconds = p.retry_base_seconds
    cfg.enable_caregiver_reminders = p.enable_caregiver_reminders
    cfg.updated_by = s.id
    cfg.updated_at = now()
    audit(
        db,
        s,
        "update_comm_settings",
        "clinic_comm_config",
        s.clinic,
        f"channel={p.default_channel}; offsets={cfg.reminder_offsets_hours_json}",
    )
    db.commit()
    d = row(cfg)
    d["reminder_offsets_hours"] = parse_offsets_hours(cfg)
    d["approved_templates"] = APPROVED_TEMPLATES
    d["providers_status"] = get_messaging_providers_status()
    return d


# ---------------------------------------------------------------------------
# Phase 5: Workforce, Field Visits, Hospital Partnerships, Transport & Governance
# ---------------------------------------------------------------------------
from app.phase5_routes import register_phase5_routes
from app.phase6_routes import register_phase6_routes

register_phase5_routes(app, dbsession, who, permitted, audit, row, mother_for)
register_phase6_routes(app, dbsession, who, permitted, audit, row, mother_for)


# ---------------------------------------------------------------------------
# Frontend SPA Serving
# ---------------------------------------------------------------------------
@app.get("/")
def home() -> FileResponse:
    dist_index = FRONTEND_DIST / "index.html"
    if dist_index.is_file():
        return FileResponse(dist_index)
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/{full_path:path}")
def spa_fallback(full_path: str) -> FileResponse:
    if full_path.startswith("api/") or full_path.startswith("static/"):
        raise HTTPException(404, "Not found")
    candidate = FRONTEND_DIST / full_path
    if candidate.is_file():
        return FileResponse(candidate)
    dist_index = FRONTEND_DIST / "index.html"
    if dist_index.is_file():
        return FileResponse(dist_index)
    return FileResponse(STATIC_DIR / "index.html")
