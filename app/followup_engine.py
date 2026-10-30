"""Phase 4: Durable reminder scheduling, transactional outbox, closed-loop state machine, and human follow-up engine."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.messaging import (
    DELIVERY_STATUS_RANKS,
    get_messaging_adapter,
    mask_phone,
    render_approved_template,
)
from app.models import (
    CaregiverConsent,
    CarePlan,
    ClinicCommConfig,
    ContactAttempt,
    Event,
    Message,
    Mother,
    ReminderJob,
    Staff,
    Task,
    TransactionalOutbox,
    WebhookEvent,
    now,
)

try:
    IST = ZoneInfo("Asia/Kolkata")
except ZoneInfoNotFoundError:
    IST = timezone(timedelta(hours=5, minutes=30))


ALL_FOLLOWUP_STATES: tuple[str, ...] = (
    "scheduled",
    "reminder_sent",
    "delivered",
    "acknowledged",
    "visit_confirmed",
    "closed",
    # Alternative operational states
    "delivery_failed",
    "no_acknowledgement",
    "missed_appointment",
    "contact_required",
    "staff_assigned",
    "contact_attempted",
    "rescheduled_by_authorised_staff",
    "resolved",
    "unreachable",
)

# Explicit closed-loop state machine transition rules.
# Delivery, acknowledgement, attendance (visit_confirmed), and closure are strictly distinct.
ALLOWED_FOLLOWUP_TRANSITIONS: dict[str, set[str]] = {
    "scheduled": {
        "reminder_sent",
        "delivery_failed",
        "no_acknowledgement",
        "contact_required",
        "missed_appointment",
        "rescheduled_by_authorised_staff",
    },
    "reminder_sent": {
        "delivered",
        "acknowledged",
        "delivery_failed",
        "no_acknowledgement",
        "contact_required",
        "staff_assigned",
        "missed_appointment",
        "rescheduled_by_authorised_staff",
    },
    "delivered": {
        "acknowledged",
        "no_acknowledgement",
        "contact_required",
        "staff_assigned",
        "missed_appointment",
        "rescheduled_by_authorised_staff",
    },
    "acknowledged": {
        "visit_confirmed",
        "missed_appointment",
        "contact_required",
        "rescheduled_by_authorised_staff",
    },
    "visit_confirmed": {
        "closed",
        "resolved",
    },
    "delivery_failed": {
        "reminder_sent",
        "delivered",
        "contact_required",
        "staff_assigned",
        "unreachable",
        "rescheduled_by_authorised_staff",
    },
    "no_acknowledgement": {
        "acknowledged",
        "contact_required",
        "staff_assigned",
        "contact_attempted",
        "missed_appointment",
        "rescheduled_by_authorised_staff",
    },
    "missed_appointment": {
        "contact_required",
        "staff_assigned",
        "contact_attempted",
        "rescheduled_by_authorised_staff",
        "unreachable",
        "resolved",
    },
    "contact_required": {
        "staff_assigned",
        "contact_attempted",
        "acknowledged",
        "visit_confirmed",
        "rescheduled_by_authorised_staff",
        "unreachable",
        "resolved",
    },
    "staff_assigned": {
        "contact_attempted",
        "acknowledged",
        "visit_confirmed",
        "rescheduled_by_authorised_staff",
        "unreachable",
        "resolved",
    },
    "contact_attempted": {
        "contact_attempted",
        "acknowledged",
        "visit_confirmed",
        "rescheduled_by_authorised_staff",
        "unreachable",
        "resolved",
    },
    "rescheduled_by_authorised_staff": {
        "closed",
        "resolved",
        "scheduled",
    },
    "unreachable": {
        "contact_attempted",
        "rescheduled_by_authorised_staff",
        "resolved",
        "closed",
    },
    "resolved": {
        "closed",
    },
    "closed": set(),
}


def get_or_create_clinic_comm_config(db: Session, clinic: str) -> ClinicCommConfig:
    cfg = db.get(ClinicCommConfig, clinic)
    if not cfg:
        cfg = ClinicCommConfig(
            clinic=clinic,
            timezone="Asia/Kolkata",
            reminder_offsets_hours_json="[-48, -24, 0]",
            ack_deadline_hours=12,
            default_channel="local-simulator",
            whatsapp_template_en="janani_anc_reminder_en",
            whatsapp_template_te="janani_anc_reminder_te",
            whatsapp_template_hi="janani_anc_reminder_hi",
            max_retry_attempts=3,
            retry_base_seconds=60,
            enable_caregiver_reminders=True,
        )
        db.add(cfg)
        db.flush()
    return cfg


def parse_offsets_hours(cfg: ClinicCommConfig) -> list[int]:
    try:
        vals = json.loads(cfg.reminder_offsets_hours_json or "[-48, -24, 0]")
        if isinstance(vals, list) and vals:
            return sorted({int(x) for x in vals})
    except Exception:
        pass
    return [-48, -24, 0]


def compute_scheduled_datetime_ist(visit_date: date, offset_hours: int) -> datetime:
    """Compute reminder timestamp in India Standard Time (Asia/Kolkata) relative to 09:00 IST on visit_date."""
    anchor_ist = datetime.combine(visit_date, time(9, 0, 0), tzinfo=IST)
    target_ist = anchor_ist + timedelta(hours=offset_hours)
    return target_ist.astimezone(timezone.utc)


def select_template_for_language(cfg: ClinicCommConfig, language: str, recipient_type: str = "mother") -> str:
    if recipient_type == "caregiver":
        return "janani_caregiver_admin_reminder_v1"
    lang = (language or "te").strip().lower()
    if lang == "te":
        return cfg.whatsapp_template_te or "janani_anc_reminder_te"
    if lang == "hi":
        return cfg.whatsapp_template_hi or "janani_anc_reminder_hi"
    return cfg.whatsapp_template_en or "janani_anc_reminder_en"


def transition_care_plan_state(
    db: Session,
    plan: CarePlan,
    target_state: str,
    *,
    actor_id: str,
    actor_role: str,
    reason: str = "",
    allow_idempotent: bool = True,
) -> tuple[bool, str]:
    """Validate and apply a closed-loop follow-up state transition on a CarePlan."""
    current = (plan.followup_state or "scheduled").strip()
    target = target_state.strip()

    if target not in ALL_FOLLOWUP_STATES:
        return False, f"Unknown follow-up state '{target}'."

    if current == target:
        if allow_idempotent:
            return True, f"Idempotent no-op: already in state '{current}'."
        return False, f"Care plan is already in state '{current}'."

    allowed = ALLOWED_FOLLOWUP_TRANSITIONS.get(current, set())
    if target not in allowed:
        return (
            False,
            f"Invalid follow-up state transition from '{current}' to '{target}'. Allowed: {sorted(allowed)}",
        )

    ts = now()
    plan.followup_state = target
    if target == "acknowledged":
        plan.acknowledged_at = plan.acknowledged_at or ts
    elif target == "visit_confirmed":
        plan.visit_confirmed_at = plan.visit_confirmed_at or ts
        plan.appointment_status = "completed"
    elif target == "missed_appointment":
        plan.appointment_status = "missed"
    elif target == "rescheduled_by_authorised_staff":
        plan.appointment_status = "rescheduled"
    elif target == "closed":
        plan.closed_at = plan.closed_at or ts

    db.add(
        Event(
            clinic=plan.clinic,
            actor=actor_id,
            actor_role=actor_role,
            action="followup_state_transition",
            entity="care_plan",
            entity_id=plan.id,
            detail=f"{current} -> {target}" + (f" ({reason})" if reason else ""),
        )
    )
    return True, f"Transitioned '{current}' -> '{target}'."


def cancel_obsolete_reminders(
    db: Session,
    *,
    clinic: str,
    mother_id: Optional[str] = None,
    care_plan_id: Optional[str] = None,
    caregiver_id: Optional[str] = None,
    reason: str,
    actor_id: str = "system",
    actor_role: str = "system",
) -> int:
    """Cancel pending/retrying/dispatched reminder jobs when a care plan is superseded or consent is withdrawn."""
    stmt = select(ReminderJob).where(
        ReminderJob.clinic == clinic,
        ReminderJob.status.in_(("pending", "dispatched", "retrying")),
    )
    if mother_id:
        stmt = stmt.where(ReminderJob.mother_id == mother_id)
    if care_plan_id:
        stmt = stmt.where(ReminderJob.care_plan_id == care_plan_id)
    if caregiver_id:
        stmt = stmt.where(ReminderJob.caregiver_id == caregiver_id)

    jobs = list(db.scalars(stmt))
    ts = now()
    cancelled_count = 0
    for job in jobs:
        job.status = "cancelled"
        job.cancelled_at = ts
        job.cancellation_reason = reason
        job.updated_at = ts
        cancelled_count += 1

        outbox_key = f"cancel:{job.id}:{int(ts.timestamp())}"
        if not db.scalar(
            select(TransactionalOutbox).where(TransactionalOutbox.idempotency_key == outbox_key)
        ):
            db.add(
                TransactionalOutbox(
                    idempotency_key=outbox_key,
                    clinic=clinic,
                    aggregate_type="reminder_job",
                    aggregate_id=job.id,
                    event_type="cancel_reminder",
                    payload_json=json.dumps({"job_id": job.id, "reason": reason}),
                    status="dispatched",
                    dispatched_at=ts,
                )
            )

    if cancelled_count > 0:
        db.add(
            Event(
                clinic=clinic,
                actor=actor_id,
                actor_role=actor_role,
                action="cancel_obsolete_reminders",
                entity="care_plan" if care_plan_id else "mother",
                entity_id=care_plan_id or mother_id or caregiver_id or "batch",
                detail=f"Cancelled {cancelled_count} pending reminder job(s); reason={reason}",
            )
        )
    return cancelled_count


def schedule_reminders_for_care_plan(
    db: Session,
    plan: CarePlan,
    mother: Mother,
    *,
    actor_id: str,
    actor_role: str,
    channel_override: Optional[str] = None,
) -> list[ReminderJob]:
    """Create persistent ReminderJob + TransactionalOutbox records for a doctor-authorised CarePlan.

    Never infers appointment dates: strictly uses `plan.visit_date` authorised by `plan.approved_by`.
    Requires explicit mother consent (`mother.consent == True`) to schedule mother reminders,
    and explicit `CaregiverConsent` (`consent_granted == True` and `allow_admin_reminders == True`)
    to schedule caregiver administrative reminders.
    """
    if not plan.visit_date or not plan.approved_by:
        return []

    cfg = get_or_create_clinic_comm_config(db, plan.clinic)
    offsets = parse_offsets_hours(cfg)
    channel = (channel_override or cfg.default_channel or "local-simulator").strip()
    created_jobs: list[ReminderJob] = []

    # 1. Mother reminders (only if mother has granted communication consent)
    if mother.consent:
        tpl_mother = select_template_for_language(cfg, mother.language, "mother")
        for offset in offsets:
            idem_key = f"plan:{plan.id}:v{plan.version}:mother:{mother.id}:offset:{offset}"
            existing = db.scalar(
                select(ReminderJob).where(ReminderJob.idempotency_key == idem_key)
            )
            if existing:
                created_jobs.append(existing)
                continue

            sched_dt = compute_scheduled_datetime_ist(plan.visit_date, offset)
            job = ReminderJob(
                idempotency_key=idem_key,
                care_plan_id=plan.id,
                mother_id=mother.id,
                clinic=plan.clinic,
                recipient_type="mother",
                caregiver_id=None,
                offset_hours=offset,
                scheduled_for=sched_dt,
                timezone_name=cfg.timezone or "Asia/Kolkata",
                channel=channel,
                template_name=tpl_mother,
                status="pending",
                attempts=0,
                max_attempts=cfg.max_retry_attempts or 3,
            )
            db.add(job)
            db.flush()

            outbox = TransactionalOutbox(
                idempotency_key=f"outbox:{idem_key}",
                clinic=plan.clinic,
                aggregate_type="reminder_job",
                aggregate_id=job.id,
                event_type="enqueue_reminder",
                payload_json=json.dumps(
                    {
                        "job_id": job.id,
                        "care_plan_id": plan.id,
                        "mother_id": mother.id,
                        "recipient_type": "mother",
                        "offset_hours": offset,
                        "scheduled_for": sched_dt.isoformat(),
                    }
                ),
                status="pending",
            )
            db.add(outbox)
            created_jobs.append(job)

    # 2. Caregiver administrative reminders (only if clinic + caregiver explicitly permit)
    if cfg.enable_caregiver_reminders:
        caregivers = list(
            db.scalars(
                select(CaregiverConsent).where(
                    CaregiverConsent.mother_id == mother.id,
                    CaregiverConsent.clinic == plan.clinic,
                    CaregiverConsent.consent_granted.is_(True),
                    CaregiverConsent.allow_admin_reminders.is_(True),
                )
            )
        )
        for cg in caregivers:
            # Send a single -24h (or nearest configured offset) administrative reminder to caregiver
            cg_offset = -24 if -24 in offsets else offsets[0]
            idem_key = f"plan:{plan.id}:v{plan.version}:caregiver:{cg.id}:offset:{cg_offset}"
            existing = db.scalar(
                select(ReminderJob).where(ReminderJob.idempotency_key == idem_key)
            )
            if existing:
                created_jobs.append(existing)
                continue

            sched_dt = compute_scheduled_datetime_ist(plan.visit_date, cg_offset)
            job = ReminderJob(
                idempotency_key=idem_key,
                care_plan_id=plan.id,
                mother_id=mother.id,
                clinic=plan.clinic,
                recipient_type="caregiver",
                caregiver_id=cg.id,
                offset_hours=cg_offset,
                scheduled_for=sched_dt,
                timezone_name=cfg.timezone or "Asia/Kolkata",
                channel=channel,
                template_name="janani_caregiver_admin_reminder_v1",
                status="pending",
                attempts=0,
                max_attempts=cfg.max_retry_attempts or 3,
            )
            db.add(job)
            db.flush()

            db.add(
                TransactionalOutbox(
                    idempotency_key=f"outbox:{idem_key}",
                    clinic=plan.clinic,
                    aggregate_type="reminder_job",
                    aggregate_id=job.id,
                    event_type="enqueue_reminder",
                    payload_json=json.dumps(
                        {
                            "job_id": job.id,
                            "care_plan_id": plan.id,
                            "mother_id": mother.id,
                            "recipient_type": "caregiver",
                            "caregiver_id": cg.id,
                            "offset_hours": cg_offset,
                            "scheduled_for": sched_dt.isoformat(),
                        }
                    ),
                    status="pending",
                )
            )
            created_jobs.append(job)

    db.flush()
    return created_jobs


def process_outbox_and_due_jobs(
    db: Session,
    *,
    clinic: Optional[str] = None,
    force_due: bool = False,
    simulate_failure: bool = False,
    job_id_filter: Optional[str] = None,
) -> dict[str, Any]:
    """Transactional outbox dispatcher and reminder worker runner.

    Safely recovers pending outbox entries and executes due reminder jobs with exponential
    backoff retry and dead-letter transition after max_attempts.
    """
    ts = now()
    outbox_stmt = select(TransactionalOutbox).where(TransactionalOutbox.status == "pending")
    if clinic:
        outbox_stmt = outbox_stmt.where(TransactionalOutbox.clinic == clinic)

    dispatched_outbox = 0
    for entry in db.scalars(outbox_stmt):
        entry.status = "dispatched"
        entry.attempts += 1
        entry.dispatched_at = ts
        dispatched_outbox += 1
        try:
            payload = json.loads(entry.payload_json or "{}")
            jid = payload.get("job_id")
            if jid:
                j = db.get(ReminderJob, jid)
                if j and j.status == "pending":
                    j.status = "dispatched"
                    j.updated_at = ts
        except Exception as exc:
            entry.last_error = str(exc)

    db.flush()

    job_stmt = select(ReminderJob).where(
        ReminderJob.status.in_(("pending", "dispatched", "retrying"))
    )
    if clinic:
        job_stmt = job_stmt.where(ReminderJob.clinic == clinic)
    if job_id_filter:
        job_stmt = job_stmt.where(ReminderJob.id == job_id_filter)

    jobs = list(db.scalars(job_stmt.order_by(ReminderJob.scheduled_for.asc())))
    sent_count = 0
    retried_count = 0
    dead_letter_count = 0
    cancelled_count = 0

    for job in jobs:
        sched = job.scheduled_for
        if sched and sched.tzinfo is None:
            sched = sched.replace(tzinfo=timezone.utc)
        retry_at = job.next_retry_at
        if retry_at and retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)

        if not force_due and not job_id_filter:
            if job.status == "retrying" and retry_at and retry_at > ts:
                continue
            if job.status in ("pending", "dispatched") and sched and sched > ts:
                continue

        mother = db.get(Mother, job.mother_id)
        plan = db.get(CarePlan, job.care_plan_id)
        if not mother or not plan or not plan.active:
            job.status = "cancelled"
            job.cancelled_at = ts
            job.cancellation_reason = "care_plan_inactive_or_superseded"
            job.updated_at = ts
            cancelled_count += 1
            continue

        # Re-check consent before dispatch
        target_phone = mother.phone
        caregiver_name = ""
        lang = mother.language or "te"
        if job.recipient_type == "mother":
            if not mother.consent:
                job.status = "cancelled"
                job.cancelled_at = ts
                job.cancellation_reason = "mother_consent_withdrawn"
                job.updated_at = ts
                cancelled_count += 1
                continue
        elif job.recipient_type == "caregiver":
            cg = db.get(CaregiverConsent, job.caregiver_id) if job.caregiver_id else None
            if not cg or not cg.consent_granted or not cg.allow_admin_reminders:
                job.status = "cancelled"
                job.cancelled_at = ts
                job.cancellation_reason = "caregiver_permission_revoked"
                job.updated_at = ts
                cancelled_count += 1
                continue
            target_phone = cg.caregiver_phone
            caregiver_name = cg.caregiver_name
            lang = cg.language or "en"

        cfg = get_or_create_clinic_comm_config(db, job.clinic)
        rendered_body = render_approved_template(
            job.template_name,
            mother_name=mother.name,
            clinic=job.clinic,
            visit_date=plan.visit_date,
            caregiver_name=caregiver_name,
        )

        adapter = get_messaging_adapter(job.channel)
        job.attempts += 1
        job.updated_at = ts
        send_res = adapter.send_template_message(
            to_phone=target_phone,
            template_name=job.template_name,
            language_code=lang,
            rendered_body=rendered_body,
            idempotency_key=job.idempotency_key,
            recipient_type=job.recipient_type,
            simulate_failure=simulate_failure,
        )

        if send_res.ok:
            msg = Message(
                mother_id=mother.id,
                care_plan_id=plan.id,
                reminder_job_id=job.id,
                clinic=job.clinic,
                direction="outbound",
                recipient_type=job.recipient_type,
                recipient_phone_masked=mask_phone(target_phone),
                template_name=job.template_name,
                body=rendered_body,
                status="sent",
                delivery_status_rank=DELIVERY_STATUS_RANKS["sent"],
                provider=send_res.provider,
                provider_message_id=send_res.provider_message_id,
                idempotency_key=job.idempotency_key,
                sent_at=ts,
            )
            db.add(msg)
            db.flush()

            job.status = "sent"
            job.message_id = msg.id
            job.last_error = ""
            job.next_retry_at = None
            sent_count += 1

            # Update CarePlan follow-up state to reminder_sent if currently scheduled or delivery_failed
            if plan.followup_state in ("scheduled", "delivery_failed"):
                transition_care_plan_state(
                    db,
                    plan,
                    "reminder_sent",
                    actor_id="worker",
                    actor_role="system",
                    reason=f"Reminder job {job.id} sent via {send_res.provider}",
                )
                plan.ack_deadline_at = ts + timedelta(hours=cfg.ack_deadline_hours or 12)
        else:
            job.last_error = f"{send_res.failure_code}: {send_res.failure_reason}"
            if job.attempts >= job.max_attempts:
                job.status = "dead_letter"
                job.dead_lettered_at = ts
                job.next_retry_at = None
                dead_letter_count += 1

                # Record failed message entry for operator audit
                failed_msg = Message(
                    mother_id=mother.id,
                    care_plan_id=plan.id,
                    reminder_job_id=job.id,
                    clinic=job.clinic,
                    direction="outbound",
                    recipient_type=job.recipient_type,
                    recipient_phone_masked=mask_phone(target_phone),
                    template_name=job.template_name,
                    body=rendered_body,
                    status="failed",
                    delivery_status_rank=DELIVERY_STATUS_RANKS["failed"],
                    provider=send_res.provider,
                    idempotency_key=job.idempotency_key,
                    failure_code=send_res.failure_code,
                    failure_reason=send_res.failure_reason,
                    sent_at=ts,
                )
                db.add(failed_msg)
                db.flush()
                job.message_id = failed_msg.id

                if plan.followup_state in ("scheduled", "reminder_sent"):
                    transition_care_plan_state(
                        db,
                        plan,
                        "delivery_failed",
                        actor_id="worker",
                        actor_role="system",
                        reason=f"Dead-lettered after {job.attempts} attempts ({send_res.failure_code})",
                    )
            else:
                backoff_secs = (cfg.retry_base_seconds or 60) * (2 ** max(0, job.attempts - 1))
                job.status = "retrying"
                job.next_retry_at = ts + timedelta(seconds=backoff_secs)
                retried_count += 1

    db.flush()
    return {
        "outbox_dispatched": dispatched_outbox,
        "jobs_sent": sent_count,
        "jobs_retrying": retried_count,
        "jobs_dead_lettered": dead_letter_count,
        "jobs_cancelled": cancelled_count,
    }


def operator_retry_dead_letter_job(
    db: Session,
    job: ReminderJob,
    *,
    actor_id: str,
    actor_role: str,
    channel_override: Optional[str] = None,
) -> dict[str, Any]:
    """Reset a dead-lettered or retrying job and immediately re-run delivery."""
    if channel_override:
        job.channel = channel_override
    job.status = "pending"
    job.attempts = 0
    job.dead_lettered_at = None
    job.last_error = ""
    job.next_retry_at = None
    job.updated_at = now()

    db.add(
        Event(
            clinic=job.clinic,
            actor=actor_id,
            actor_role=actor_role,
            action="operator_retry_reminder_job",
            entity="reminder_job",
            entity_id=job.id,
            detail=f"Operator retried dead-letter job on channel={job.channel}",
        )
    )
    db.flush()
    return process_outbox_and_due_jobs(db, clinic=job.clinic, force_due=True, job_id_filter=job.id)


def process_delivery_callback(
    db: Session,
    *,
    event_id: str,
    provider: str,
    provider_message_id: Optional[str] = None,
    message_id: Optional[str] = None,
    delivery_status: str,
    failure_code: str = "",
    failure_reason: str = "",
    raw_payload_hash: str = "",
) -> dict[str, Any]:
    """Idempotent delivery status callback processor with strict rank-ordering protection."""
    existing_ev = db.scalar(select(WebhookEvent).where(WebhookEvent.event_id == event_id))
    if existing_ev:
        return {
            "ok": True,
            "duplicate_ignored": True,
            "event_id": event_id,
            "detail": "Duplicate webhook event_id ignored idempotently.",
        }

    msg: Optional[Message] = None
    if message_id:
        msg = db.get(Message, message_id)
    if not msg and provider_message_id:
        msg = db.scalar(
            select(Message).where(Message.provider_message_id == provider_message_id)
        )
    if not msg:
        return {"ok": False, "error": "Target message not found for delivery callback."}

    norm_status = delivery_status.strip().lower()
    if norm_status not in DELIVERY_STATUS_RANKS:
        return {"ok": False, "error": f"Unsupported delivery_status '{delivery_status}'."}

    new_rank = DELIVERY_STATUS_RANKS[norm_status]
    current_rank = msg.delivery_status_rank or 0
    ts = now()

    # Out-of-order protection: never downgrade a message that has already reached a higher delivery rank
    # (e.g., if 'sent' callback arrives after 'delivered' or 'acknowledged')
    status_updated = False
    if norm_status == "failed" and current_rank <= 1:
        msg.status = "failed"
        msg.delivery_status_rank = -1
        msg.failure_code = failure_code or "PROVIDER_DELIVERY_FAILED"
        msg.failure_reason = failure_reason or "Provider reported delivery failure"
        status_updated = True
    elif new_rank > current_rank:
        msg.status = norm_status
        msg.delivery_status_rank = new_rank
        if norm_status in ("delivered", "read") and not msg.delivered_at:
            msg.delivered_at = ts
        if norm_status == "acknowledged" and not msg.acknowledged_at:
            msg.acknowledged_at = ts
        status_updated = True

    if msg.care_plan_id and status_updated and msg.recipient_type == "mother":
        plan = db.get(CarePlan, msg.care_plan_id)
        if plan:
            if norm_status in ("delivered", "read") and plan.followup_state == "reminder_sent":
                transition_care_plan_state(
                    db,
                    plan,
                    "delivered",
                    actor_id=provider,
                    actor_role="webhook",
                    reason=f"Callback event {event_id}: {norm_status}",
                )
            elif norm_status == "failed" and plan.followup_state in ("scheduled", "reminder_sent"):
                transition_care_plan_state(
                    db,
                    plan,
                    "delivery_failed",
                    actor_id=provider,
                    actor_role="webhook",
                    reason=f"Callback event {event_id}: {failure_code}",
                )

    db.add(
        WebhookEvent(
            provider=provider,
            event_id=event_id,
            clinic=msg.clinic,
            event_type="delivery_callback",
            signature_verified=True,
            payload_hash=raw_payload_hash,
            status="processed",
            detail=f"msg={msg.id} status={msg.status} updated={status_updated}",
            processed_at=ts,
        )
    )
    db.flush()
    return {
        "ok": True,
        "duplicate_ignored": False,
        "message_id": msg.id,
        "message_status": msg.status,
        "status_updated": status_updated,
        "care_plan_id": msg.care_plan_id,
    }


def process_inbound_reply(
    db: Session,
    *,
    event_id: str,
    provider: str,
    mother_id: Optional[str] = None,
    from_phone: Optional[str] = None,
    care_plan_id: Optional[str] = None,
    reply_text: str,
    raw_payload_hash: str = "",
) -> dict[str, Any]:
    """Process an idempotent inbound message from a mother or caregiver.

    - Preserves exact verbatim patient reply.
    - Handles STOP/UNSUBSCRIBE opt-out immediately.
    - Handles YES/CONFIRM acknowledgement without implying clinic attendance (`visit_confirmed`).
    - Flags non-standard or concern replies for clinician review under clinic protocol without
      autonomous clinical diagnosis or severity scoring.
    """
    existing_ev = db.scalar(select(WebhookEvent).where(WebhookEvent.event_id == event_id))
    if existing_ev:
        return {
            "ok": True,
            "duplicate_ignored": True,
            "event_id": event_id,
            "detail": "Duplicate inbound webhook event_id ignored idempotently.",
        }

    mother: Optional[Mother] = None
    if mother_id:
        mother = db.get(Mother, mother_id)
    if not mother and from_phone:
        clean_digits = "".join(ch for ch in from_phone if ch.isdigit())[-10:]
        for m in db.scalars(select(Mother)):
            m_digits = "".join(ch for ch in (m.phone or "") if ch.isdigit())[-10:]
            if clean_digits and m_digits == clean_digits:
                mother = m
                break
    if not mother:
        return {"ok": False, "error": "Mother record not found for inbound message."}

    plan: Optional[CarePlan] = None
    if care_plan_id:
        plan = db.get(CarePlan, care_plan_id)
    if not plan:
        plan = db.scalar(
            select(CarePlan)
            .where(
                CarePlan.mother_id == mother.id,
                CarePlan.clinic == mother.clinic,
                CarePlan.active.is_(True),
            )
            .order_by(CarePlan.version.desc())
        )

    verbatim = (reply_text or "").strip()
    upper = verbatim.upper()
    ts = now()

    # Check if reply is opt-out, standard acknowledgement, or requires human/clinician review
    is_opt_out = upper in ("STOP", "UNSUBSCRIBE", "OPT OUT", "OPTOUT", "CANCEL")
    is_ack = upper in ("YES", "Y", "OK", "CONFIRM", "CONFIRMED", "1", "అవును", "हाँ", "HAAN")
    needs_clinical_review = not is_opt_out and not is_ack

    inbound_msg = Message(
        mother_id=mother.id,
        care_plan_id=plan.id if plan else None,
        clinic=mother.clinic,
        direction="inbound",
        recipient_type="mother",
        recipient_phone_masked=mask_phone(mother.phone),
        body=verbatim,
        status="received",
        delivery_status_rank=DELIVERY_STATUS_RANKS["acknowledged"] if is_ack else 2,
        provider=provider,
        provider_message_id=f"in.{event_id}",
        idempotency_key=f"inbound:{event_id}",
        sent_at=ts,
        acknowledged_at=ts if is_ack else None,
        flagged_for_clinical_review=needs_clinical_review,
        clinical_review_status="pending_clinician_review" if needs_clinical_review else "not_required",
    )
    db.add(inbound_msg)
    db.flush()

    action_taken = "recorded_verbatim"
    if is_opt_out:
        mother.consent = False
        mother.consent_updated_at = ts
        cancelled = cancel_obsolete_reminders(
            db,
            clinic=mother.clinic,
            mother_id=mother.id,
            reason="patient_inbound_opt_out",
            actor_id=mother.id,
            actor_role="mother",
        )
        action_taken = f"consent_withdrawn_cancelled_{cancelled}_jobs"
    elif is_ack and plan:
        if plan.followup_state in ("scheduled", "reminder_sent", "delivered", "no_acknowledgement", "contact_required", "staff_assigned"):
            if plan.followup_state == "scheduled":
                transition_care_plan_state(
                    db, plan, "reminder_sent", actor_id=mother.id, actor_role="mother", reason="Inbound ack"
                )
            transition_care_plan_state(
                db,
                plan,
                "acknowledged",
                actor_id=mother.id,
                actor_role="mother",
                reason=f"Patient replied '{verbatim}'",
            )
            action_taken = "care_plan_acknowledged"
    elif needs_clinical_review and plan:
        # Create an operational follow-up task for staff/clinician protocol review without autonomous diagnosis
        existing_task = db.scalar(
            select(Task).where(
                Task.mother_id == mother.id,
                Task.care_plan_id == plan.id,
                Task.category == "flagged_message_review",
                Task.status.in_(("open", "in_progress")),
            )
        )
        if not existing_task:
            assignee = _find_clinic_followup_assignee(db, mother.clinic)
            db.add(
                Task(
                    mother_id=mother.id,
                    care_plan_id=plan.id,
                    clinic=mother.clinic,
                    category="flagged_message_review",
                    priority="high",
                    due_date=date.today(),
                    status="open",
                    assigned_to=assignee,
                    detail=f"Patient reply requires staff/clinician protocol review: \"{verbatim}\"",
                    created_by="system",
                )
            )
        action_taken = "flagged_for_clinician_protocol_review"

    db.add(
        WebhookEvent(
            provider=provider,
            event_id=event_id,
            clinic=mother.clinic,
            event_type="inbound_message",
            signature_verified=True,
            payload_hash=raw_payload_hash or hashlib.sha256(verbatim.encode("utf-8")).hexdigest(),
            status="processed",
            detail=f"msg={inbound_msg.id} action={action_taken}",
            processed_at=ts,
        )
    )
    db.flush()
    return {
        "ok": True,
        "duplicate_ignored": False,
        "message_id": inbound_msg.id,
        "action_taken": action_taken,
        "flagged_for_clinical_review": inbound_msg.flagged_for_clinical_review,
        "care_plan_followup_state": plan.followup_state if plan else None,
    }


def _find_clinic_followup_assignee(db: Session, clinic: str) -> str:
    """Select an active nurse or field coordinator in the clinic for follow-up task assignment."""
    staff = db.scalar(
        select(Staff)
        .where(
            Staff.clinic == clinic,
            Staff.is_active.is_(True),
            Staff.role.in_(("field_coordinator", "nurse")),
        )
        .order_by(Staff.role.asc())
    )
    if staff:
        return staff.id
    fallback = db.scalar(
        select(Staff).where(Staff.clinic == clinic, Staff.is_active.is_(True))
    )
    return fallback.id if fallback else ""


def evaluate_overdue_acknowledgements(
    db: Session,
    *,
    clinic: Optional[str] = None,
    as_of: Optional[datetime] = None,
) -> dict[str, Any]:
    """Scan active CarePlans whose acknowledgement deadline has passed and create human follow-up tasks."""
    reference_ts = as_of or now()
    stmt = select(CarePlan).where(
        CarePlan.active.is_(True),
        CarePlan.followup_state.in_(("reminder_sent", "delivered", "delivery_failed")),
    )
    if clinic:
        stmt = stmt.where(CarePlan.clinic == clinic)

    plans = list(db.scalars(stmt))
    tasks_created = 0
    plans_escalated = 0

    for plan in plans:
        deadline = plan.ack_deadline_at
        if deadline and deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)

        is_overdue = False
        if plan.followup_state == "delivery_failed":
            is_overdue = True
        elif deadline and deadline <= reference_ts:
            is_overdue = True
        elif plan.visit_date < reference_ts.date():
            is_overdue = True

        if not is_overdue:
            continue

        if plan.followup_state in ("reminder_sent", "delivered"):
            transition_care_plan_state(
                db,
                plan,
                "no_acknowledgement",
                actor_id="scheduler",
                actor_role="system",
                reason="Operational acknowledgement deadline elapsed",
            )
        transition_care_plan_state(
            db,
            plan,
            "contact_required",
            actor_id="scheduler",
            actor_role="system",
            reason="Human follow-up required",
        )

        existing_task = db.scalar(
            select(Task).where(
                Task.mother_id == plan.mother_id,
                Task.care_plan_id == plan.id,
                Task.category.in_(("unacknowledged_reminder_followup", "missed_visit")),
                Task.status.in_(("open", "in_progress")),
            )
        )
        assignee = _find_clinic_followup_assignee(db, plan.clinic)
        if not existing_task:
            t = Task(
                mother_id=plan.mother_id,
                care_plan_id=plan.id,
                clinic=plan.clinic,
                category="unacknowledged_reminder_followup",
                priority="high",
                due_date=date.today(),
                status="open",
                assigned_to=assignee,
                detail=(
                    f"Operational deadline passed without patient acknowledgement for "
                    f"doctor-authorised ANC visit on {plan.visit_date.isoformat()}. "
                    f"Please contact patient/caregiver and record outcome."
                ),
                created_by="system",
            )
            db.add(t)
            db.flush()
            tasks_created += 1

        if assignee:
            transition_care_plan_state(
                db,
                plan,
                "staff_assigned",
                actor_id="scheduler",
                actor_role="system",
                reason=f"Assigned follow-up task to {assignee}",
            )
        plans_escalated += 1

    db.flush()
    return {
        "plans_escalated": plans_escalated,
        "tasks_created": tasks_created,
    }

