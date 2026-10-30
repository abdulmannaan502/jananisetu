"""Celery + Redis worker and Celery Beat scheduler for JananiSetu Phase 4 durable reminders."""
from __future__ import annotations

from typing import Any, Optional
from celery import Celery
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.followup_engine import (
    evaluate_overdue_acknowledgements,
    process_outbox_and_due_jobs,
)
from app.models import ReminderJob, TransactionalOutbox

settings = get_settings()

celery_app = Celery(
    "jananisetu",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    timezone=settings.default_timezone or "Asia/Kolkata",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    beat_schedule={
        "dispatch-outbox-and-due-reminders-every-60s": {
            "task": "jananisetu.process_due_reminders",
            "schedule": 60.0,
        },
        "evaluate-overdue-acknowledgements-every-300s": {
            "task": "jananisetu.evaluate_overdue_acknowledgements",
            "schedule": 300.0,
        },
    },
)


@celery_app.task(name="jananisetu.process_due_reminders", bind=True, max_retries=3)
def task_process_due_reminders(self, clinic: Optional[str] = None, force_due: bool = False) -> dict[str, Any]:
    with SessionLocal() as db:
        result = process_outbox_and_due_jobs(db, clinic=clinic, force_due=force_due)
        db.commit()
        return result


@celery_app.task(name="jananisetu.evaluate_overdue_acknowledgements", bind=True)
def task_evaluate_overdue_acknowledgements(self, clinic: Optional[str] = None) -> dict[str, Any]:
    with SessionLocal() as db:
        result = evaluate_overdue_acknowledgements(db, clinic=clinic)
        db.commit()
        return result


def check_worker_and_queue_health(db: Session, clinic: str) -> dict[str, Any]:
    """Return Redis broker connectivity, Celery Beat configuration, and clinic-scoped queue depth metrics."""
    redis_connected = False
    redis_error = ""
    try:
        import redis

        r = redis.Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=0.35,
            socket_timeout=0.35,
        )
        redis_connected = bool(r.ping())
    except Exception as exc:
        redis_error = str(exc)[:180]

    pending_jobs = db.scalar(
        select(func.count(ReminderJob.id)).where(
            ReminderJob.clinic == clinic,
            ReminderJob.status.in_(("pending", "dispatched")),
        )
    ) or 0
    retrying_jobs = db.scalar(
        select(func.count(ReminderJob.id)).where(
            ReminderJob.clinic == clinic,
            ReminderJob.status == "retrying",
        )
    ) or 0
    dead_letter_jobs = db.scalar(
        select(func.count(ReminderJob.id)).where(
            ReminderJob.clinic == clinic,
            ReminderJob.status == "dead_letter",
        )
    ) or 0
    sent_jobs = db.scalar(
        select(func.count(ReminderJob.id)).where(
            ReminderJob.clinic == clinic,
            ReminderJob.status == "sent",
        )
    ) or 0
    cancelled_jobs = db.scalar(
        select(func.count(ReminderJob.id)).where(
            ReminderJob.clinic == clinic,
            ReminderJob.status == "cancelled",
        )
    ) or 0
    pending_outbox = db.scalar(
        select(func.count(TransactionalOutbox.id)).where(
            TransactionalOutbox.clinic == clinic,
            TransactionalOutbox.status == "pending",
        )
    ) or 0

    return {
        "worker_engine": "celery+redis" if redis_connected else "db_transactional_outbox_runner",
        "redis_broker_connected": redis_connected,
        "redis_url_configured": bool(settings.redis_url),
        "redis_note": (
            "Redis broker connected."
            if redis_connected
            else f"Redis broker offline locally ({redis_error or 'not running'}); deterministic DB transactional outbox runner active."
        ),
        "timezone": settings.default_timezone or "Asia/Kolkata",
        "beat_schedules": list(celery_app.conf.beat_schedule.keys()),
        "queue_metrics": {
            "pending_jobs": pending_jobs,
            "retrying_jobs": retrying_jobs,
            "dead_letter_jobs": dead_letter_jobs,
            "sent_jobs": sent_jobs,
            "cancelled_jobs": cancelled_jobs,
            "pending_outbox_events": pending_outbox,
        },
    }

