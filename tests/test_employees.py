"""Employee and job-role CRUD tests (VG-1.5)."""

from __future__ import annotations

from datetime import date

import pytest

from src.employees.service import EmployeeService, RoleService
from src.errors import AppError


def test_employee_crud_for_all_ten_roles(session) -> None:
    """VG-1.5: profiles can be created for each of the 10 NovaCart job roles."""
    roles = [
        ("Software Engineer", "Engineering"),
        ("DevOps/Infrastructure Engineer", "Engineering"),
        ("QA Engineer", "Engineering"),
        ("Customer Support Representative", "Customer Support"),
        ("Payments Operations Specialist", "Finance"),
        ("HR Generalist", "People & Culture"),
        ("Recruiter", "People & Culture"),
        ("Financial Analyst", "Finance"),
        ("Accounts Payable Clerk", "Finance"),
        ("Warehouse Operations Coordinator", "Warehouse"),
    ]
    role_service = RoleService(session)
    employee_service = EmployeeService(session)
    created_roles = [role_service.create(title, dept) for title, dept in roles]
    assert len(role_service.list_roles()) == 10
    for index, role in enumerate(created_roles, start=1):
        employee_service.create(
            employee_code=f"E{index:03d}",
            name=f"Person {index}",
            role_id=role.id,
            department=role.department,
            experience_level="Intermediate",
            location="Amman",
            joining_date=date(2026, 9, 1),
            reporting_manager="Lead",
            required_competencies=["Policy Awareness"],
            prior_experience="Prior ops work",
            training_status="not_started",
        )
    assert len(employee_service.list_employees()) == 10
    first = employee_service.list_employees()[0]
    employee_service.update(first.id, name="Updated Name", training_status="in_progress")
    assert employee_service.get(first.id).name == "Updated Name"
    employee_service.delete(first.id)
    assert len(employee_service.list_employees()) == 9


def test_duplicate_role_rejected(session) -> None:
    """Role titles are unique."""
    RoleService(session).create("Recruiter", "People & Culture")
    with pytest.raises(AppError) as exc:
        RoleService(session).create("Recruiter", "People & Culture")
    assert exc.value.status_code == 409
