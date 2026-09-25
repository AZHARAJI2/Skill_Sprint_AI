"""HTML dashboard skeleton that reads live database counts (not placeholder numbers)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from config.settings import settings
from database.base import get_session
from role_matrix.repository import RoleMatrixRepository
from src.auth.dependencies import get_current_user, require_role
from src.auth.models import User
from src.documents.metrics import CorpusMetricsService
from src.employees.service import EmployeeService, RoleService

router = APIRouter(tags=["dashboards"])
templates = Jinja2Templates(directory=str(settings.project_root / "templates"))


@router.get("/", response_class=HTMLResponse)
def root(request: Request) -> RedirectResponse:
    """Send anonymous visitors to login; authenticated users to /dashboard."""
    if not request.cookies.get("skillsprint_token"):
        return RedirectResponse(url="/login", status_code=303)
    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_router(request: Request, user: User = Depends(get_current_user)) -> RedirectResponse:
    """Dispatch to employee / admin / reviewer dashboards by RBAC role."""
    del request
    mapping = {
        "Employee": "/dashboard/employee",
        "Admin": "/dashboard/admin",
        "Training Manager": "/dashboard/admin",
        "Reviewer": "/dashboard/admin",
        "Manager": "/dashboard/role",
    }
    return RedirectResponse(url=mapping.get(user.app_role, "/dashboard/employee"), status_code=303)


@router.get("/dashboard/employee", response_class=HTMLResponse)
def employee_dashboard(
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Employee", "Admin", "Manager")),
) -> HTMLResponse:
    """Employee-facing skeleton showing assigned profile data when present."""
    employee = None
    if user.employee_id:
        employee = EmployeeService(session).get(user.employee_id)
    return templates.TemplateResponse(
        request=request,
        name="employee_dashboard.html",
        context={"user": user, "employee": employee},
    )


@router.get("/dashboard/admin", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer")),
) -> HTMLResponse:
    """Admin/training/reviewer skeleton with live corpus and matrix counts."""
    metrics = CorpusMetricsService(session).compute()
    employees = EmployeeService(session).list_employees()
    roles = RoleService(session).list_roles()
    matrix_count = RoleMatrixRepository(session).count()
    return templates.TemplateResponse(
        request=request,
        name="admin_dashboard.html",
        context={
            "user": user,
            "metrics": metrics,
            "employee_count": len(employees),
            "role_count": len(roles),
            "matrix_count": matrix_count,
        },
    )


@router.get("/dashboard/role", response_class=HTMLResponse)
def role_dashboard(
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Manager", "Admin", "Training Manager")),
) -> HTMLResponse:
    """Role dashboard skeleton with per-role employee counts from the live database."""
    roles = RoleService(session).list_roles()
    employees = EmployeeService(session).list_employees()
    by_role = []
    for role in roles:
        count = sum(1 for emp in employees if emp.role_id == role.id)
        by_role.append({"title": role.title, "department": role.department, "employees": count})
    return templates.TemplateResponse(
        request=request,
        name="role_dashboard.html",
        context={"user": user, "by_role": by_role},
    )


@router.get("/documents/upload", response_class=HTMLResponse)
def upload_page(
    request: Request,
    user: User = Depends(require_role("Admin", "Training Manager")),
) -> HTMLResponse:
    """Document upload form."""
    return templates.TemplateResponse(
        request=request,
        name="document_upload.html",
        context={"user": user},
    )
