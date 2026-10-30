# JananiSetu — Deployment Readiness & Production Operations

This document outlines the container architecture, environment configuration, database migration procedure, and runtime deployment topology for production rollouts.

---

## 1. Container Infrastructure & Docker Compose

JananiSetu provides a multi-container Docker Compose configuration (`docker-compose.yml`) supporting the entire production stack:

### Services:
1. **`db` (PostgreSQL 16)**:
   - Image: `postgres:16-alpine`
   - Volume: `pg_data:/var/lib/postgresql/data`
   - Healthcheck: `pg_isready -U janani -d jananisetu`
2. **`redis` (Cache & Task Broker)**:
   - Image: `redis:7-alpine`
   - Healthcheck: `redis-cli ping`
3. **`api` (FastAPI Application Server)**:
   - Build: `.` (Dockerfile with Python 3.12/3.14 virtual environment)
   - Command: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4`
   - Depends on: `db`, `redis`
4. **`celery_worker` (Background Reminder Worker)**:
   - Command: `celery -A app.celery_app worker --loglevel=info -c 4`
   - Depends on: `api`, `redis`, `db`
5. **`celery_beat` (Scheduled Beat Engine)**:
   - Command: `celery -A app.celery_app beat --loglevel=info`
   - Depends on: `celery_worker`
6. **`frontend` (React + Nginx)**:
   - Multi-stage build compiling TypeScript/Tailwind and serving production bundles via Nginx on port 80.

---

## 2. Environment Variables & Secrets Management

Production deployments require the following environment variables (defined in `.env` or injected via container secrets):

| Variable | Description | Production Requirement |
| :--- | :--- | :--- |
| `JANANI_ENV` | Environment identifier | Must be `production` |
| `SECRET_KEY` | Cryptographic secret for JWT signing | 64+ char random hex string (never default) |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host:5432/dbname` |
| `REDIS_URL` | Redis connection string | `redis://:pass@host:6379/0` |
| `WEBHOOK_SECRET` | HMAC secret for WhatsApp Cloud API | Shared secret with Meta Developer Dashboard |
| `META_WHATSAPP_TOKEN` | Bearer token for WhatsApp Cloud API | System user token with `whatsapp_business_messaging` |
| `META_PHONE_NUMBER_ID` | WhatsApp Business Phone Number ID | Meta Developer ID |
| `JANANI_ALLOW_LEGACY_HEADER`| Legacy `X-Staff-ID` backward compat | Must be `false` (enforces strict JWT authentication) |

---

## 3. Database Migration Strategy

- **Tool**: Alembic with SQLAlchemy.
- **Transactional Migrations**: Revisions run within an explicit transaction. If any DDL fails, the entire migration rolls back without leaving corrupted schemas.
- **Current Revision**: `0005_phase6_contracts_budgets_payroll`.
- **Command to Apply**:
  ```bash
  alembic upgrade head
  ```
- **SQLite to PostgreSQL Data Migration**: Included CLI utility `scripts/migrate_sqlite_to_postgres.py` transfers existing clinics, staff, mothers, care plans, and documents safely with table dependency resolution.

---

## 4. Background Worker & Transactional Outbox Operations

- **Zero-Loss Guarantee**: Even during Celery worker restarts, the transactional outbox (`transactional_outbox` table) ensures no scheduled reminder or SMS job is lost.
- **Fallback Outbox Runner**: In lightweight clinic deployments lacking Redis/Celery, the built-in outbox runner endpoint (`POST /api/reminders/worker/run`) can be triggered by a standard system cron or task scheduler every 60 seconds to dispatch pending communications.

