"""Phase 3 validation rule: Flag plans with items that failed GenAI generation after retries."""

from __future__ import annotations

from typing import Any

from python_validation.base import BaseValidator
from schemas.common_schema import VerificationStatus
from schemas.plan_schema import GeneratedPlan
from schemas.validation_schema import ItemValidationResult, ValidationReport


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


def __getattr__(name: str):
    if name == "ValidationPipeline":
        from python_validation.pipeline import ValidationPipeline
        return ValidationPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["BaseValidator", "GenerationFailureValidator", "ValidationPipeline"]
