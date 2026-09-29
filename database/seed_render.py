"""Render-aware seed: runs the full seed only when the database is empty.

This module is called from build.sh on every Render deploy.
It is idempotent: if users, roles, or employees already exist it exits
quickly without touching the database.  On a fresh PostgreSQL instance
(first deploy or a database reset) it runs the complete seed so the
evaluator can log in immediately after the service starts.

Usage:
    python -m database.seed_render
"""

from __future__ import annotations

import sys

from config.logging_config import configure_logging, get_logger
from config.settings import settings
from database.base import SessionLocal
from database.migrations import create_schema
from src.auth.models import User
from src.employees.models import Employee

configure_logging()
logger = get_logger("seed_render")


def _database_has_data(session) -> bool:
    """Return True if the DB already contains users and employees."""
    user_count = session.query(User).count()
    employee_count = session.query(Employee).count()
    return user_count > 0 and employee_count > 0


def main() -> None:
    """Entry point: seed only when the database is empty."""
    settings.ensure_runtime_dirs()

    # Always create schema (safe / idempotent via create_all)
    create_schema()
    logger.info("render_seed schema_ready")

    session = SessionLocal()
    try:
        if _database_has_data(session):
            logger.info(
                "render_seed skipped  database already contains data; "
                "existing employees and plans are preserved"
            )
            print(
                "[OK] Database already seeded  skipping to preserve existing data.",
                flush=True,
            )
            return

        logger.info("render_seed starting  database is empty, running full seed")
        print("[SEED] Empty database detected  running full seed...", flush=True)

    finally:
        session.close()

    # Import here to avoid circular-import issues at module load time
    from database.seed import seed_all  # noqa: PLC0415

    try:
        summary = seed_all(ingest_documents=True, seed_demo_plans=True)
        logger.info("render_seed complete summary=%s", summary)
        print("\n  Seed complete!", flush=True)
        print(f"    Files ingested : {summary.get('files_ingested', 0)}", flush=True)
        print(f"    Matrix rows    : {summary.get('matrix_loaded', 0)}", flush=True)
        demo_plans = summary.get("demo_plans", {})
        print(f"    Demo plans     : {demo_plans.get('created', 0)}", flush=True)
        accounts = summary.get("employee_accounts", [])
        print(f"    Employees     : {summary.get('employees_seeded', len(accounts))}", flush=True)
        print(f"    Employee accts : {len(accounts)}", flush=True)
        print("\n  Staff logins (all pre-created):", flush=True)
        print("   admin    / admin123", flush=True)
        print("   trainer  / trainer123", flush=True)
        print("   reviewer / reviewer123", flush=True)
        print("   manager  / manager123", flush=True)
        print("   employee / employee123", flush=True)
    except Exception as exc:
        logger.error("render_seed failed error=%s", exc)
        print(f"\n  Seed failed: {exc}", flush=True)
        # Exit with non-zero so Render marks the deploy as failed
        # (better to fail visibly than silently start with an empty DB)
        sys.exit(1)


if __name__ == "__main__":
    main()
