"""Employee and job-role CRUD tests (VG-1.5)."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from database.base import get_session
from src.auth.service import AuthService
from src.employees.service import EmployeeService, RoleService
from src.errors import AppError
from src.main import app


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


def test_admin_can_create_a_linked_employee_login(session) -> None:
    """A new employee can receive an Employee-only account linked to their profile."""
    role = RoleService(session).create("Support Specialist", "Support")
    AuthService(session).create_user("admin-user", "admin-password", "Admin")
    session.commit()

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        admin_token = client.post(
            "/api/login", json={"username": "admin-user", "password": "admin-password"}
        ).json()["access_token"]
        response = client.post(
            "/api/employees",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "employee_code": "EMP-ACCESS-001",
                "name": "Employee With Access",
                "role_id": role.id,
                "department": "Support",
                "create_login": True,
                "login_username": "employee.access",
                "temporary_password": "safe-pass-123",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["login"] == {"username": "employee.access", "role": "Employee"}
        assert "temporary_password" not in body

        employee_token = client.post(
            "/api/login", json={"username": "employee.access", "password": "safe-pass-123"}
        ).json()["access_token"]
        identity = client.get("/api/me", headers={"Authorization": f"Bearer {employee_token}"})
        assert identity.json()["employee_id"] == body["id"]
    finally:
        app.dependency_overrides.clear()


def test_existing_employee_can_receive_a_login_later(session) -> None:
    """Profiles created without a login can be given username/password access later."""
    role = RoleService(session).create("Warehouse Clerk", "Warehouse")
    employee = EmployeeService(session).create(
        employee_code="EMP-LOGIN-002",
        name="Later Access",
        role_id=role.id,
        department="Warehouse",
        experience_level="Beginner",
        actor="admin-user",
    )
    AuthService(session).create_user("admin-user", "admin-password", "Admin")
    session.commit()

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        admin_token = client.post(
            "/api/login", json={"username": "admin-user", "password": "admin-password"}
        ).json()["access_token"]
        response = client.post(
            f"/api/employees/{employee.id}/account",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["login"]["role"] == "Employee"
        assert body["initial_password"].startswith("SkillSprint!")
        employee_token = client.post(
            "/api/login",
            json={"username": body["login"]["username"], "password": body["initial_password"]},
        ).json()["access_token"]
        identity = client.get("/api/me", headers={"Authorization": f"Bearer {employee_token}"})
        assert identity.json()["employee_id"] == employee.id
    finally:
        app.dependency_overrides.clear()


def test_new_employee_auto_generates_username_and_password(session) -> None:
    """When creating an employee without manual credentials, username and password are auto-generated."""
    role = RoleService(session).create("Security Specialist", "Cybersecurity")
    AuthService(session).create_user("admin-tester", "admin-password", "Admin")
    session.commit()

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        admin_token = client.post(
            "/api/login", json={"username": "admin-tester", "password": "admin-password"}
        ).json()["access_token"]
        response = client.post(
            "/api/employees",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "employee_code": "EMP-AUTO-777",
                "name": "Sarah Connor",
                "role_id": role.id,
                "department": "Cybersecurity",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "login" in body
        assert body["login"]["username"] == "sarah-c"
        assert body["initial_password"] == "SkillSprint!EMP-AUTO-777"

        # Verify the employee can authenticate with these auto-generated credentials
        employee_token = client.post(
            "/api/login", json={"username": "sarah-c", "password": "SkillSprint!EMP-AUTO-777"}
        ).json()["access_token"]
        identity = client.get("/api/me", headers={"Authorization": f"Bearer {employee_token}"})
        assert identity.json()["employee_id"] == body["id"]
    finally:
        app.dependency_overrides.clear()

