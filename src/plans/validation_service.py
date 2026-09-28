"""Persisted orchestration for the independent, pure-Python plan validation pipeline."""

from __future__ import annotations

from sqlalchemy.orm import Session

from python_validation.pipeline import ValidationPipeline
from role_matrix.repository import RoleMatrixRepository
from src.documents.repository import ChunkRepository, DocumentRepository
from src.employees.service import EmployeeService
from src.errors import AppError
from src.plans.repository import PlanRepository
from src.reviews.models import ValidationReportRecord
from src.reviews.repository import AuditRepository


class PlanValidationService:
    """Run Pipeline 2 for a stored plan and persist its verification evidence.

    This service deliberately imports no GenAI provider.  It supplies the stored
    role matrix and document corpus to the deterministic validation pipeline,
    records the resulting report, and updates only the plan lifecycle metadata.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.plans = PlanRepository(session)
        self.employees = EmployeeService(session)
        self.matrix = RoleMatrixRepository(session)
        self.documents = DocumentRepository(session)
        self.chunks = ChunkRepository(session)
        self.audit = AuditRepository(session)

    _REVIEW_REQUIRED_STATUSES = {
        "Source Support Missing",
        "Requirement Missing",
        "Unsupported Requirement",
        "Outdated Source",
        "Contradiction Detected",
        "Manual Review Required",
        "Partially Verified",
    }

    def validate(self, plan_id: int, actor: str = "system") -> ValidationReportRecord:
        """Validate one generated plan and store the resulting report.

        Args:
            plan_id: Persisted onboarding plan identifier.
            actor: Authenticated user or system identity recorded in the audit log.

        Returns:
            The saved validation report.

        Raises:
            AppError: If the plan is missing or has no structured payload.
        """
        plan = self.plans.get(plan_id)
        if plan is None:
            raise AppError("Plan not found", status_code=404)
        if not plan.structured_json:
            raise AppError("Plan structured JSON is not available for validation", status_code=400)

        employee = self.employees.get(plan.employee_id)
        if employee.role is None:
            raise AppError("Employee has no job role assigned", status_code=400)

        report = ValidationPipeline().run(
            plan.structured_json,
            matrix=self.matrix.get_by_role(employee.role.title),
            documents=self.documents.list_active(),
            chunks=self.chunks.list_unique_sections(),
            plan_id=plan.id,
        )
        report_payload = report.model_dump(mode="json")
        stored = ValidationReportRecord(
            plan_id=plan.id,
            coverage_score=report.coverage_score,
            traceability_score=report.traceability_score,
            consistency_score=report.consistency_score,
            missing_count=report.missing_count,
            unsupported_count=report.unsupported_count,
            contradiction_count=report.contradiction_count,
            overall_status=report.overall_status.value if report.overall_status else None,
            payload=report_payload,
        )
        self.session.add(stored)

        plan.verification_status = stored.overall_status
        plan.status = (
            "manual_review"
            if stored.overall_status in self._REVIEW_REQUIRED_STATUSES
            else "validated"
        )
        self.audit.record(
            actor,
            "plan_validated",
            "onboarding_plan",
            str(plan.id),
            {
                "overall_status": stored.overall_status,
                "coverage_score": stored.coverage_score,
                "traceability_score": stored.traceability_score,
                "missing_count": stored.missing_count,
                "unsupported_count": stored.unsupported_count,
                "contradiction_count": stored.contradiction_count,
            },
        )
        self.session.flush()
        return stored
