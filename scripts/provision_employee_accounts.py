"""Create or normalize employee sign-ins for all existing employee profiles.

Run with --reset-passwords only when an administrator is ready to distribute
the newly printed temporary passwords through a private channel.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permit both `python -m scripts.provision_employee_accounts` and direct
# execution from the project folder, without relying on a global PYTHONPATH.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.base import SessionLocal
from database.migrations import create_schema
from src.auth.service import AuthService
from src.employees.service import EmployeeService


def main() -> None:
    """Provision accounts and print credentials only to the invoking administrator."""
    parser = argparse.ArgumentParser(description="Provision SkillSprint employee accounts.")
    parser.add_argument("--reset-passwords", action="store_true", help="Set and print new initial passwords.")
    args = parser.parse_args()
    create_schema()
    session = SessionLocal()
    try:
        auth = AuthService(session)
        employees = EmployeeService(session).list_employees()
        for employee in employees:
            account, initial_password = auth.provision_employee_account(
                employee,
                reset_password=args.reset_passwords,
                normalize_username=True,
                actor="account-provisioning",
            )
            password = initial_password or "(unchanged)"
            print(f"{employee.employee_code}\t{employee.name}\t{account.username}\t{password}")
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
