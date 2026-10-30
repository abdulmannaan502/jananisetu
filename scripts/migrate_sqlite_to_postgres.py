"""Utility script to migrate existing SQLite records into PostgreSQL (or upgrade schema in-place)."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import ensure_schema_and_migrate_legacy
from app.models import (
    Base,
    CarePlan,
    Document,
    Event,
    Expense,
    Message,
    Mother,
    Staff,
    Task,
    Transport,
)
from app.security import hash_password


def migrate_data(source_url: str, target_url: str) -> dict[str, int]:
    """Copy all records from a source SQLite database into a target PostgreSQL/SQLAlchemy database."""
    src_engine = create_engine(
        source_url,
        connect_args={"check_same_thread": False} if source_url.startswith("sqlite") else {},
    )
    ensure_schema_and_migrate_legacy(src_engine)

    tgt_engine = create_engine(
        target_url,
        connect_args={"check_same_thread": False} if target_url.startswith("sqlite") else {},
    )
    ensure_schema_and_migrate_legacy(tgt_engine)

    SrcSession = sessionmaker(bind=src_engine)
    TgtSession = sessionmaker(bind=tgt_engine)

    counts: dict[str, int] = {}
    default_pw = hash_password("Janani@2026")

    models_in_order = [
        Staff,
        Mother,
        CarePlan,
        Task,
        Message,
        Transport,
        Expense,
        Document,
        Event,
    ]

    with SrcSession() as src_db, TgtSession() as tgt_db:
        for model in models_in_order:
            table_name = model.__tablename__
            rows = list(src_db.scalars(select(model)))
            migrated = 0
            for item in rows:
                if tgt_db.get(model, item.id) is not None:
                    continue
                data = {
                    col.name: getattr(item, col.name)
                    for col in model.__table__.columns
                }
                if model is Staff and not data.get("password_hash"):
                    data["password_hash"] = default_pw
                if "clinic" in data and not data.get("clinic"):
                    data["clinic"] = "demo-clinic"
                tgt_db.add(model(**data))
                migrated += 1
            tgt_db.commit()
            counts[table_name] = migrated

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate JananiSetu SQLite data to PostgreSQL.")
    parser.add_argument(
        "--source",
        default=f"sqlite:///{ROOT / 'data' / 'janani.db'}",
        help="Source SQLite URL",
    )
    parser.add_argument(
        "--target",
        required=True,
        help="Target PostgreSQL URL (e.g., postgresql+psycopg://janani:pass@localhost:5432/jananisetu)",
    )
    args = parser.parse_args()
    result = migrate_data(args.source, args.target)
    print("Migration complete:", result)


if __name__ == "__main__":
    main()

