"""Employee-file import tests for supported formats and all-or-nothing validation."""

from __future__ import annotations

from datetime import date
from io import BytesIO

import pytest
from openpyxl import Workbook

from src.employees.import_service import EmployeeImportService
from src.employees.service import EmployeeService, RoleService
from src.errors import AppError


def test_csv_import_resolves_role_title_and_creates_profiles(session) -> None:
    """CSV rows create onboarding profiles through the employee service."""
    RoleService(session).create("Software Engineer", "Engineering")
    raw = (
        "employee_code,name,role_title,department,experience_level,required_competencies,joining_date\n"
        "EMP-101,Ada Lovelace,Software Engineer,Engineering,Intermediate,Security Awareness;Git Basics,2026-10-01\n"
    ).encode()

    employees = EmployeeImportService(session).import_file("new-hires.csv", raw, actor="admin")

    assert len(employees) == 1
    assert employees[0].employee_code == "EMP-101"
    assert employees[0].required_competencies == ["Security Awareness", "Git Basics"]
    assert employees[0].joining_date.isoformat() == "2026-10-01"


def test_json_import_rejects_invalid_row_without_partial_creation(session) -> None:
    """A bad row leaves even otherwise-valid rows out of the database."""
    role = RoleService(session).create("Recruiter", "People & Culture")
    raw = (
        "["
        '{"employee_code":"EMP-201","name":"Grace Hopper","role_id":%s,"department":"People & Culture"},'
        '{"employee_code":"EMP-202","name":"Invalid Role","role_title":"Unknown","department":"People & Culture"}'
        "]"
    ) % role.id

    with pytest.raises(AppError) as exc:
        EmployeeImportService(session).import_file("new-hires.json", raw.encode(), actor="admin")

    assert exc.value.status_code == 422
    assert exc.value.details["rows"][0]["row"] == 3
    assert EmployeeService(session).list_employees() == []


def test_json_import_accepts_one_employee_object(session) -> None:
    """A single JSON object is accepted for the one-employee import workflow."""
    role = RoleService(session).create("QA Engineer", "Engineering")
    raw = (
        '{"employee_code":"EMP-250","name":"Margaret Hamilton",'
        f'"role_id":{role.id},"department":"Engineering"}}'
    ).encode()

    employees = EmployeeImportService(session).import_file("one-employee.json", raw, actor="admin")

    assert [employee.employee_code for employee in employees] == ["EMP-250"]


def test_xlsx_import_accepts_first_worksheet(session) -> None:
    """XLSX imports use the first sheet and its header row."""
    role = RoleService(session).create("Financial Analyst", "Finance")
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["employee_code", "name", "role_id", "department", "joining_date"])
    sheet.append(["EMP-301", "Katherine Johnson", role.id, "Finance", date(2026, 10, 2)])
    stream = BytesIO()
    workbook.save(stream)

    employees = EmployeeImportService(session).import_file("new-hires.xlsx", stream.getvalue(), actor="admin")

    assert [employee.employee_code for employee in employees] == ["EMP-301"]
