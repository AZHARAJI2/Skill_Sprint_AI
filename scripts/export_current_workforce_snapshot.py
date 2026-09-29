"""Export the approved local workforce into the reproducible Git seed snapshot.

The export deliberately includes profile and role fields only. It never exports
password hashes, API keys, source-document binaries, plans, quiz answers, or
scores. Plans must continue to be produced from the committed corpus and role
matrix at seed time, as required by the Project Map.

Run after an administrator has reviewed newly imported employee profiles:
    .\\.venv\\Scripts\\python.exe -m scripts.export_current_workforce_snapshot
"""

from __future__ import annotations

import argparse
import base64
from datetime import date
import gzip
import json
from pathlib import Path

from database.base import SessionLocal
from src.employees.models import Employee, EmployeeRole


DEFAULT_OUTPUT = Path("database/current_demo_snapshot.py")


def _as_json_value(value):
    if isinstance(value, date):
        return value.isoformat()
    return value


def build_workforce_payload() -> dict[str, list[dict]]:
    """Return roles referenced by employee profiles and the corresponding data."""
    session = SessionLocal()
    try:
        employees = session.query(Employee).order_by(Employee.employee_code).all()
        role_ids = {employee.role_id for employee in employees}
        roles = (
            session.query(EmployeeRole)
            .filter(EmployeeRole.id.in_(role_ids))
            .order_by(EmployeeRole.title)
            .all()
        )
        role_by_id = {role.id: role for role in roles}
        if len(role_by_id) != len(role_ids):
            raise ValueError("Every exported employee must refer to an existing job role.")

        return {
            "roles": [
                {
                    "title": role.title,
                    "department": role.department,
                    "description": role.description,
                }
                for role in roles
            ],
            "employees": [
                {
                    "employee_code": employee.employee_code,
                    "name": employee.name,
                    "role_title": role_by_id[employee.role_id].title,
                    "department": employee.department,
                    "experience_level": employee.experience_level,
                    "location": employee.location,
                    "joining_date": _as_json_value(employee.joining_date),
                    "reporting_manager": employee.reporting_manager,
                    "required_competencies": employee.required_competencies,
                    "prior_experience": employee.prior_experience,
                    "training_status": employee.training_status,
                }
                for employee in employees
            ],
        }
    finally:
        session.close()


def render_snapshot_module(payload: dict[str, list[dict]]) -> str:
    """Render deterministic, compressed Python source for the seed reader."""
    encoded = base64.b64encode(
        gzip.compress(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            mtime=0,
        )
    ).decode("ascii")
    chunks = "\n".join(f'    "{encoded[index:index + 100]}"' for index in range(0, len(encoded), 100))
    return f'''"""Compressed, versioned employee snapshot for a reproducible evaluator seed.

This contains approved demonstration profiles only—never password hashes,
API keys, uploaded files, generated plan content, quiz answers, or scores.
Run ``python -m scripts.export_current_workforce_snapshot`` after reviewing
approved local employee imports to refresh this Git-tracked snapshot.
"""

from __future__ import annotations

import base64
import gzip
import json
from typing import Any


_CURRENT_WORKFORCE_B64 = (
{chunks}
)


def load_current_workforce() -> dict[str, list[dict[str, Any]]]:
    """Return a fresh copy of the committed employee/role seed snapshot."""
    payload = gzip.decompress(base64.b64decode(_CURRENT_WORKFORCE_B64))
    decoded = json.loads(payload.decode("utf-8"))
    if not isinstance(decoded, dict) or not isinstance(decoded.get("roles"), list) or not isinstance(decoded.get("employees"), list):
        raise ValueError("Current workforce seed snapshot is invalid.")
    return decoded
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--minimum-employees", type=int, default=1000)
    args = parser.parse_args()

    workforce = build_workforce_payload()
    employee_count = len(workforce["employees"])
    if employee_count < args.minimum_employees:
        raise SystemExit(
            f"Refusing to replace the snapshot: found {employee_count} employees, "
            f"below the required minimum of {args.minimum_employees}."
        )

    args.out.write_text(render_snapshot_module(workforce), encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {"output": str(args.out), "employees": employee_count, "roles": len(workforce["roles"])},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
