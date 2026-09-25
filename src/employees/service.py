"""Employee and job-role CRUD services."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from config.logging_config import get_logger
from src.employees.models import Employee, EmployeeRole
from src.employees.repository import EmployeeRepository, RoleRepository
from src.errors import AppError
from src.reviews.repository import AuditRepository

logger = get_logger("employee_service")


class RoleService:
    """Create and list job roles used by the matrix and employee profiles."""

    def __init__(self, session: Session) -> None:
        self.roles = RoleRepository(session)
        self.audit = AuditRepository(session)

    def create(self, title: str, department: str, description: str | None = None) -> EmployeeRole:
        """Insert a job role if the title is not already taken."""
        if self.roles.get_by_title(title):
            raise AppError(f"Role already exists: {title}", status_code=409)
        role = EmployeeRole(title=title, department=department, description=description)
        self.roles.add(role)
        self.audit.record("system", "role_created", "role", title, {"department": department})
        logger.info("role_created title=%s department=%s", title, department)
        return role

    def list_roles(self) -> list[EmployeeRole]:
        """Return all job roles."""
        return self.roles.list_all()

    def get(self, role_id: int) -> EmployeeRole:
        """Fetch a role or raise 404."""
        role = self.roles.get(role_id)
        if role is None:
            raise AppError("Role not found", status_code=404)
        return role

    def ensure_role(self, title: str, department: str, description: str | None = None) -> EmployeeRole:
        """Idempotent create used by seeding."""
        existing = self.roles.get_by_title(title)
        if existing:
            return existing
        return self.create(title, department, description)


class EmployeeService:
    """Employee profile management with no extra PII fields."""

    def __init__(self, session: Session) -> None:
        self.employees = EmployeeRepository(session)
        self.roles = RoleRepository(session)
        self.audit = AuditRepository(session)

    def create(
        self,
        employee_code: str,
        name: str,
        role_id: int,
        department: str,
        experience_level: str = "Beginner",
        location: str | None = None,
        joining_date: date | None = None,
        reporting_manager: str | None = None,
        required_competencies: list | None = None,
        prior_experience: str | None = None,
        training_status: str = "not_started",
        actor: str = "system",
    ) -> Employee:
        """Create an employee assigned to an existing job role."""
        if self.employees.get_by_code(employee_code):
            raise AppError(f"Employee code already exists: {employee_code}", status_code=409)
        if self.roles.get(role_id) is None:
            raise AppError("Role not found", status_code=404)
        employee = Employee(
            employee_code=employee_code,
            name=name,
            role_id=role_id,
            department=department,
            experience_level=experience_level,
            location=location,
            joining_date=joining_date,
            reporting_manager=reporting_manager,
            required_competencies=required_competencies,
            prior_experience=prior_experience,
            training_status=training_status,
        )
        self.employees.add(employee)
        self.audit.record(actor, "employee_created", "employee", employee_code, {"role_id": role_id})
        logger.info("employee_created code=%s role_id=%s", employee_code, role_id)
        return employee

    def update(self, employee_id: int, actor: str = "system", **fields: object) -> Employee:
        """Patch allowed profile fields."""
        employee = self.get(employee_id)
        allowed = {
            "name",
            "role_id",
            "department",
            "experience_level",
            "location",
            "joining_date",
            "reporting_manager",
            "required_competencies",
            "prior_experience",
            "training_status",
        }
        for key, value in fields.items():
            if key in allowed and value is not None:
                setattr(employee, key, value)
        self.audit.record(actor, "employee_updated", "employee", employee.employee_code, {"fields": list(fields)})
        return employee

    def get(self, employee_id: int) -> Employee:
        """Fetch an employee or raise 404."""
        employee = self.employees.get(employee_id)
        if employee is None:
            raise AppError("Employee not found", status_code=404)
        return employee

    def list_employees(self) -> list[Employee]:
        """Return all employee profiles."""
        return self.employees.list_with_roles()

    def delete(self, employee_id: int, actor: str = "system") -> None:
        """Delete an employee profile."""
        employee = self.get(employee_id)
        code = employee.employee_code
        self.employees.delete(employee)
        self.audit.record(actor, "employee_deleted", "employee", code, None)
        logger.info("employee_deleted code=%s", code)
