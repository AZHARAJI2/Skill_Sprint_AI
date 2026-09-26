"""Phase 3 validation rule: Flag plans with items that failed GenAI generation after retries."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from schemas.common_schema import VerificationStatus
from schemas.plan_schema import GeneratedPlan
from schemas.validation_schema import ItemValidationResult, ValidationReport


class BaseValidator(ABC):
    """Abstract base for all Pipeline 2 validation rules."""

    @abstractmethod
    def validate(
        self,
        plan: GeneratedPlan | dict[str, Any],
        matrix: list[Any] | None = None,
        documents: list[Any] | None = None,
        chunks: list[Any] | None = None,
    ) -> list[ItemValidationResult]:
        """Run validation rule and return item-level validation results."""


class GenerationFailureValidator(BaseValidator):
    """Deterministic Phase 3 validator.

    Forces overall plan verification_status to 'Manual Review Required'
    if any item in the plan has generation_status == 'failed_after_retries'.
    """

    def validate(
        self,
        plan: GeneratedPlan | dict[str, Any],
        matrix: list[Any] | None = None,
        documents: list[Any] | None = None,
        chunks: list[Any] | None = None,
    ) -> list[ItemValidationResult]:
        payload = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else plan
        results: list[ItemValidationResult] = []

        item_sections = [
            ("modules", "learning_module", "module_id"),
            ("checklists", "checklist_item", "item_id"),
            ("tasks", "task_item", "task_id"),
            ("quizzes", "quiz_question", "question_id"),
            ("assessments", "assessment", "assessment_id"),
        ]

        for section_key, item_type, id_field in item_sections:
            for item in payload.get(section_key, []):
                gen_status = item.get("generation_status")
                title_or_desc = (
                    item.get("title")
                    or item.get("activity")
                    or item.get("description")
                    or item.get("question_text")
                    or ""
                )
                if gen_status == "failed_after_retries" or "[UNGENERATED - PENDING REVIEW]" in title_or_desc:
                    item_id = str(item.get(id_field, "UNKNOWN"))
                    results.append(
                        ItemValidationResult(
                            item_id=item_id,
                            item_type=item_type,
                            verification_status=VerificationStatus.MANUAL_REVIEW_REQUIRED,
                            details="Item failed GenAI generation after retries and requires manual review.",
                            source_references=[
                                f"{item.get('source_document_id', '')}§{item.get('source_section_id', '')}"
                            ],
                        )
                    )

        return results


class ValidationPipeline:
    """Composes and runs all validators in sequence."""

    def __init__(self, validators: list[BaseValidator] | None = None) -> None:
        self.validators = validators or [
            GenerationFailureValidator(),
        ]

    def run(
        self,
        plan: GeneratedPlan | dict[str, Any],
        matrix: list[Any] | None = None,
        documents: list[Any] | None = None,
        chunks: list[Any] | None = None,
        plan_id: int = 1,
    ) -> ValidationReport:
        all_results: list[ItemValidationResult] = []
        for validator in self.validators:
            res = validator.validate(plan, matrix=matrix, documents=documents, chunks=chunks)
            if isinstance(res, list):
                all_results.extend(res)
            elif res is not None:
                all_results.append(res)

        overall = VerificationStatus.VERIFIED
        for r in all_results:
            if r.verification_status == VerificationStatus.MANUAL_REVIEW_REQUIRED:
                overall = VerificationStatus.MANUAL_REVIEW_REQUIRED
                break

        return ValidationReport(
            plan_id=plan_id,
            per_item_results=all_results,
            overall_status=overall,
        )
