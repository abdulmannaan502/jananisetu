"""Phase 4 Automated Test Suite: Durable Reminders, Closed-Loop State Machine, Signed Webhooks,
Human Follow-Up Escalation, Caregiver Permissions, Cross-Clinic Isolation & Worker Recovery.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import sys
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.main import SessionLocal, app
from app.models import ReminderJob, TransactionalOutbox


def _sign_webhook(payload_dict: dict) -> tuple[bytes, str]:
    raw = json.dumps(payload_dict).encode("utf-8")
    secret = get_settings().webhook_secret
    digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return raw, f"sha256={digest}"


def _setup_two_clinics(c: TestClient) -> dict:
    c.post("/api/auth/seed-demo")

    def login_token(email: str) -> str:
        r = c.post("/api/auth/login", json={"identifier": email, "password": "Janani@2026"})
        assert r.status_code == 200, r.text
        return r.json()["access_token"]

    return {
        "admin1": {"Authorization": f"Bearer {login_token('admin@nalgonda.janani.org')}"},
        "doc1": {"Authorization": f"Bearer {login_token('doctor@nalgonda.janani.org')}"},
        "nurse1": {"Authorization": f"Bearer {login_token('nurse@nalgonda.janani.org')}"},
        "fc1": {"Authorization": f"Bearer {login_token('coordinator@nalgonda.janani.org')}"},
        "admin2": {"Authorization": f"Bearer {login_token('admin@warangal.janani.org')}"},
        "doc2": {"Authorization": f"Bearer {login_token('doctor@warangal.janani.org')}"},
    }


def test_01_consent_enforcement_and_opt_out_cancellation():
    """Verify reminders are blocked without consent and pending jobs are immediately cancelled on withdrawal."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    # Create mother WITHOUT consent
    m_res = c.post(
        "/api/mothers",
        headers=hdrs["nurse1"],
        json={
            "name": "Kavitha NoConsent",
            "phone": "9848011101",
            "language": "te",
            "consent": False,
        },
    )
    assert m_res.status_code == 200
    mid = m_res.json()["id"]

    # Doctor authorises care plan -> 0 mother reminder jobs should be scheduled while consent=False
    visit_dt = (date.today() + timedelta(days=7)).isoformat()
    plan_res = c.post(
        f"/api/mothers/{mid}/plans",
        headers=hdrs["doc1"],
        json={"visit_date": visit_dt, "visit_type": "anc_checkup", "note": "ANC checkup"},
    )
    assert plan_res.status_code == 200
    assert plan_res.json()["scheduled_reminder_jobs_count"] == 0

    # Grant consent -> automatically schedules reminder jobs for active doctor-authorised plan
    grant_res = c.patch(
        f"/api/mothers/{mid}/consent",
        headers=hdrs["nurse1"],
        json={"consent": True},
    )
    assert grant_res.status_code == 200

    jobs_res = c.get(f"/api/reminders/jobs?mother_id={mid}", headers=hdrs["nurse1"])
    assert jobs_res.status_code == 200
    pending_jobs = [j for j in jobs_res.json() if j["status"] == "pending"]
    assert len(pending_jobs) == 3  # -48h, -24h, 0h offsets

    # Withdraw consent -> immediately cancels all pending reminder jobs
    revoke_res = c.patch(
        f"/api/mothers/{mid}/consent",
        headers=hdrs["nurse1"],
        json={"consent": False},
    )
    assert revoke_res.status_code == 200
    assert revoke_res.json()["cancelled_reminder_jobs"] == 3

    jobs_after = c.get(f"/api/reminders/jobs?mother_id={mid}", headers=hdrs["nurse1"]).json()
    assert all(j["status"] == "cancelled" for j in jobs_after)
    assert all(j["cancellation_reason"] == "mother_consent_withdrawn" for j in jobs_after)


def test_02_reminder_creation_from_doctor_approved_plan_with_ist_offsets():
    """Verify persistent reminder jobs are scheduled in Asia/Kolkata using only doctor-approved dates."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    # Configure custom clinic offsets [-72, -24, 0]
    cfg_res = c.put(
        "/api/settings/communication",
        headers=hdrs["admin1"],
        json={
            "timezone": "Asia/Kolkata",
            "reminder_offsets_hours": [-72, -24, 0],
            "ack_deadline_hours": 12,
            "default_channel": "local-simulator",
            "whatsapp_template_en": "janani_anc_reminder_en",
            "whatsapp_template_te": "janani_anc_reminder_te",
            "whatsapp_template_hi": "janani_anc_reminder_hi",
            "max_retry_attempts": 3,
            "retry_base_seconds": 60,
            "enable_caregiver_reminders": True,
        },
    )
    assert cfg_res.status_code == 200
    assert cfg_res.json()["reminder_offsets_hours"] == [-72, -24, 0]

    m = c.post(
        "/api/mothers",
        headers=hdrs["nurse1"],
        json={"name": "Padmavathi IST", "phone": "9848011102", "language": "te", "consent": True},
    ).json()

    # Non-doctor cannot create care plan
    forb = c.post(
        f"/api/mothers/{m['id']}/plans",
        headers=hdrs["nurse1"],
        json={"visit_date": "2026-12-15", "visit_type": "anc_checkup"},
    )
    assert forb.status_code == 403

    # Doctor approves care plan
    plan = c.post(
        f"/api/mothers/{m['id']}/plans",
        headers=hdrs["doc1"],
        json={"visit_date": "2026-12-15", "visit_type": "anc_checkup", "note": "Doctor authorised"},
    ).json()
    assert plan["scheduled_reminder_jobs_count"] == 3
    assert plan["followup_state"] == "scheduled"

    jobs = c.get(f"/api/reminders/jobs?care_plan_id={plan['id']}", headers=hdrs["doc1"]).json()
    assert len(jobs) == 3
    offsets = sorted(j["offset_hours"] for j in jobs)
    assert offsets == [-72, -24, 0]
    assert all(j["timezone_name"] == "Asia/Kolkata" for j in jobs)


def test_03_automatic_cancellation_when_plan_is_superseded():
    """Verify obsolete reminders are automatically cancelled when a doctor authorises a new CarePlan."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    m = c.post(
        "/api/mothers",
        headers=hdrs["nurse1"],
        json={"name": "Renuka Supersede", "phone": "9848011103", "language": "en", "consent": True},
    ).json()

    plan_v1 = c.post(
        f"/api/mothers/{m['id']}/plans",
        headers=hdrs["doc1"],
        json={"visit_date": "2026-12-10", "visit_type": "anc_checkup", "note": "v1 plan"},
    ).json()
    assert plan_v1["version"] == 1

    # Doctor supersedes v1 with v2
    plan_v2 = c.post(
        f"/api/mothers/{m['id']}/plans",
        headers=hdrs["doc1"],
        json={"visit_date": "2026-12-20", "visit_type": "anc_checkup", "note": "v2 rescheduled"},
    ).json()
    assert plan_v2["version"] == 2
    assert plan_v2["cancelled_obsolete_jobs"] >= 3

    v1_jobs = c.get(f"/api/reminders/jobs?care_plan_id={plan_v1['id']}", headers=hdrs["doc1"]).json()
    assert len(v1_jobs) >= 3
    assert all(j["status"] == "cancelled" for j in v1_jobs)
    assert all("superseded_by_plan_v2" in j["cancellation_reason"] for j in v1_jobs)

    v2_jobs = c.get(f"/api/reminders/jobs?care_plan_id={plan_v2['id']}", headers=hdrs["doc1"]).json()
    assert len(v2_jobs) >= 3
    assert all(j["status"] == "pending" for j in v2_jobs)


def test_04_idempotent_scheduling_and_transactional_outbox():
    """Verify calling schedule multiple times for the same CarePlan is strictly idempotent."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    m = c.post(
        "/api/mothers",
        headers=hdrs["nurse1"],
        json={"name": "Anitha Idempotent", "phone": "9848011104", "language": "hi", "consent": True},
    ).json()
    plan = c.post(
        f"/api/mothers/{m['id']}/plans",
        headers=hdrs["doc1"],
        json={"visit_date": "2026-12-22", "visit_type": "anc_checkup"},
    ).json()

    # Re-trigger scheduling twice
    r1 = c.post(f"/api/reminders/schedule/{plan['id']}", headers=hdrs["nurse1"])
    r2 = c.post(f"/api/reminders/schedule/{plan['id']}", headers=hdrs["nurse1"])
    assert r1.status_code == 200
    assert r2.status_code == 200

    jobs = c.get(f"/api/reminders/jobs?care_plan_id={plan['id']}", headers=hdrs["nurse1"]).json()
    idem_keys = [j["idempotency_key"] for j in jobs]
    assert len(jobs) == len(set(idem_keys)) == 3

    outbox = c.get("/api/reminders/outbox", headers=hdrs["admin1"]).json()
    plan_outbox = [o for o in outbox if any(k in o["idempotency_key"] for k in idem_keys)]
    assert len(plan_outbox) == 3


def test_05_exponential_backoff_retry_and_dead_letter_with_operator_retry():
    """Verify transient provider failures trigger exponential backoff retries, dead-letter after max_attempts, and operator recovery."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    # Phone ending in 0000 simulates transient provider failure unless overridden, or we pass simulate_failure=True
    m = c.post(
        "/api/mothers",
        headers=hdrs["nurse1"],
        json={"name": "Swathi RetryTest", "phone": "9848011105", "language": "te", "consent": True},
    ).json()
    plan = c.post(
        f"/api/mothers/{m['id']}/plans",
        headers=hdrs["doc1"],
        json={"visit_date": (date.today() + timedelta(days=2)).isoformat(), "visit_type": "anc_checkup"},
    ).json()

    # Cancel 2 of the 3 jobs so we test retry lifecycle on a single job deterministically
    jobs = c.get(f"/api/reminders/jobs?care_plan_id={plan['id']}", headers=hdrs["admin1"]).json()
    target_job_id = jobs[0]["id"]
    for extra in jobs[1:]:
        c.post(f"/api/reminders/jobs/{extra['id']}/cancel", headers=hdrs["admin1"])

    # Attempt 1 (simulate_failure=True) -> status becomes 'retrying', attempts=1
    w1 = c.post(
        "/api/reminders/worker/run",
        headers=hdrs["admin1"],
        json={"force_due": True, "simulate_failure": True},
    )
    assert w1.status_code == 200
    j1 = [j for j in c.get(f"/api/reminders/jobs?care_plan_id={plan['id']}", headers=hdrs["admin1"]).json() if j["id"] == target_job_id][0]
    assert j1["status"] == "retrying"
    assert j1["attempts"] == 1
    assert j1["next_retry_at"] is not None

    # Attempt 2 (simulate_failure=True) -> status='retrying', attempts=2
    c.post(
        "/api/reminders/worker/run",
        headers=hdrs["admin1"],
        json={"force_due": True, "simulate_failure": True},
    )
    j2 = [j for j in c.get(f"/api/reminders/jobs?care_plan_id={plan['id']}", headers=hdrs["admin1"]).json() if j["id"] == target_job_id][0]
    assert j2["status"] == "retrying"
    assert j2["attempts"] == 2

    # Attempt 3 (simulate_failure=True) -> reaches max_attempts (3) -> status='dead_letter'
    c.post(
        "/api/reminders/worker/run",
        headers=hdrs["admin1"],
        json={"force_due": True, "simulate_failure": True},
    )
    j3 = [j for j in c.get(f"/api/reminders/jobs?care_plan_id={plan['id']}", headers=hdrs["admin1"]).json() if j["id"] == target_job_id][0]
    assert j3["status"] == "dead_letter"
    assert j3["attempts"] == 3
    assert j3["dead_lettered_at"] is not None

    # CarePlan state should reflect delivery_failed
    cp_after_fail = [p for p in c.get(f"/api/mothers/{m['id']}/plans", headers=hdrs["admin1"]).json() if p["id"] == plan["id"]][0]
    assert cp_after_fail["followup_state"] == "delivery_failed"

    # Operator retries the dead-letter job -> succeeds and transitions CarePlan to reminder_sent
    retry_res = c.post(
        f"/api/reminders/jobs/{target_job_id}/retry",
        headers=hdrs["admin1"],
        json={"channel_override": "local-simulator"},
    )
    assert retry_res.status_code == 200
    assert retry_res.json()["job"]["status"] == "sent"
    assert retry_res.json()["job"]["message_id"] is not None

    cp_recovered = [p for p in c.get(f"/api/mothers/{m['id']}/plans", headers=hdrs["admin1"]).json() if p["id"] == plan["id"]][0]
    assert cp_recovered["followup_state"] == "reminder_sent"


def test_06_signed_webhook_verification_hmac_sha256():
    """Verify unsigned or invalidly signed webhook requests are rejected with 401."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    payload = {
        "event_id": "evt-sig-test-001",
        "event_type": "delivery_callback",
        "provider": "whatsapp-cloud",
        "delivery_status": "delivered",
    }
    raw_bytes = json.dumps(payload).encode("utf-8")

    # 1. Missing signature header -> 401
    r_missing = c.post(
        "/api/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json"},
    )
    assert r_missing.status_code == 401

    # 2. Tampered signature header -> 401
    r_bad = c.post(
        "/api/webhooks/whatsapp",
        content=raw_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=0000000000000000000000000000000000000000000000000000000000000000",
        },
    )
    assert r_bad.status_code == 401


def test_07_duplicate_webhook_event_idempotency():
    """Verify duplicate signed webhook events with the same event_id are processed idempotently."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    m = c.post(
        "/api/mothers",
        headers=hdrs["nurse1"],
        json={"name": "Deepika Webhook", "phone": "9848011107", "language": "te", "consent": True},
    ).json()
    plan = c.post(
        f"/api/mothers/{m['id']}/plans",
        headers=hdrs["doc1"],
        json={"visit_date": (date.today() + timedelta(days=4)).isoformat(), "visit_type": "anc_checkup"},
    ).json()

    c.post("/api/reminders/worker/run", headers=hdrs["admin1"], json={"force_due": True})
    jobs = c.get(f"/api/reminders/jobs?care_plan_id={plan['id']}", headers=hdrs["admin1"]).json()
    msg_id = [j["message_id"] for j in jobs if j["message_id"]][0]

    dup_event_id = f"evt-dup-check-{uuid.uuid4().hex[:8]}"
    payload = {
        "event_id": dup_event_id,
        "event_type": "delivery_callback",
        "provider": "whatsapp-cloud",
        "message_id": msg_id,
        "delivery_status": "delivered",
    }
    raw_bytes, sig = _sign_webhook(payload)

    res1 = c.post(
        "/api/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res1.status_code == 200
    assert res1.json()["duplicate_ignored"] is False

    # Replay exact same webhook event_id
    res2 = c.post(
        "/api/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert res2.status_code == 200
    assert res2.json()["duplicate_ignored"] is True


def test_08_out_of_order_delivery_status_callbacks_never_downgrade():
    """Verify out-of-order callbacks (e.g. 'sent' arriving after 'delivered' or 'read') never downgrade state."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)
    run_tag = uuid.uuid4().hex[:8]

    m = c.post(
        "/api/mothers",
        headers=hdrs["nurse1"],
        json={"name": "Haritha Ordering", "phone": "9848011108", "language": "en", "consent": True},
    ).json()
    plan = c.post(
        f"/api/mothers/{m['id']}/plans",
        headers=hdrs["doc1"],
        json={"visit_date": (date.today() + timedelta(days=3)).isoformat(), "visit_type": "anc_checkup"},
    ).json()

    c.post("/api/reminders/worker/run", headers=hdrs["admin1"], json={"force_due": True})
    jobs = c.get(f"/api/reminders/jobs?care_plan_id={plan['id']}", headers=hdrs["admin1"]).json()
    msg_id = [j["message_id"] for j in jobs if j["message_id"]][0]

    # 1. 'delivered' arrives first
    cb1 = c.post(
        f"/api/messages/{msg_id}/simulate-callback",
        headers=hdrs["admin1"],
        json={"event_id": f"evt-order-delivered-{run_tag}", "delivery_status": "delivered"},
    )
    assert cb1.status_code == 200
    assert cb1.json()["message_status"] == "delivered"
    assert cb1.json()["status_updated"] is True

    # 2. Late out-of-order 'sent' callback arrives after 'delivered' -> must NOT downgrade!
    cb2 = c.post(
        f"/api/messages/{msg_id}/simulate-callback",
        headers=hdrs["admin1"],
        json={"event_id": f"evt-order-late-sent-{run_tag}", "delivery_status": "sent"},
    )
    assert cb2.status_code == 200
    assert cb2.json()["message_status"] == "delivered"
    assert cb2.json()["status_updated"] is False


def test_09_patient_acknowledgement_and_closed_loop_distinct_stages():
    """Verify Scheduled -> Reminder Sent -> Delivered -> Acknowledged -> Visit Confirmed -> Closed are distinct."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)
    run_tag = uuid.uuid4().hex[:8]

    m = c.post(
        "/api/mothers",
        headers=hdrs["nurse1"],
        json={"name": "Madhavi ClosedLoop", "phone": "9848011109", "language": "te", "consent": True},
    ).json()
    plan = c.post(
        f"/api/mothers/{m['id']}/plans",
        headers=hdrs["doc1"],
        json={"visit_date": (date.today() + timedelta(days=2)).isoformat(), "visit_type": "anc_checkup"},
    ).json()
    pid = plan["id"]
    assert plan["followup_state"] == "scheduled"

    # Stage 2: Reminder Sent
    c.post("/api/reminders/worker/run", headers=hdrs["admin1"], json={"force_due": True})
    cp = [p for p in c.get(f"/api/mothers/{m['id']}/plans", headers=hdrs["nurse1"]).json() if p["id"] == pid][0]
    assert cp["followup_state"] == "reminder_sent"

    # Stage 3: Delivered (does NOT imply Acknowledged)
    jobs = c.get(f"/api/reminders/jobs?care_plan_id={pid}", headers=hdrs["nurse1"]).json()
    msg_id = [j["message_id"] for j in jobs if j["message_id"]][0]
    c.post(
        f"/api/messages/{msg_id}/simulate-callback",
        headers=hdrs["nurse1"],
        json={"event_id": f"evt-cl-deliv-{run_tag}", "delivery_status": "delivered"},
    )
    cp = [p for p in c.get(f"/api/mothers/{m['id']}/plans", headers=hdrs["nurse1"]).json() if p["id"] == pid][0]
    assert cp["followup_state"] == "delivered"
    assert cp["acknowledged_at"] is None

    # Stage 4: Patient replies 'YES' via signed inbound webhook -> Acknowledged (does NOT imply Visit Confirmed)
    inbound_payload = {
        "event_id": f"evt-cl-ack-{run_tag}",
        "event_type": "inbound_message",
        "provider": "whatsapp-cloud",
        "mother_id": m["id"],
        "care_plan_id": pid,
        "body": "YES",
    }
    raw_bytes, sig = _sign_webhook(inbound_payload)
    in_res = c.post(
        "/api/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert in_res.status_code == 200
    assert in_res.json()["care_plan_followup_state"] == "acknowledged"

    cp = [p for p in c.get(f"/api/mothers/{m['id']}/plans", headers=hdrs["nurse1"]).json() if p["id"] == pid][0]
    assert cp["followup_state"] == "acknowledged"
    assert cp["visit_confirmed_at"] is None

    # Stage 5: Nurse confirms actual clinic visit attendance -> Visit Confirmed (does NOT auto-close)
    vc_res = c.post(
        f"/api/appointments/{pid}/transition",
        headers=hdrs["nurse1"],
        json={"target_state": "visit_confirmed", "reason": "Mother attended clinic ANC checkup"},
    )
    assert vc_res.status_code == 200
    assert vc_res.json()["followup_state"] == "visit_confirmed"
    assert vc_res.json()["closed_at"] is None

    # Stage 6: Doctor/Nurse closes the loop -> Closed
    cl_res = c.post(
        f"/api/appointments/{pid}/transition",
        headers=hdrs["doc1"],
        json={"target_state": "closed", "reason": "Documentation and post-visit follow-up completed"},
    )
    assert cl_res.status_code == 200
    assert cl_res.json()["followup_state"] == "closed"
    assert cl_res.json()["closed_at"] is not None


def test_10_unacknowledged_reminder_escalation_creates_clinic_followup_task():
    """Verify overdue unacknowledged reminders transition to staff_assigned and create a follow-up Task."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    m = c.post(
        "/api/mothers",
        headers=hdrs["nurse1"],
        json={"name": "Sunitha OverdueAck", "phone": "9848011110", "language": "te", "consent": True},
    ).json()
    plan = c.post(
        f"/api/mothers/{m['id']}/plans",
        headers=hdrs["doc1"],
        json={"visit_date": (date.today() + timedelta(days=1)).isoformat(), "visit_type": "anc_checkup"},
    ).json()
    pid = plan["id"]

    # Send reminder
    c.post("/api/reminders/worker/run", headers=hdrs["admin1"], json={"force_due": True})

    # Simulate operational deadline passing (+24h in the future)
    future_iso = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    esc = c.post(
        f"/api/reminders/evaluate-overdue?as_of_iso={future_iso}",
        headers=hdrs["admin1"],
    )
    assert esc.status_code == 200
    assert esc.json()["plans_escalated"] >= 1
    assert esc.json()["tasks_created"] >= 1

    cp = [p for p in c.get(f"/api/mothers/{m['id']}/plans", headers=hdrs["nurse1"]).json() if p["id"] == pid][0]
    assert cp["followup_state"] == "staff_assigned"

    tasks = c.get("/api/tasks", headers=hdrs["fc1"]).json()
    mother_tasks = [t for t in tasks if t["mother_id"] == m["id"] and t["category"] == "unacknowledged_reminder_followup"]
    assert len(mother_tasks) == 1
    assert mother_tasks[0]["assigned_to"] != ""


def test_11_staff_contact_attempt_logging_and_supervisor_escalation():
    """Verify recording contact attempts updates task/plan state and supports supervisor escalation."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    m = c.post(
        "/api/mothers",
        headers=hdrs["nurse1"],
        json={"name": "Vasundhara Contact", "phone": "9848011111", "language": "te", "consent": True},
    ).json()
    plan = c.post(
        f"/api/mothers/{m['id']}/plans",
        headers=hdrs["doc1"],
        json={"visit_date": (date.today() + timedelta(days=1)).isoformat(), "visit_type": "anc_checkup"},
    ).json()
    c.post("/api/reminders/worker/run", headers=hdrs["admin1"], json={"force_due": True})
    future_iso = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    c.post(f"/api/reminders/evaluate-overdue?as_of_iso={future_iso}", headers=hdrs["admin1"])

    tasks = [t for t in c.get("/api/tasks", headers=hdrs["fc1"]).json() if t["mother_id"] == m["id"]]
    tid = tasks[0]["id"]

    # 1. Field coordinator logs first contact attempt (no_answer)
    ca1 = c.post(
        f"/api/tasks/{tid}/contact-attempts",
        headers=hdrs["fc1"],
        json={"channel": "phone_call", "outcome": "no_answer", "notes": "Phone rang out; will retry in evening."},
    )
    assert ca1.status_code == 200
    assert ca1.json()["task_status"] == "in_progress"
    assert ca1.json()["care_plan_followup_state"] == "contact_attempted"

    # 2. Escalate task to supervisor
    esc_res = c.post(
        f"/api/tasks/{tid}/escalate",
        headers=hdrs["fc1"],
        json={"escalation_reason": "Two unanswered phone calls; needs ANM/MO supervisor review."},
    )
    assert esc_res.status_code == 200
    assert esc_res.json()["priority"] == "urgent"
    assert esc_res.json()["escalated_to"] is not None

    # 3. Nurse contacts mother on home visit and confirms attendance
    ca2 = c.post(
        f"/api/tasks/{tid}/contact-attempts",
        headers=hdrs["nurse1"],
        json={"channel": "home_visit", "outcome": "reached_confirmed", "notes": "Met mother at home; confirmed visit."},
    )
    assert ca2.status_code == 200
    assert ca2.json()["task_status"] == "resolved"
    assert ca2.json()["care_plan_followup_state"] == "acknowledged"

    history = c.get(f"/api/tasks/{tid}/contact-attempts", headers=hdrs["nurse1"]).json()
    assert len(history) == 2


def test_12_invalid_state_transition_rejection():
    """Verify invalid closed-loop state transitions are rejected with 409 Conflict."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    m = c.post(
        "/api/mothers",
        headers=hdrs["nurse1"],
        json={"name": "Lalitha StateGuard", "phone": "9848011112", "language": "en", "consent": True},
    ).json()
    plan = c.post(
        f"/api/mothers/{m['id']}/plans",
        headers=hdrs["doc1"],
        json={"visit_date": (date.today() + timedelta(days=5)).isoformat(), "visit_type": "anc_checkup"},
    ).json()
    pid = plan["id"]

    # Cannot jump directly from 'scheduled' to 'closed' or 'visit_confirmed'
    bad1 = c.post(
        f"/api/appointments/{pid}/transition",
        headers=hdrs["doc1"],
        json={"target_state": "closed", "reason": "Premature close attempt"},
    )
    assert bad1.status_code == 409

    bad2 = c.post(
        f"/api/appointments/{pid}/transition",
        headers=hdrs["doc1"],
        json={"target_state": "visit_confirmed", "reason": "Premature confirmation without reminder/ack"},
    )
    assert bad2.status_code == 409


def test_13_caregiver_permission_enforcement_and_privacy_guard():
    """Verify caregiver permissions are separate, revocable, and block any clinical/ANC scan disclosure."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    m = c.post(
        "/api/mothers",
        headers=hdrs["nurse1"],
        json={"name": "Geetha CaregiverTest", "phone": "9848011113", "language": "te", "consent": True},
    ).json()
    plan = c.post(
        f"/api/mothers/{m['id']}/plans",
        headers=hdrs["doc1"],
        json={"visit_date": (date.today() + timedelta(days=6)).isoformat(), "visit_type": "anc_checkup"},
    ).json()

    # Add caregiver with explicit permission
    cg_res = c.post(
        f"/api/mothers/{m['id']}/caregivers",
        headers=hdrs["nurse1"],
        json={
            "caregiver_name": "Ramesh (Spouse)",
            "caregiver_phone": "9848099913",
            "relationship_type": "spouse",
            "language": "te",
            "consent_granted": True,
            "allow_admin_reminders": True,
        },
    )
    assert cg_res.status_code == 200
    cg_id = cg_res.json()["id"]

    # Verify caregiver reminder job was scheduled
    cg_jobs = c.get(
        f"/api/reminders/jobs?care_plan_id={plan['id']}&recipient_type=caregiver",
        headers=hdrs["nurse1"],
    ).json()
    assert len(cg_jobs) == 1
    assert cg_jobs[0]["status"] == "pending"

    # Attempt to send clinical/scan information to caregiver -> blocked by privacy guard (403)
    leak_attempt = c.post(
        f"/api/caregivers/{cg_id}/send-reminder",
        headers=hdrs["nurse1"],
        json={"custom_body": "Caregiver update: patient hemoglobin level is low and ANC scan shows anemia."},
    )
    assert leak_attempt.status_code == 403

    # Send permitted administrative reminder to caregiver -> succeeds (200)
    ok_send = c.post(
        f"/api/caregivers/{cg_id}/send-reminder",
        headers=hdrs["nurse1"],
        json={},
    )
    assert ok_send.status_code == 200
    assert ok_send.json()["recipient_type"] == "caregiver"

    # Revoke caregiver consent -> cancels pending caregiver reminder jobs and blocks further messages
    rev_res = c.patch(
        f"/api/caregivers/{cg_id}",
        headers=hdrs["nurse1"],
        json={"consent_granted": False},
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["cancelled_reminder_jobs"] == 1

    blocked_send = c.post(f"/api/caregivers/{cg_id}/send-reminder", headers=hdrs["nurse1"], json={})
    assert blocked_send.status_code == 403


def test_14_cross_clinic_isolation_across_reminders_messages_tasks_caregivers():
    """Verify staff from Clinic B (warangal-clinic) cannot access or mutate Clinic A's Phase 4 resources."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    m = c.post(
        "/api/mothers",
        headers=hdrs["nurse1"],
        json={"name": "Nalgonda Isolated Mother", "phone": "9848011114", "language": "te", "consent": True},
    ).json()
    plan = c.post(
        f"/api/mothers/{m['id']}/plans",
        headers=hdrs["doc1"],
        json={"visit_date": (date.today() + timedelta(days=4)).isoformat(), "visit_type": "anc_checkup"},
    ).json()
    cg = c.post(
        f"/api/mothers/{m['id']}/caregivers",
        headers=hdrs["nurse1"],
        json={"caregiver_name": "Kiran", "caregiver_phone": "9848099914", "relationship_type": "spouse"},
    ).json()
    task = c.post(
        "/api/tasks",
        headers=hdrs["nurse1"],
        json={"mother_id": m["id"], "category": "contact_attempt", "priority": "high"},
    ).json()

    jobs_clinic1 = c.get(f"/api/reminders/jobs?care_plan_id={plan['id']}", headers=hdrs["admin1"]).json()
    jid = jobs_clinic1[0]["id"]

    # Clinic 2 cannot view or cancel Clinic 1's reminder jobs
    c2_jobs = c.get("/api/reminders/jobs", headers=hdrs["admin2"]).json()
    assert all(j["clinic"] == "warangal-clinic" for j in c2_jobs)
    assert c.post(f"/api/reminders/jobs/{jid}/cancel", headers=hdrs["admin2"]).status_code == 404

    # Clinic 2 cannot transition Clinic 1's appointment state
    assert (
        c.post(
            f"/api/appointments/{plan['id']}/transition",
            headers=hdrs["doc2"],
            json={"target_state": "reminder_sent"},
        ).status_code
        == 404
    )

    # Clinic 2 cannot log contact attempts or escalate Clinic 1's task
    assert (
        c.post(
            f"/api/tasks/{task['id']}/contact-attempts",
            headers=hdrs["admin2"],
            json={"channel": "phone_call", "outcome": "no_answer"},
        ).status_code
        == 404
    )
    assert (
        c.post(
            f"/api/tasks/{task['id']}/escalate",
            headers=hdrs["admin2"],
            json={"escalation_reason": "cross clinic"},
        ).status_code
        == 404
    )

    # Clinic 2 cannot modify or message Clinic 1's caregiver
    assert c.patch(f"/api/caregivers/{cg['id']}", headers=hdrs["admin2"], json={"consent_granted": False}).status_code == 404
    assert c.post(f"/api/caregivers/{cg['id']}/send-reminder", headers=hdrs["admin2"], json={}).status_code == 404


def test_15_worker_restart_recovery_from_transactional_outbox_and_clinician_review():
    """Verify transactional outbox recovery after simulated worker crash and clinician review of flagged replies."""
    c = TestClient(app)
    hdrs = _setup_two_clinics(c)

    m = c.post(
        "/api/mothers",
        headers=hdrs["nurse1"],
        json={"name": "jyothi Recovery", "phone": "9848011115", "language": "te", "consent": True},
    ).json()
    plan = c.post(
        f"/api/mothers/{m['id']}/plans",
        headers=hdrs["doc1"],
        json={"visit_date": (date.today() + timedelta(days=3)).isoformat(), "visit_type": "anc_checkup"},
    ).json()

    # Verify TransactionalOutbox entries exist in 'pending' state before worker runs
    with SessionLocal() as db:
        pending_outbox = list(
            db.scalars(
                select(TransactionalOutbox).where(
                    TransactionalOutbox.clinic == "demo-clinic",
                    TransactionalOutbox.status == "pending",
                )
            )
        )
        assert len(pending_outbox) >= 3

    # Worker starts up after restart and recovers all pending outbox entries & jobs
    run_res = c.post("/api/reminders/worker/run", headers=hdrs["admin1"], json={"force_due": True})
    assert run_res.status_code == 200
    assert run_res.json()["outbox_dispatched"] >= 3
    assert run_res.json()["jobs_sent"] >= 3

    # Patient sends a non-standard reply asking for help -> preserved verbatim and flagged for clinician review
    inbound_payload = {
        "event_id": f"evt-flagged-reply-{uuid.uuid4().hex[:8]}",
        "event_type": "inbound_message",
        "provider": "whatsapp-cloud",
        "mother_id": m["id"],
        "care_plan_id": plan["id"],
        "body": "I have swelling in my feet and need to speak with the doctor before Friday.",
    }
    raw_bytes, sig = _sign_webhook(inbound_payload)
    in_res = c.post(
        "/api/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert in_res.status_code == 200
    assert in_res.json()["flagged_for_clinical_review"] is True
    msg_id = in_res.json()["message_id"]

    # Field coordinator cannot perform clinical review of flagged message (403)
    forb_rev = c.patch(
        f"/api/messages/{msg_id}/review",
        headers=hdrs["fc1"],
        json={"clinical_review_note": "Tried to review"},
    )
    assert forb_rev.status_code == 403

    # Licensed doctor reviews the flagged message under clinic protocol
    doc_rev = c.patch(
        f"/api/messages/{msg_id}/review",
        headers=hdrs["doc1"],
        json={
            "clinical_review_note": "Contacted patient per clinic protocol; advised immediate PHC visit for evaluation.",
            "resolve_related_task": True,
        },
    )
    assert doc_rev.status_code == 200
    assert doc_rev.json()["clinical_review_status"] == "reviewed_by_clinician"
    assert doc_rev.json()["reviewed_by"] is not None