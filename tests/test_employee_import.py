"""Employee-file import tests for supported formats and all-or-nothing validation."""

from __future__ import annotations

from datetime import date
from io import BytesIO
import json

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from database.base import get_session
from src.auth.service import AuthService
from src.employees.import_service import EmployeeImportService
from src.employees.service import EmployeeService, RoleService
from src.errors import AppError
from src.main import app


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


def test_json_import_accepts_utf8_bom_and_json_lines(session) -> None:
    """Large HR exports may be BOM-prefixed JSON Lines rather than an array."""
    role = RoleService(session).create("Support Agent", "Customer Support")
    raw = (
        f'{{"employee_code":"EMP-401","name":"Sam One","role_id":{role.id},"department":"Customer Support"}}\n'
        f'{{"employee_code":"EMP-402","name":"Sam Two","role_id":{role.id},"department":"Customer Support"}}\n'
    ).encode("utf-8-sig")

    employees = EmployeeImportService(session).import_file("new-hires.json", raw, actor="admin")

    assert [employee.employee_code for employee in employees] == ["EMP-401", "EMP-402"]


def test_json_import_accepts_comma_separated_objects_without_array(session) -> None:
    """Accept the common HR-export form ``{employee}, {employee}`` without brackets."""
    role = RoleService(session).create("QA Engineer", "Quality Assurance")
    raw = (
        f'''{{
  "employee_code": "EMP-QA-013",
  "name": "Kevin Hakim",
  "role_title": "QA Engineer",
  "department": "Quality Assurance",
  "required_competencies": ["Test Case Design", "Automated Testing"]
}},
{{
  "employee_code": "EMP-QA-014",
  "name": "Rakan Al-Malki",
  "role_title": "QA Engineer",
  "department": "Quality Assurance",
  "required_competencies": ["Bug Tracking", "Regression Testing"]
}}'''
    ).encode("utf-8")

    employees = EmployeeImportService(session).import_file("qa-employees.json", raw, actor="admin")

    assert [employee.employee_code for employee in employees] == ["EMP-QA-013", "EMP-QA-014"]
    assert employees[0].required_competencies == ["Test Case Design", "Automated Testing"]


def test_json_import_reads_a_thousand_employee_rows_before_validation(session) -> None:
    """A 1,000-row JSON array is a supported bulk-import size under 20 MB."""
    service = EmployeeImportService(session)
    raw = json.dumps(
        [
            {
                "employee_code": f"BULK-{number:04d}",
                "name": f"Bulk Employee {number}",
                "role_title": "Any Existing Role",
                "department": "Operations",
            }
            for number in range(1, 1001)
        ]
    ).encode("utf-8")

    rows = service._parse_file(".json", raw)

    assert len(rows) == 1000
    assert rows[0]["employee_code"] == "BULK-0001"
    assert rows[-1]["employee_code"] == "BULK-1000"


def test_json_import_rejects_a_truncated_bulk_file_without_importing_prefix(session) -> None:
    """A malformed tail must not turn a 1,000-row upload into a silent partial import."""
    role = RoleService(session).create("QA Engineer", "Quality Assurance")
    raw = (
        f'{{"employee_code":"EMP-QA-001","name":"One","role_id":{role.id},"department":"Quality Assurance"}},\n'
        f'{{"employee_code":"EMP-QA-002","name":"Two","role_id":{role.id},"department":"Quality Assurance"}},\n'
        '{"employee_code":"EMP-QA-003","name":"Broken"'
    ).encode("utf-8")

    with pytest.raises(AppError, match="incomplete or invalid"):
        EmployeeImportService(session).import_file("broken-bulk.json", raw, actor="admin")

    assert EmployeeService(session).list_employees() == []


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


def test_import_employees_endpoint_auto_provisions_logins(session) -> None:
    """The /api/employees/import endpoint auto-generates logins for all imported rows."""
    RoleService(session).create("Software Engineer", "Engineering")
    AuthService(session).create_user("admin-importer", "admin-password", "Admin")
    session.commit()

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        admin_token = client.post(
            "/api/login", json={"username": "admin-importer", "password": "admin-password"}
        ).json()["access_token"]

        csv_content = (
            "employee_code,name,role_title,department\n"
            "EMP-IMP-888,Tariq Omar,Software Engineer,Engineering\n"
        ).encode("utf-8")

        response = client.post(
            "/api/employees/import",
            headers={"Authorization": f"Bearer {admin_token}"},
            files={"file": ("import_test.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 1
        assert len(data["credentials"]) == 1
        cred = data["credentials"][0]
        assert cred["employee_code"] == "EMP-IMP-888"
        assert cred["username"] == "tariq-e"
        assert cred["initial_password"] == "SkillSprint!EMP-IMP-888"

        # Verify employee can authenticate immediately with auto-generated credentials
        login_res = client.post(
            "/api/login",
            json={"username": "tariq-e", "password": "SkillSprint!EMP-IMP-888"},
        )
        assert login_res.status_code == 200
        assert "access_token" in login_res.json()

        # Re-importing the same employee code updates the profile but never
        # resets or re-discloses an existing employee's password.
        repeat = client.post(
            "/api/employees/import",
            headers={"Authorization": f"Bearer {admin_token}"},
            files={"file": ("import_test.csv", csv_content, "text/csv")},
        )
        assert repeat.status_code == 200
        repeat_data = repeat.json()
        assert repeat_data["processed"] == 1
        assert repeat_data["created"] == 0
        assert repeat_data["updated"] == 1
        assert repeat_data["credentials"] == []
    finally:
        app.dependency_overrides.clear()

