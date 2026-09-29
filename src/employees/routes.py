"""Employee and job-role CRUD API."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from database.base import get_session
from src.auth.dependencies import get_current_user, require_role
from src.auth.models import User
from src.auth.service import AuthService
from src.employees.service import EmployeeService, RoleService
from src.employees.import_service import EmployeeImportService

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
    create_login: bool = True
    login_username: str | None = None
    temporary_password: str | None = None

    @field_validator("login_username")
    @classmethod
    def normalise_login_username(cls, value: str | None) -> str | None:
        """Trim optional employee usernames before uniqueness is checked."""
        return value.strip() if value else None


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
    """Create an employee profile and its linked Employee login by default."""
    profile_fields = body.model_dump(
        exclude={"create_login", "login_username", "temporary_password"}
    )
    if body.temporary_password and len(body.temporary_password) < 8:
        from src.errors import AppError

        raise AppError("The temporary password must contain at least 8 characters.", status_code=422)

    employee = EmployeeService(session).create(actor=user.username, **profile_fields)
    payload = _employee_payload(employee)
    if body.create_login:
        account, initial_password = AuthService(session).provision_employee_account(
            employee,
            preferred_username=body.login_username,
            temporary_password=body.temporary_password,
            actor=user.username,
        )
        payload["login"] = {"username": account.username, "role": account.app_role}
        if initial_password:
            payload["initial_password"] = initial_password
    return payload


@router.post("/employees/import")
async def import_employees(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager")),
) -> dict:
    """Create one or more employee profiles from a CSV, XLSX, or JSON file."""
    importer = EmployeeImportService(session)
    employees = importer.import_file(
        file.filename or "employee-import",
        await file.read(),
        actor=user.username,
    )
    auth = AuthService(session)
    credentials = []
    for employee in employees:
        account, initial_password = auth.provision_employee_account(employee, actor=user.username)
        # This can also be a pre-existing employee profile that had no login
        # yet.  Show a secret only when this request actually set one.
        if initial_password:
            credentials.append(
                {
                    "employee_code": employee.employee_code,
                    "username": account.username,
                    "initial_password": initial_password,
                }
            )
    created = len(importer.last_created_codes)
    updated = len(importer.last_updated_codes)
    return {
        "created": created,
        "updated": updated,
        "processed": len(employees),
        "employees": [_employee_payload(employee) for employee in employees],
        "credentials": credentials,
        "message": f"Created {created} new employee profile(s) and updated {updated} existing profile(s).",
    }


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


@router.post("/employees/{employee_id}/account")
def provision_employee_login(
    employee_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager")),
) -> dict:
    """Create a missing Employee login for an existing profile."""
    employee = EmployeeService(session).get(employee_id)
    account, initial_password = AuthService(session).provision_employee_account(
        employee, actor=user.username
    )
    payload = {
        "employee_id": employee.id,
        "login": {"username": account.username, "role": account.app_role},
    }
    if initial_password:
        payload["initial_password"] = initial_password
    return payload


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
