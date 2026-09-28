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

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from config.settings import settings
from database.base import get_session
from role_matrix.repository import RoleMatrixRepository
from role_matrix.service import RoleRequirementService
from src.auth.dependencies import get_current_user, require_role
from src.auth.models import User
from src.dashboards.service import DashboardService
from src.dashboards.progress_service import ProgressTrackingService
from src.documents.metrics import CorpusMetricsService
from src.documents.repository import DocumentRepository
from src.employees.service import EmployeeService, RoleService
from src.errors import AppError
from src.plans.models import (
    AssessmentRecord,
    ChecklistItemRecord,
    LearningModuleRecord,
    OnboardingPlan,
    TaskRecord,
)
from src.plans.repository import PlanRepository
from src.reviews.models import ValidationReportRecord
from src.reviews.service import ReviewService, ValidationReportRepository
from schemas.plan_schema import GeneratedPlan  # noqa: F401 — used via plan.structured_json

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
    employee_id: int | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Employee", "Admin", "Manager", "Training Manager")),
) -> HTMLResponse:
    """Employee dashboard with real progress, recommendations, and weak areas (Tasks 50, 53-56)."""
    svc = DashboardService(session)

    # Determine target employee ID
    target_emp_id = user.employee_id
    if user.app_role in ("Admin", "Manager", "Training Manager", "Reviewer") and employee_id:
        target_emp_id = employee_id
    elif not target_emp_id and user.app_role in ("Admin", "Manager", "Training Manager", "Reviewer"):
        first_plan = session.query(OnboardingPlan).first()
        if first_plan:
            target_emp_id = first_plan.employee_id
        else:
            first_emp = EmployeeService(session).list_employees()
            if first_emp:
                target_emp_id = first_emp[0].id

    employee = None
    if target_emp_id:
        employee = EmployeeService(session).get(target_emp_id)

    progress = svc.employee_progress(target_emp_id) if target_emp_id else None
    plan = svc.get_latest_plan(target_emp_id) if target_emp_id else None
    recommendations = svc.adaptive_recommendations(target_emp_id) if target_emp_id else []
    weak_areas = svc.weak_areas(target_emp_id) if target_emp_id else []

    # Parse structured_json for the tab panels
    plan_detail = None
    item_statuses: dict[str, str] = {}
    quiz_items: list[dict] = []
    if plan and plan.structured_json:
        try:
            from schemas.plan_schema import GeneratedPlan as GP
            plan_detail = GP.model_validate(plan.structured_json)
        except Exception:
            plan_detail = _StructuredProxy(plan.structured_json)
        item_statuses = _item_statuses(session, plan.id)
        quiz_items = ProgressTrackingService(session).get_sanitized_quiz_items(plan.id)

    plan_is_actionable = bool(
        plan
        and plan_detail
        and getattr(plan_detail, "generation_status", None) != "failed_after_retries"
    )

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
            "passing_score": 70,
            "item_statuses": item_statuses,
            "quiz_items": quiz_items,
            "plan_is_actionable": plan_is_actionable,
            "can_confirm_progress": user.app_role in {"Admin", "Training Manager", "Reviewer", "Manager"},
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
            "login_usernames": stats["login_usernames"],
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


@router.get("/employees/new", response_class=HTMLResponse)
def new_employee_page(
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager")),
) -> HTMLResponse:
    """Render the structured employee-profile form used before plan generation."""
    roles = RoleService(session).list_roles()
    return templates.TemplateResponse(
        request=request,
        name="employee_form.html",
        context={"user": user, "roles": roles},
    )


@router.get("/roles/new", response_class=HTMLResponse)
def new_role_page(
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager")),
) -> HTMLResponse:
    """Render guided creation of a job role and its source-linked requirements."""
    return templates.TemplateResponse(
        request=request,
        name="role_setup.html",
        context={
            "user": user,
            "roles": RoleService(session).list_roles(),
            "documents": DocumentRepository(session).list_active(),
            "drafts": RoleRequirementService(session).list_drafts(),
        },
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

    if user.app_role == "Employee" and user.employee_id != plan.employee_id:
        from src.errors import AppError

        raise AppError("Forbidden", status_code=403)

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
    plan_id: str | None = Query(None),
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer", "Manager")),
) -> HTMLResponse:
    """Human review queue page, optionally scoped to one employee plan."""
    parsed_plan_id = _optional_plan_id(plan_id)
    service = ReviewService(session)
    plans = sorted(PlanRepository(session).list_all(), key=lambda plan: plan.id, reverse=True)
    employee_labels = {
        employee.id: employee
        for employee in EmployeeService(session).list_employees()
    }
    plan_options = [
        {
            "id": plan.id,
            "label": (
                f"#{plan.id} — {employee_labels[plan.employee_id].name} "
                f"({employee_labels[plan.employee_id].employee_code})"
                if plan.employee_id in employee_labels
                else f"#{plan.id} — Employee #{plan.employee_id}"
            ),
        }
        for plan in plans
    ]
    queue = service.get_queue(plan_id=parsed_plan_id)
    return templates.TemplateResponse(
        request=request,
        name="review_queue.html",
        context={
            "user": user,
            "queue": [_review_queue_row(item) for item in queue],
            "plan_options": plan_options,
            "selected_plan_id": parsed_plan_id,
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _optional_plan_id(raw: str | None) -> int | None:
    """Treat a missing or blank filter as 'all plans' instead of a 422 JSON page."""
    if raw is None or not str(raw).strip():
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise AppError("plan_id must be a positive integer.", status_code=422) from exc
    if value <= 0:
        raise AppError("plan_id must be a positive integer.", status_code=422)
    return value


def _review_queue_row(item) -> dict:
    """Keep review-queue HTML small and attribute-safe."""
    row = item.to_dict()
    original = row.get("original_result") or {}
    if not isinstance(original, dict):
        original = {}
    row["original_result"] = {
        "item_id": original.get("item_id") or row.get("item_id"),
        "item_type": original.get("item_type") or row.get("item_type"),
        "verification_status": original.get("verification_status") or row.get("verification_status"),
        "details": original.get("details"),
        "source_references": original.get("source_references") or row.get("source_references") or [],
    }
    return row

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


def _item_statuses(session: Session, plan_id: int) -> dict[str, str]:
    """Read persisted item states for status badges; never infer completion."""
    records = (
        ("module", LearningModuleRecord, "module_id"),
        ("task", TaskRecord, "task_id"),
        ("checklist", ChecklistItemRecord, "item_id"),
        ("assessment", AssessmentRecord, "assessment_id"),
    )
    states: dict[str, str] = {}
    for item_type, model, identifier in records:
        for row in session.query(model).filter(model.plan_id == plan_id).all():
            payload = row.payload or {}
            item_id = payload.get(identifier)
            if item_id:
                states[f"{item_type}:{item_id}"] = payload.get("completion_status", "not_started")
    return states


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
