"""HTML dashboard routes — Phase 4, Tasks 50-56.

Serves three role-specific dashboards (Employee / Admin / Role) with live data
from DashboardService.  All context variables are computed from real DB rows.

Routes
------
GET /              → redirect based on auth state
GET /dashboard     → dispatch to role-specific dashboard
GET /dashboard/employee
GET /dashboard/admin
GET /dashboard/role
GET /documents/upload
GET /plans/{plan_id}   → full plan detail view
GET /reviews           → review queue HTML
"""

from __future__ import annotations

import json
from collections import defaultdict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from config.settings import settings
from database.base import get_session
from role_matrix.repository import RoleMatrixRepository
from src.auth.dependencies import get_current_user, require_role
from src.auth.models import User
from src.dashboards.service import DashboardService
from src.documents.metrics import CorpusMetricsService
from src.employees.service import EmployeeService, RoleService
from src.plans.models import OnboardingPlan
from src.plans.repository import PlanRepository
from src.reviews.models import ValidationReportRecord
from src.reviews.service import ReviewService, ValidationReportRepository
from src.schemas import GeneratedPlan  # noqa: F401 — used via plan.structured_json

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
    """Employee dashboard with real progress, recommendations, and weak areas (Tasks 50, 53-56)."""
    svc = DashboardService(session)
    employee = None
    if user.employee_id:
        employee = EmployeeService(session).get(user.employee_id)

    progress = svc.employee_progress(user.employee_id) if user.employee_id else None
    plan = svc.get_latest_plan(user.employee_id) if user.employee_id else None
    recommendations = svc.adaptive_recommendations(user.employee_id) if user.employee_id else []
    weak_areas = svc.weak_areas(user.employee_id) if user.employee_id else []

    # Parse structured_json for the tab panels
    plan_detail = None
    if plan and plan.structured_json:
        try:
            from schemas.plan_schema import GeneratedPlan as GP
            plan_detail = GP.model_validate(plan.structured_json)
        except Exception:
            plan_detail = _StructuredProxy(plan.structured_json)

    return templates.TemplateResponse(
        request=request,
        name="employee_dashboard.html",
        context={
            "user": user,
            "employee": employee,
            "progress": progress or _empty_progress(),
            "plan": plan,
            "plan_detail": plan_detail,
            "recommendations": [{"type": r.type, "message": r.message, "priority": r.priority} for r in recommendations],
            "weak_areas": [{"topic": w.topic, "score": w.score} for w in weak_areas],
        },
    )


@router.get("/dashboard/admin", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer")),
) -> HTMLResponse:
    """Admin dashboard with live corpus metrics, coverage, flagged content (Tasks 51, 53)."""
    svc = DashboardService(session)
    metrics = CorpusMetricsService(session).compute()
    stats = svc.admin_stats()

    return templates.TemplateResponse(
        request=request,
        name="admin_dashboard.html",
        context={
            "user": user,
            "metrics": metrics,
            "employee_count": stats["employee_count"],
            "role_count": stats["role_count"],
            "matrix_count": RoleMatrixRepository(session).count(),
            "plan_count": stats["plan_count"],
            "pending_reviews": stats["pending_reviews"],
            "flagged_hallucinations": stats["flagged_hallucinations"],
            "flagged_contradictions": stats["flagged_contradictions"],
            "coverage_by_role": [
                {"role": r.role, "pct": r.pct} for r in stats["coverage_by_role"]
            ],
            "employees": stats["employees"],
            "plan_ids": stats["plan_ids"],
        },
    )


@router.get("/dashboard/role", response_class=HTMLResponse)
def role_dashboard(
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Manager", "Admin", "Training Manager")),
) -> HTMLResponse:
    """Role dashboard with per-role requirement completion stats (Task 52)."""
    svc = DashboardService(session)
    rows = svc.role_dashboard_rows()

    # Department grouping for breakdown section
    by_department: dict[str, list] = defaultdict(list)
    for row in rows:
        by_department[row.department].append({"title": row.title, "employees": row.employees})

    # Plotly pie chart data
    labels = [r.title for r in rows if r.employees > 0] or [r.title for r in rows[:5]]
    values = [r.employees for r in rows if r.employees > 0] or [1] * len(rows[:5])

    return templates.TemplateResponse(
        request=request,
        name="role_dashboard.html",
        context={
            "user": user,
            "by_role": [
                {
                    "title": r.title,
                    "department": r.department,
                    "employees": r.employees,
                    "matrix_count": r.matrix_count,
                    "mandatory_count": r.mandatory_count,
                    "coverage_pct": r.coverage_pct,
                }
                for r in rows
            ],
            "by_department": dict(by_department),
            "role_chart_json": json.dumps({"labels": labels, "values": values}),
        },
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


@router.get("/plans/{plan_id}", response_class=HTMLResponse)
def plan_view(
    plan_id: int,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer", "Manager", "Employee")),
) -> HTMLResponse:
    """Full plan detail view with tabbed modules/tasks/checklists/quizzes/assessments."""
    plan: OnboardingPlan | None = session.query(OnboardingPlan).get(plan_id)
    if plan is None:
        return templates.TemplateResponse(
            request=request, name="plan_view.html",
            context={"user": user, "plan": None, "detail": None, "validation": None},
        )

    detail = None
    if plan.structured_json:
        try:
            from schemas.plan_schema import GeneratedPlan as GP
            detail = GP.model_validate(plan.structured_json)
        except Exception:
            detail = _StructuredProxy(plan.structured_json)

    validation = ValidationReportRepository(session).get_by_plan(plan_id)

    return templates.TemplateResponse(
        request=request,
        name="plan_view.html",
        context={
            "user": user,
            "plan": plan,
            "detail": detail,
            "validation": validation,
        },
    )


@router.get("/reviews", response_class=HTMLResponse)
def review_queue_page(
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer", "Manager")),
) -> HTMLResponse:
    """Human review queue page (Tasks 48-49)."""
    service = ReviewService(session)
    queue = service.get_queue()
    return templates.TemplateResponse(
        request=request,
        name="review_queue.html",
        context={"user": user, "queue": [item.to_dict() for item in queue]},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_progress():
    """Return a zero-filled ProgressData-like namespace for un-linked users."""
    class _P:
        overall_pct = 0
        status = "Not Started"
        modules_done = modules_total = 0
        tasks_done = tasks_total = 0
        checklists_done = checklists_total = 0
        quizzes_done = quizzes_total = 0
        avg_quiz_score = 0
        assessments_done = assessments_total = 0
    return _P()


class _StructuredProxy:
    """Lightweight proxy so templates can access plan data when Pydantic parsing fails."""

    def __init__(self, data: dict) -> None:
        self._data = data or {}

    @property
    def modules(self):
        return [_DictProxy(m) for m in self._data.get("modules", [])]

    @property
    def tasks(self):
        return [_DictProxy(t) for t in self._data.get("tasks", [])]

    @property
    def checklists(self):
        return [_DictProxy(c) for c in self._data.get("checklists", [])]

    @property
    def quizzes(self):
        return [_DictProxy(q) for q in self._data.get("quizzes", [])]

    @property
    def assessments(self):
        return [_DictProxy(a) for a in self._data.get("assessments", [])]


class _DictProxy:
    """Proxy a dict as object attributes for template access."""

    def __init__(self, data: dict) -> None:
        self._d = data or {}

    def __getattr__(self, name: str):
        return self._d.get(name, "")
