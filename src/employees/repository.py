"""Repositories for employees and job roles."""

from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from database.base import BaseRepository
from src.employees.models import Employee, EmployeeRole


class RoleRepository(BaseRepository[EmployeeRole]):
    """Data access for job roles."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, EmployeeRole)

    def get_by_title(self, title: str) -> EmployeeRole | None:
        """Fetch a role by exact title."""
        return self.session.query(EmployeeRole).filter(EmployeeRole.title == title).one_or_none()


class EmployeeRepository(BaseRepository[Employee]):
    """Data access for employee profiles."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Employee)

    def get_by_code(self, employee_code: str) -> Employee | None:
        """Fetch an employee by business identifier."""
        return self.session.query(Employee).filter(Employee.employee_code == employee_code).one_or_none()

    def list_by_role_id(self, role_id: int) -> list[Employee]:
        """List employees assigned to a job role."""
        return list(self.session.query(Employee).filter(Employee.role_id == role_id).all())

    def list_with_roles(self) -> list[Employee]:
        """Return employees with job-role relationship loaded."""
        return list(self.session.query(Employee).options(joinedload(Employee.role)).all())
