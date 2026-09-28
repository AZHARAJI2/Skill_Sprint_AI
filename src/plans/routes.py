"""HTTP API for Pipeline 1 plan generation and retrieval."""

from __future__ import annotations

import copy
from typing import Any

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.base import get_session
from genai_pipeline.base_provider import BaseGenAIProvider
from src.auth.dependencies import get_current_user, require_role
from src.auth.models import User
from src.errors import AppError
from src.plans.dependencies import get_genai_provider
from src.plans.service import PlanGenerationService
from src.plans.validation_service import PlanValidationService
from src.dashboards.progress_service import ProgressTrackingService

router = APIRouter(prefix="/api/plans", tags=["plans"])


class QuizSubmission(BaseModel):
    """Answers submitted by the employee for one plan-level quiz attempt."""

    answers: dict[str, Any]


class QuizCheckRequest(BaseModel):
    """Single-question answer check payload."""

    question_id: str
    selected: Any  # str for SC/TF, list[str] for MR


class CompletionConfirmation(BaseModel):
    """Manager or reviewer decision for a practical completion request."""

    confirmed: bool
    comment: str = ""


def _assert_plan_access(plan, user: User) -> None:
    """Enforce employee ownership while allowing authorized training staff."""
    if user.app_role == "Employee" and user.employee_id != plan.employee_id:
        raise AppError("Forbidden", status_code=403)


def _plan_payload(plan, *, include_quiz_answers: bool = True) -> dict:
    """Serialize a plan, withholding quiz answer keys for employee readers."""
    structured_json = copy.deepcopy(plan.structured_json)
    if not include_quiz_answers and structured_json:
        for question in structured_json.get("quizzes", []):
            question.pop("correct_answer", None)
            question.pop("explanation", None)
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
        "structured_json": structured_json,
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
    include_answers = user.app_role != "Employee"
    return [
        _plan_payload(plan, include_quiz_answers=include_answers)
        for plan in service.list_for_employee(employee_id)
    ]


@router.get("/{plan_id}")
def get_plan(
    plan_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Return a stored plan. Employees may only read their own."""
    service = PlanGenerationService(session)
    plan = service.get_plan(plan_id)
    _assert_plan_access(plan, user)
    return _plan_payload(plan, include_quiz_answers=user.app_role != "Employee")


@router.get("/{plan_id}/progress")
def plan_progress(
    plan_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Return progress calculated only from persisted completion and quiz data."""
    plan = PlanGenerationService(session).get_plan(plan_id)
    _assert_plan_access(plan, user)
    progress = ProgressTrackingService(session).compute_employee_progress(plan.employee_id)
    return progress.__dict__


@router.get("/{plan_id}/quiz")
def plan_quiz(
    plan_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """Return quiz questions without answers or explanations before submission."""
    plan = PlanGenerationService(session).get_plan(plan_id)
    _assert_plan_access(plan, user)
    return ProgressTrackingService(session).get_sanitized_quiz_items(plan_id)


@router.post("/{plan_id}/quiz/submit")
def submit_plan_quiz(
    plan_id: int,
    submission: QuizSubmission,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Grade an employee quiz on the server and record an auditable result."""
    plan = PlanGenerationService(session).get_plan(plan_id)
    _assert_plan_access(plan, user)
    if user.app_role == "Employee" and plan.employee_id != user.employee_id:
        raise AppError("Forbidden", status_code=403)
    return ProgressTrackingService(session).grade_quiz(plan_id, submission.answers, actor=user.username)


@router.post("/{plan_id}/quiz/check")
def check_quiz_answer(
    plan_id: int,
    body: QuizCheckRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Validate a single quiz question and return correctness + explanation.

    Powers the interactive per-question feedback in the employee dashboard.
    The answer key is fetched from the DB on demand, never preloaded in the page.
    """
    plan = PlanGenerationService(session).get_plan(plan_id)
    _assert_plan_access(plan, user)
    try:
        return ProgressTrackingService(session).check_single_answer(
            plan_id, body.question_id, body.selected
        )
    except ValueError as exc:
        raise AppError(str(exc), status_code=404) from exc


@router.post("/{plan_id}/items/{item_type}/{item_id}/complete")
def complete_plan_item(
    plan_id: int,
    item_type: str,
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Persist employee completion; practical work is routed for confirmation."""
    plan = PlanGenerationService(session).get_plan(plan_id)
    _assert_plan_access(plan, user)
    if user.app_role not in {"Employee", "Admin", "Training Manager", "Manager"}:
        raise AppError("Forbidden for this role", status_code=403)
    if (plan.structured_json or {}).get("generation_status") == "failed_after_retries":
        raise AppError("This fallback plan must be approved before employees can record progress.", status_code=409)
    service = ProgressTrackingService(session)
    blocked, reason = service.check_prerequisites(item_type, item_id, plan_id)
    if blocked:
        raise AppError(reason, status_code=409)
    return service.record_item_completion(plan_id, item_type, item_id, actor=user.username)


@router.post("/{plan_id}/items/{item_type}/{item_id}/confirm")
def confirm_plan_item(
    plan_id: int,
    item_type: str,
    item_id: str,
    decision: CompletionConfirmation,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer", "Manager")),
) -> dict:
    """Store a manager/reviewer confirmation or rejection with an audit entry."""
    plan = PlanGenerationService(session).get_plan(plan_id)
    return ProgressTrackingService(session).confirm_item_completion(
        plan_id,
        item_type,
        item_id,
        reviewer_name=user.username,
        confirmed=decision.confirmed,
        comment=decision.comment,
    )


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
