"""HTTP API for Pipeline 1 plan generation and retrieval."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.base import get_session
from genai_pipeline.base_provider import BaseGenAIProvider
from src.auth.dependencies import get_current_user, require_role
from src.auth.models import User
from src.errors import AppError
from src.plans.dependencies import get_genai_provider
from src.plans.service import PlanGenerationService

router = APIRouter(prefix="/api/plans", tags=["plans"])


def _plan_payload(plan) -> dict:
    return {
        "id": plan.id,
        "employee_id": plan.employee_id,
        "role_id": plan.role_id,
        "generation_timestamp": plan.generation_timestamp.isoformat() if plan.generation_timestamp else None,
        "prompt_version": plan.prompt_version,
        "model_used": plan.model_used,
        "source_doc_versions": plan.source_doc_versions,
        "status": plan.status,
        "verification_status": plan.verification_status,
        "structured_json": plan.structured_json,
    }


@router.post("/generate/{employee_id}")
def generate_plan(
    employee_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager")),
    provider: BaseGenAIProvider = Depends(get_genai_provider),
) -> dict:
    """Generate a personalized onboarding plan for the employee (Pipeline 1)."""
    plan = PlanGenerationService(session, provider=provider).generate_for_employee(
        employee_id, actor=user.username
    )
    return _plan_payload(plan)


@router.get("/employee/{employee_id}")
def list_employee_plans(
    employee_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """List plans for an employee. Declared before /{plan_id} so 'employee' is not parsed as an id."""
    if user.app_role == "Employee" and user.employee_id != employee_id:
        raise AppError("Forbidden", status_code=403)
    service = PlanGenerationService(session)
    return [_plan_payload(plan) for plan in service.list_for_employee(employee_id)]


@router.get("/{plan_id}")
def get_plan(
    plan_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Return a stored plan. Employees may only read their own."""
    service = PlanGenerationService(session)
    plan = service.get_plan(plan_id)
    if user.app_role == "Employee" and user.employee_id != plan.employee_id:
        raise AppError("Forbidden", status_code=403)
    return _plan_payload(plan)
