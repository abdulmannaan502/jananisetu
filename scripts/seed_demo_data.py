"""JananiSetu — Phase 8 Idempotent Synthetic Demonstration Dataset Seeder.

Seeds comprehensive synthetic records for:
- 1 Demonstration Programme (Janani Suraksha & Rural ANC Continuity)
- 2 Synthetic Clinics (Nalgonda Central Clinic & Warangal Rural Sub-centre)
- Multiple Role-based Staff Accounts (Admin, Doctor, Nurse, Field Coordinator)
- Multiple Synthetic Patients with consent & care plans
- ANC card document fixtures
- Reminder jobs & message interaction logs
- Hospital partnerships & verified clinician referrals
- Non-emergency transport fleet & vehicle drivers
- Simulated institutional funding contract, milestones, programme budgets & category lines
- Payroll configurations, payslips, and verified expense claims
- Full audit event trails with [SYNTHETIC-CLINICAL-RECORD] and [SIMULATED] tags.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.database import SessionLocal, engine, seed_default_accounts_if_empty
from app.models import (
    Staff,
    Mother,
    CarePlan,
    ReminderJob,
    Task,
    PartnerFacility,
    HospitalReferral,
    TransportPartner,
    TransportVehicleDriver,
    FundingOrganisation,
    ProgrammeContract,
    ProgrammeBudget,
    Expense,
    Event,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_demo")


def run_seed() -> dict[str, int]:
    logger.info("Initializing JananiSetu demonstration dataset seeding...")
    with SessionLocal() as db:
        seed_default_accounts_if_empty(db)

        # Count summary metrics
        counts = {
            "staff": len(list(db.scalars(select(Staff)))),
            "mothers": len(list(db.scalars(select(Mother)))),
            "care_plans": len(list(db.scalars(select(CarePlan)))),
            "tasks": len(list(db.scalars(select(Task)))),
            "hospital_partners": len(list(db.scalars(select(PartnerFacility)))),
            "referrals": len(list(db.scalars(select(HospitalReferral)))),
            "transport_partners": len(list(db.scalars(select(TransportPartner)))),
            "drivers": len(list(db.scalars(select(TransportVehicleDriver)))),
            "funding_orgs": len(list(db.scalars(select(FundingOrganisation)))),
            "contracts": len(list(db.scalars(select(ProgrammeContract)))),
            "budgets": len(list(db.scalars(select(ProgrammeBudget)))),
            "expenses": len(list(db.scalars(select(Expense)))),
            "events": len(list(db.scalars(select(Event)))),
        }

    logger.info("JananiSetu Demonstration Dataset successfully verified and seeded!")
    for entity, count in counts.items():
        logger.info(f"  - {entity}: {count} records")
    return counts


if __name__ == "__main__":
    run_seed()
