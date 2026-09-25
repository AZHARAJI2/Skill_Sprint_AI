"""Employee and job-role CRUD API."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.base import get_session
from src.auth.dependencies import get_current_user, require_role
from src.auth.models import User
from src.employees.service import EmployeeService, RoleService

router = APIRouter(prefix="/api", tags=["employees"])


class RoleCreate(BaseModel):
    """Payload to create a job role."""

    title: str
    department: str
    description: str | None = None


class EmployeeCreate(BaseModel):
    """Payload to create an employee profile."""

    employee_code: str
    name: str
    role_id: int
    department: str
    experience_level: str = "Beginner"
    location: str | None = None
    joining_date: date | None = None
    reporting_manager: str | None = None
    required_competencies: list[str] | None = None
    prior_experience: str | None = None
    training_status: str = "not_started"


class EmployeeUpdate(BaseModel):
    """Patchable employee fields."""

    name: str | None = None
    role_id: int | None = None
    department: str | None = None
    experience_level: str | None = None
    location: str | None = None
    joining_date: date | None = None
    reporting_manager: str | None = None
    required_competencies: list[str] | None = None
    prior_experience: str | None = None
    training_status: str | None = None


def _employee_payload(employee) -> dict:
    return {
        "id": employee.id,
        "employee_code": employee.employee_code,
        "name": employee.name,
        "role_id": employee.role_id,
        "role_title": employee.role.title if employee.role else None,
        "department": employee.department,
        "experience_level": employee.experience_level,
        "location": employee.location,
        "joining_date": employee.joining_date.isoformat() if employee.joining_date else None,
        "reporting_manager": employee.reporting_manager,
        "required_competencies": employee.required_competencies,
        "prior_experience": employee.prior_experience,
        "training_status": employee.training_status,
    }


@router.post("/roles")
def create_role(
    body: RoleCreate,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager")),
) -> dict:
    """Create a job role."""
    role = RoleService(session).create(body.title, body.department, body.description)
    return {"id": role.id, "title": role.title, "department": role.department, "description": role.description}


@router.get("/roles")
def list_roles(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """List job roles."""
    del user
    return [
        {"id": r.id, "title": r.title, "department": r.department, "description": r.description}
        for r in RoleService(session).list_roles()
    ]


@router.post("/employees")
def create_employee(
    body: EmployeeCreate,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager")),
) -> dict:
    """Create an employee profile."""
    employee = EmployeeService(session).create(actor=user.username, **body.model_dump())
    return _employee_payload(employee)


@router.get("/employees")
def list_employees(
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer", "Manager")),
) -> list[dict]:
    """List employee profiles."""
    del user
    return [_employee_payload(e) for e in EmployeeService(session).list_employees()]


@router.get("/employees/{employee_id}")
def get_employee(
    employee_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Employees may only read their own profile; staff roles may read any."""
    employee = EmployeeService(session).get(employee_id)
    if user.app_role == "Employee" and user.employee_id != employee.id:
        from src.errors import AppError

        raise AppError("Forbidden", status_code=403)
    return _employee_payload(employee)


@router.patch("/employees/{employee_id}")
def update_employee(
    employee_id: int,
    body: EmployeeUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager")),
) -> dict:
    """Update an employee profile."""
    employee = EmployeeService(session).update(
        employee_id, actor=user.username, **body.model_dump(exclude_unset=True)
    )
    return _employee_payload(employee)


@router.delete("/employees/{employee_id}")
def delete_employee(
    employee_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin")),
) -> dict:
    """Delete an employee profile (Admin only)."""
    EmployeeService(session).delete(employee_id, actor=user.username)
    return {"ok": True}
