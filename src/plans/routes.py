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
from src.plans.validation_service import PlanValidationService

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


def _validation_payload(report) -> dict:
    """Serialize a persisted Pipeline 2 report without exposing ORM details."""
    return {
        "plan_id": report.plan_id,
        "coverage_score": report.coverage_score,
        "traceability_score": report.traceability_score,
        "consistency_score": report.consistency_score,
        "missing_count": report.missing_count,
        "unsupported_count": report.unsupported_count,
        "contradiction_count": report.contradiction_count,
        "overall_status": report.overall_status,
    }


@router.post("/generate/{employee_id}")
def generate_plan(
    employee_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager")),
    provider: BaseGenAIProvider = Depends(get_genai_provider),
) -> dict:
    """Generate, validate, and persist a personalized onboarding plan.

    Pipeline 1 is the only GenAI stage.  Pipeline 2 runs immediately afterwards
    using deterministic Python validators, so the UI never treats raw model
    output as approved training content.
    """
    plan = PlanGenerationService(session, provider=provider).generate_for_employee(
        employee_id, actor=user.username
    )
    validation = PlanValidationService(session).validate(plan.id, actor=user.username)
    payload = _plan_payload(plan)
    payload["validation"] = _validation_payload(validation)
    return payload


@router.post("/{plan_id}/validate")
def validate_plan(
    plan_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer")),
) -> dict:
    """Re-run Pipeline 2 only; this endpoint never makes a GenAI call."""
    report = PlanValidationService(session).validate(plan_id, actor=user.username)
    return _validation_payload(report)


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


# ---------------------------------------------------------------------------
# Phase 4 — Policy update detection & selective regeneration (Tasks 57-59)
# ---------------------------------------------------------------------------

@router.get("/policy-impact/{document_id}", summary="Impact analysis for a document update")
def policy_impact(
    document_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager")),
) -> dict:
    """Return all plans and items affected by a change to the given document (Task 57-58)."""
    from src.plans.policy_update import PolicyUpdateService
    impact = PolicyUpdateService(session).analyse_impact(document_id)
    return {
        "document_id": impact.document_id,
        "old_version": impact.old_version,
        "new_version": impact.new_version,
        "affected_plan_ids": impact.affected_plan_ids,
        "total_affected": impact.total_affected,
        "analysis_timestamp": impact.analysis_timestamp,
        "affected_items": [
            {
                "item_id": i.item_id,
                "item_type": i.item_type,
                "plan_id": i.plan_id,
                "source_document_id": i.source_document_id,
                "source_section_id": i.source_section_id,
                "title": i.title,
            }
            for i in impact.affected_items
        ],
    }


@router.post("/selective-regenerate/{document_id}", summary="Request selective regeneration")
def selective_regenerate(
    document_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager")),
) -> dict:
    """Mark only affected items for regeneration when a source document changes (Task 59)."""
    from src.plans.policy_update import PolicyUpdateService
    impact = PolicyUpdateService(session).request_selective_regeneration(
        document_id, actor=user.username
    )
    return {
        "document_id": impact.document_id,
        "affected_plan_ids": impact.affected_plan_ids,
        "total_affected": impact.total_affected,
        "message": (
            f"{impact.total_affected} items marked for selective regeneration "
            f"across {len(impact.affected_plan_ids)} plan(s)."
        ),
    }
