# JananiSetu — Deployment & Operations Guide

JananiSetu supports two deployment modes:
1. **Mode A: Docker Compose Deployment (Preferred / Production Topology)**
2. **Mode B: Local Windows Development Deployment**

---

## 1. Mode A: Docker Compose Deployment (Recommended)

### Prerequisites
- Docker Engine 24.0+ & Docker Compose v2 (e.g. Docker Desktop)
- Minimum 4 GB RAM allocated to Docker VM
- Port availability: `8000` (FastAPI/React), `5432` (PostgreSQL), `6379` (Redis)

### Architecture of Services in Compose
- `jananisetu-postgres`: PostgreSQL 16 Alpine with persistent volume `pgdata` and automated health check (`pg_isready`).
- `jananisetu-redis`: Redis 7 Alpine with persistent volume `redisdata` and health check (`redis-cli ping`).
- `jananisetu-backend`: Multi-stage build producing static React frontend and running Alembic migrations on container startup (`alembic upgrade head`).
- `jananisetu-celery-worker`: Background worker processing transactional outbox polling and retry tasks.
- `jananisetu-celery-beat`: Periodic scheduler triggering routine follow-up escalation checks.

### Startup Commands
```bash
# 1. Obtain repository source
cd jananisetu

# 2. Build and launch all services with health checks
docker compose up -d --build

# 3. Inspect running services
docker compose ps

# 4. Verify backend health
curl -f http://localhost:8000/api/health

# 5. Access the Web Application
# Open your browser to http://localhost:8000
```

### Graceful Teardown
```bash
docker compose down
```

---

## 2. Mode B: Local Windows Development Deployment

### Prerequisites
- Python 3.11+ (Python 3.12+ recommended)
- Node.js v20+ & npm
- Tesseract-OCR v5 (optional, falls back gracefully to structured OCR extraction)

### Step-by-Step Local Setup

#### Step 1: Environment & Virtual Environment
```powershell
# Navigate to project directory
cd c:\Projects\Healthathon\jananisetu

# Verify Python virtual environment
.\.venv\Scripts\Activate.ps1

# Install backend dependencies
pip install -r requirements.txt
```

#### Step 2: Database Schema & Demonstration Dataset
```powershell
# Run Alembic migrations to latest revision (0005)
alembic upgrade head

# Seed the complete synthetic demonstration dataset
python -m scripts.seed_demo_data
```

#### Step 3: Frontend Build
```powershell
cd frontend
npm install
npm run build
cd ..
```

#### Step 4: Run FastAPI Server
```powershell
# Start Uvicorn serving both REST API and React SPA
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

#### Step 5: Access the Application
Open your web browser at:  
👉 **http://127.0.0.1:8000**

Default Demonstration Accounts (Pre-configured):
- **Clinic Administrator**: `admin@nalgonda.janani.org` | Password: `Janani@2026`
- **Medical Officer (Doctor)**: `doctor@nalgonda.janani.org` | Password: `Janani@2026`
- **ANM Staff Nurse**: `nurse@nalgonda.janani.org` | Password: `Janani@2026`
- **Field Coordinator**: `coordinator@nalgonda.janani.org` | Password: `Janani@2026`

---

## 3. Host Dependency Status & Known Blockers on Windows Host

| Component | Status on Windows Host | Cause & Exact Resolution |
| :--- | :---: | :--- |
| **Docker CLI** | `Not Installed` | Host machine does not have Docker Desktop in system PATH. Docker Compose deployment is validated for environments where Docker Engine is installed. |
| **PostgreSQL Service** | `Running (Port 5432)` | Active Windows service `postgresql-x64-18` uses custom credentials. To prevent destructive interference with existing databases, password reset was not performed. The local environment uses SQLite for deterministic execution while Alembic maintains PostgreSQL compatibility. |
| **Redis** | `Not Running Locally` | Port 6379 inactive. The application relies on its built-in database-backed **Transactional Outbox Engine**, which provides full retry durability without requiring an active Redis server. |
| **Meta WhatsApp API** | `Mock Gateway Active` | Real WhatsApp Cloud API requires Meta Business Manager verification and Indian DLT compliance. The built-in simulator provides full webhook HMAC signing and state-machine transitions. |

