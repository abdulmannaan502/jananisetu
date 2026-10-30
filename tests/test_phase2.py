"""Comprehensive Phase 2 automated test suite for JananiSetu.

Covers:
1. Authentication (bcrypt hashing, JWT Bearer tokens, login, registration, password updates)
2. Role-Based Access Control (admin, doctor, nurse, field_coordinator)
3. Strict Cross-Clinic Data Isolation (mothers, plans, tasks, transport, expenses, documents, events, analytics)
4. Patient registration, validation, consent lifecycle, and ANC document OCR confirmation
5. Doctor-authorised care plans, appointment scheduling, and missed-visit follow-up automation
6. Task assignment & completion, transport coordination, expense management, and data migration
"""
from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
import sys
import tempfile

from fastapi.testclient import TestClient
from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app
from app.security import create_access_token, hash_password, verify_password
from scripts.migrate_sqlite_to_postgres import migrate_data

client = TestClient(app)


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register_clinic_and_roles(clinic_slug: str) -> dict[str, dict]:
    """Register an admin for a new clinic and create doctor, nurse, and field_coordinator."""
    client.cookies.clear()
    res_admin = client.post(
        "/api/auth/register",
        json={
            "name": f"Admin {clinic_slug}",
            "email": f"admin@{clinic_slug}.org",
            "password": "Password@123",
            "role": "admin",
            "clinic": clinic_slug,
            "phone": "9100000001",
        },
    )
    assert res_admin.status_code == 200, res_admin.text
    admin_data = res_admin.json()
    admin_token = admin_data["access_token"]

    roles: dict[str, dict] = {
        "admin": {"token": admin_token, "staff": admin_data["staff"]},
    }

    for role in ("doctor", "nurse", "field_coordinator"):
        r = client.post(
            "/api/staff",
            headers=auth_headers(admin_token),
            json={
                "name": f"{role.title()} {clinic_slug}",
                "email": f"{role}@{clinic_slug}.org",
                "password": "Password@123",
                "role": role,
                "phone": "9100000009",
            },
        )
        assert r.status_code == 200, r.text
        login_res = client.post(
            "/api/auth/login",
            json={
                "identifier": f"{role}@{clinic_slug}.org",
                "password": "Password@123",
            },
        )
        assert login_res.status_code == 200, login_res.text
        roles[role] = {
            "token": login_res.json()["access_token"],
            "staff": login_res.json()["staff"],
        }

    client.cookies.clear()
    return roles


def test_authentication_and_jwt_lifecycle():
    # 1. Password hashing & verification unit checks
    pw_hash = hash_password("Secret Care 2026!")
    assert pw_hash != "Secret Care 2026!"
    assert verify_password("Secret Care 2026!", pw_hash) is True
    assert verify_password("WrongPassword", pw_hash) is False

    # 2. Unauthenticated access to protected endpoints must fail with 401
    assert client.get("/api/mothers").status_code == 401
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.jwt.token"}).status_code == 401

    # 3. Expired token must be rejected with 401
    expired_token = create_access_token(
        subject="nonexistent",
        role="admin",
        clinic="auth-test-clinic",
        expires_delta=timedelta(seconds=-10),
    )
    assert client.get("/api/auth/me", headers=auth_headers(expired_token)).status_code == 401

    # 4. Register clinic admin & verify login + /api/auth/me
    roles = register_clinic_and_roles("auth-clinic-1")
    admin_token = roles["admin"]["token"]
    me_res = client.get("/api/auth/me", headers=auth_headers(admin_token))
    assert me_res.status_code == 200
    assert me_res.json()["clinic"] == "auth-clinic-1"
    assert me_res.json()["role"] == "admin"

    # 5. Once clinic has an admin, unauthenticated staff creation or registration for that clinic is blocked (401)
    unauth_staff = client.post(
        "/api/staff",
        json={"name": "Rogue Admin", "role": "admin", "clinic": "auth-clinic-1"},
    )
    assert unauth_staff.status_code == 401

    # 6. Wrong password login returns 401
    bad_login = client.post(
        "/api/auth/login",
        json={"identifier": "admin@auth-clinic-1.org", "password": "WrongPassword"},
    )
    assert bad_login.status_code == 401

    # 7. Change password workflow
    fc_token = roles["field_coordinator"]["token"]
    bad_pw_change = client.post(
        "/api/auth/change-password",
        headers=auth_headers(fc_token),
        json={"current_password": "wrong", "new_password": "NewPassword@2026"},
    )
    assert bad_pw_change.status_code == 400

    good_pw_change = client.post(
        "/api/auth/change-password",
        headers=auth_headers(fc_token),
        json={"current_password": "Password@123", "new_password": "NewPassword@2026"},
    )
    assert good_pw_change.status_code == 200

    relogin = client.post(
        "/api/auth/login",
        json={"identifier": "field_coordinator@auth-clinic-1.org", "password": "NewPassword@2026"},
    )
    assert relogin.status_code == 200

    # 8. Deactivated staff member cannot log in or use existing token
    fc_id = roles["field_coordinator"]["staff"]["id"]
    deact = client.patch(
        f"/api/staff/{fc_id}",
        headers=auth_headers(admin_token),
        json={"is_active": False},
    )
    assert deact.status_code == 200
    assert client.get("/api/auth/me", headers=auth_headers(fc_token)).status_code == 401
    assert (
        client.post(
            "/api/auth/login",
            json={"identifier": "field_coordinator@auth-clinic-1.org", "password": "NewPassword@2026"},
        ).status_code
        == 403
    )


def test_role_based_access_control():
    roles = register_clinic_and_roles("rbac-clinic")
    admin_tok = roles["admin"]["token"]
    doc_tok = roles["doctor"]["token"]
    nurse_tok = roles["nurse"]["token"]
    fc_tok = roles["field_coordinator"]["token"]

    # Non-admins cannot create staff
    for tok in (doc_tok, nurse_tok, fc_tok):
        r = client.post(
            "/api/staff",
            headers=auth_headers(tok),
            json={"name": "Unauthorized Staff", "role": "nurse"},
        )
        assert r.status_code == 403

    # Field coordinator can register a patient
    mother_res = client.post(
        "/api/mothers",
        headers=auth_headers(fc_tok),
        json={
            "name": "Lakshmi Synthetic",
            "phone": "9876543210",
            "language": "te",
            "consent": True,
            "age": 25,
        },
    )
    assert mother_res.status_code == 200
    mid = mother_res.json()["id"]

    # ONLY doctor can create/approve CarePlans (admin, nurse, field_coordinator must get 403)
    for tok in (admin_tok, nurse_tok, fc_tok):
        plan_attempt = client.post(
            f"/api/mothers/{mid}/plans",
            headers=auth_headers(tok),
            json={"visit_date": "2026-12-01", "note": "Attempted by non-doctor"},
        )
        assert plan_attempt.status_code == 403

    doc_plan = client.post(
        f"/api/mothers/{mid}/plans",
        headers=auth_headers(doc_tok),
        json={"visit_date": "2026-12-01", "visit_type": "anc_checkup", "note": "Doctor approved ANC visit"},
    )
    assert doc_plan.status_code == 200

    # ONLY admin can manage expenses (doctor, nurse, field_coordinator get 403)
    for tok in (doc_tok, nurse_tok, fc_tok):
        assert (
            client.post(
                "/api/expenses",
                headers=auth_headers(tok),
                json={"category": "travel", "amount_rupees": 250},
            ).status_code
            == 403
        )
        assert client.get("/api/expenses", headers=auth_headers(tok)).status_code == 403

    # Audit events accessible to admin and doctor, forbidden to nurse and field_coordinator
    assert client.get("/api/events", headers=auth_headers(admin_tok)).status_code == 200
    assert client.get("/api/events", headers=auth_headers(doc_tok)).status_code == 200
    assert client.get("/api/events", headers=auth_headers(nurse_tok)).status_code == 403
    assert client.get("/api/events", headers=auth_headers(fc_tok)).status_code == 403


def test_cross_clinic_data_isolation():
    clinic_a = register_clinic_and_roles("clinic-alpha")
    clinic_b = register_clinic_and_roles("clinic-beta")

    a_admin = clinic_a["admin"]["token"]
    a_doc = clinic_a["doctor"]["token"]
    a_nurse = clinic_a["nurse"]["token"]

    b_admin = clinic_b["admin"]["token"]
    b_doc = clinic_b["doctor"]["token"]
    b_nurse = clinic_b["nurse"]["token"]
    b_fc_id = clinic_b["field_coordinator"]["staff"]["id"]

    # Create patient, care plan, task, transport, expense in Clinic Alpha
    m_alpha = client.post(
        "/api/mothers",
        headers=auth_headers(a_nurse),
        json={"name": "Alpha Mother", "phone": "9900000001", "consent": True, "language": "en"},
    ).json()
    mid_a = m_alpha["id"]

    plan_a = client.post(
        f"/api/mothers/{mid_a}/plans",
        headers=auth_headers(a_doc),
        json={"visit_date": "2026-11-20", "note": "Alpha plan"},
    ).json()

    task_a = client.post(
        "/api/tasks",
        headers=auth_headers(a_nurse),
        json={"mother_id": mid_a, "category": "contact_attempt", "detail": "Alpha task"},
    ).json()

    trans_a = client.post(
        "/api/transport",
        headers=auth_headers(a_nurse),
        json={
            "mother_id": mid_a,
            "date": "2026-11-20",
            "from_location": "Alpha Village",
            "destination": "Alpha PHC",
        },
    ).json()

    exp_a = client.post(
        "/api/expenses",
        headers=auth_headers(a_admin),
        json={"category": "diagnostics", "amount_rupees": 1200, "description": "Alpha lab kit"},
    ).json()

    # Verify Clinic Beta cannot see or mutate ANY Clinic Alpha records
    assert client.get("/api/mothers", headers=auth_headers(b_nurse)).json() == []
    assert client.get(f"/api/mothers/{mid_a}", headers=auth_headers(b_nurse)).status_code == 404
    assert (
        client.patch(
            f"/api/mothers/{mid_a}/consent",
            headers=auth_headers(b_nurse),
            json={"consent": False},
        ).status_code
        == 404
    )
    assert client.get(f"/api/mothers/{mid_a}/plans", headers=auth_headers(b_doc)).status_code == 404
    assert (
        client.post(
            f"/api/mothers/{mid_a}/plans",
            headers=auth_headers(b_doc),
            json={"visit_date": "2026-12-10"},
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/appointments/{plan_a['id']}",
            headers=auth_headers(b_nurse),
            json={"appointment_status": "completed"},
        ).status_code
        == 404
    )

    # Tasks isolation + cross-clinic assignee rejection
    assert client.get("/api/tasks", headers=auth_headers(b_nurse)).json() == []
    assert (
        client.patch(
            f"/api/tasks/{task_a['id']}",
            headers=auth_headers(b_nurse),
            json={"status": "resolved"},
        ).status_code
        == 404
    )
    cross_assign = client.post(
        "/api/tasks",
        headers=auth_headers(a_nurse),
        json={"mother_id": mid_a, "category": "other", "assigned_to": b_fc_id},
    )
    assert cross_assign.status_code == 400

    # Transport isolation
    assert client.get("/api/transport", headers=auth_headers(b_nurse)).json() == []
    assert (
        client.patch(
            f"/api/transport/{trans_a['id']}",
            headers=auth_headers(b_nurse),
            json={"status": "completed"},
        ).status_code
        == 404
    )

    # Expenses isolation (Fixed v0.1 vulnerability!)
    assert client.get("/api/expenses", headers=auth_headers(b_admin)).json() == []
    assert (
        client.patch(
            f"/api/expenses/{exp_a['id']}",
            headers=auth_headers(b_admin),
            json={"approved": True},
        ).status_code
        == 404
    )

    # Audit events & analytics isolation (Fixed v0.1 vulnerability!)
    b_events = client.get("/api/events", headers=auth_headers(b_admin)).json()
    assert all(ev["clinic"] == "clinic-beta" for ev in b_events)
    assert all(ev["entity_id"] != mid_a for ev in b_events)

    b_analytics = client.get("/api/analytics", headers=auth_headers(b_admin)).json()
    assert b_analytics["registered_mothers"] == 0
    assert b_analytics["expenses_total_paise"] == 0


def test_patient_documents_appointments_tasks_transport_expenses():
    roles = register_clinic_and_roles("workflow-clinic")
    admin_tok = roles["admin"]["token"]
    doc_tok = roles["doctor"]["token"]
    nurse_tok = roles["nurse"]["token"]
    fc_tok = roles["field_coordinator"]["token"]
    fc_id = roles["field_coordinator"]["staff"]["id"]

    # 1. Input validation checks
    bad_phone = client.post(
        "/api/mothers",
        headers=auth_headers(nurse_tok),
        json={"name": "Invalid Phone", "phone": "abc-not-a-phone"},
    )
    assert bad_phone.status_code == 422

    # 2. Register mother with full details
    today = date.today()
    m_res = client.post(
        "/api/mothers",
        headers=auth_headers(nurse_tok),
        json={
            "name": "Padmavathi Synthetic",
            "phone": "+919848012345",
            "language": "te",
            "consent": True,
            "age": 26,
            "lmp": (today - timedelta(days=140)).isoformat(),
            "edd": (today + timedelta(days=140)).isoformat(),
            "address": "Block 7, Suryapet",
            "notes": "Synthetic second-trimester registration",
        },
    )
    assert m_res.status_code == 200
    mid = m_res.json()["id"]

    # 3. ANC Document upload & human confirmation
    img_buf = BytesIO()
    Image.new("RGB", (120, 80), color=(255, 255, 255)).save(img_buf, format="PNG")
    img_bytes = img_buf.getvalue()

    up_res = client.post(
        f"/api/mothers/{mid}/documents",
        headers=auth_headers(fc_tok),
        files={"file": ("anc_card.png", img_bytes, "image/png")},
    )
    assert up_res.status_code == 200
    doc_id = up_res.json()["id"]
    assert up_res.json()["confirmed"] is False

    # Field coordinator cannot confirm clinical OCR extraction (403)
    assert (
        client.patch(
            f"/api/documents/{doc_id}/confirm",
            headers=auth_headers(fc_tok),
            json={"corrected_text": "Attempted by FC"},
        ).status_code
        == 403
    )

    # Nurse confirms transcription with structured fields
    conf_res = client.patch(
        f"/api/documents/{doc_id}/confirm",
        headers=auth_headers(nurse_tok),
        json={
            "corrected_text": "ANC Visit #2 verified. Hb: 11.4 g/dL, TT1 administered.",
            "structured_fields": {"anc_visit_number": 2, "facility": "PHC Suryapet"},
        },
    )
    assert conf_res.status_code == 200
    assert conf_res.json()["confirmed"] is True

    # Download document image
    dl_res = client.get(f"/api/documents/{doc_id}/file", headers=auth_headers(nurse_tok))
    assert dl_res.status_code == 200
    assert dl_res.headers["content-type"] == "image/png"

    # 4. Doctor-authorised care plan & missed appointment follow-up automation
    plan_res = client.post(
        f"/api/mothers/{mid}/plans",
        headers=auth_headers(doc_tok),
        json={
            "visit_date": (today - timedelta(days=1)).isoformat(),
            "visit_type": "anc_checkup",
            "note": "Check blood pressure and iron supplementation compliance.",
        },
    )
    assert plan_res.status_code == 200
    pid = plan_res.json()["id"]

    appts = client.get("/api/appointments?overdue_only=true", headers=auth_headers(nurse_tok)).json()
    assert len(appts) == 1
    assert appts[0]["id"] == pid
    assert appts[0]["is_overdue"] is True

    # Mark appointment as missed and auto-create follow-up task
    missed_res = client.patch(
        f"/api/appointments/{pid}",
        headers=auth_headers(nurse_tok),
        json={
            "appointment_status": "missed",
            "follow_up_notes": "Patient could not travel due to rain; schedule home outreach.",
            "create_followup_task": True,
        },
    )
    assert missed_res.status_code == 200
    assert missed_res.json()["appointment_status"] == "missed"

    # 5. Task assignment and completion by field coordinator
    tasks_list = client.get("/api/tasks", headers=auth_headers(fc_tok)).json()
    assert len(tasks_list) == 1
    tid = tasks_list[0]["id"]
    assert tasks_list[0]["category"] == "missed_visit"

    assign_res = client.patch(
        f"/api/tasks/{tid}",
        headers=auth_headers(nurse_tok),
        json={"status": "in_progress", "assigned_to": fc_id, "priority": "urgent"},
    )
    assert assign_res.status_code == 200
    assert assign_res.json()["assigned_to"] == fc_id

    complete_res = client.patch(
        f"/api/tasks/{tid}",
        headers=auth_headers(fc_tok),
        json={"status": "resolved", "completion_notes": "Visited home; rescheduled transport for Friday."},
    )
    assert complete_res.status_code == 200
    assert complete_res.json()["status"] == "resolved"
    assert complete_res.json()["completed_at"] is not None

    # 6. Transport coordination
    tr_res = client.post(
        "/api/transport",
        headers=auth_headers(fc_tok),
        json={
            "mother_id": mid,
            "date": (today + timedelta(days=2)).isoformat(),
            "pickup_time": "08:30",
            "from_location": "Block 7, Suryapet",
            "destination": "PHC Suryapet",
            "partner": "Janani Express Van #4",
        },
    )
    assert tr_res.status_code == 200
    tr_id = tr_res.json()["id"]

    tr_upd = client.patch(
        f"/api/transport/{tr_id}",
        headers=auth_headers(fc_tok),
        json={"status": "completed", "vehicle_notes": "Completed safe drop-off at PHC"},
    )
    assert tr_upd.status_code == 200
    assert tr_upd.json()["status"] == "completed"

    # 7. Operational expenditure & analytics verification
    e1 = client.post(
        "/api/expenses",
        headers=auth_headers(admin_tok),
        json={"category": "transport", "amount_rupees": 600, "description": "Van voucher", "receipt_ref": "R-01"},
    ).json()
    e2 = client.post(
        "/api/expenses",
        headers=auth_headers(admin_tok),
        json={"category": "diagnostics", "amount_rupees": 400, "description": "Strips", "receipt_ref": "R-02"},
    ).json()
    client.patch(f"/api/expenses/{e1['id']}", headers=auth_headers(admin_tok), json={"approved": True})

    stats = client.get("/api/analytics", headers=auth_headers(admin_tok)).json()
    assert stats["registered_mothers"] == 1
    assert stats["documents_confirmed"] == 1
    assert stats["tasks_by_status"]["resolved"] == 1
    assert stats["transport_by_status"]["completed"] == 1
    assert stats["expenses_total_paise"] == 100_000
    assert stats["expenses_approved_paise"] == 60_000
    assert stats["expenses_pending_paise"] == 40_000


def test_data_migration_utility():
    tmp_src = Path(tempfile.mkdtemp(prefix="janani-mig-src-")) / "src.db"
    tmp_tgt = Path(tempfile.mkdtemp(prefix="janani-mig-tgt-")) / "tgt.db"
    src_url = f"sqlite:///{tmp_src}"
    tgt_url = f"sqlite:///{tmp_tgt}"

    counts = migrate_data(src_url, tgt_url)
    assert "staff" in counts and "mothers" in counts and "expenses" in counts


def test_health_and_frontend_serving():
    h = client.get("/api/health")
    assert h.status_code == 200
    body = h.json()
    assert body["status"] == "ok"
    assert body["clinical_advice"] is False
    assert body["autonomous_diagnosis"] is False
    assert body["risk_scoring"] is False

    home_res = client.get("/")
    assert home_res.status_code == 200
    assert "JananiSetu" in home_res.text

