"""Regression checks for the Git-tracked scalability seed snapshot."""

from database.current_demo_snapshot import load_current_workforce


def test_current_workforce_snapshot_supports_srs_employee_scale():
    workforce = load_current_workforce()
    employees = workforce["employees"]
    roles = workforce["roles"]

    assert len(employees) >= 1000
    assert len({employee["employee_code"] for employee in employees}) == len(employees)
    assert len({role["title"] for role in roles}) == len(roles)

    role_titles = {role["title"] for role in roles}
    assert all(employee["role_title"] in role_titles for employee in employees)
    assert all(employee["department"] and employee["name"] for employee in employees)
