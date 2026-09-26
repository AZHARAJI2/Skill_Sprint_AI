"""Phase 3 Step 38: Schema and structural integrity validator in pure Python."""

from __future__ import annotations

from typing import Any

from python_validation.base import BaseValidator
from schemas.common_schema import VerificationStatus
from schemas.plan_schema import GeneratedPlan
from schemas.validation_schema import ItemValidationResult


class SchemaValidator(BaseValidator):
    """Validates structural completeness and schema correctness of generated plan objects."""

    def validate(
        self,
        plan: GeneratedPlan | dict[str, Any],
        matrix: list[Any] | None = None,
        documents: list[Any] | None = None,
        chunks: list[Any] | None = None,
    ) -> list[ItemValidationResult]:
        payload = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else plan
        results: list[ItemValidationResult] = []

        # Check top-level required fields
        required_top_level = ["role_title", "employee_code", "modules"]
        for field in required_top_level:
            if not payload.get(field):
                results.append(
                    ItemValidationResult(
                        item_id="PLAN_SCHEMA",
                        item_type="onboarding_plan",
                        verification_status=VerificationStatus.MANUAL_REVIEW_REQUIRED,
                        details=f"Plan is missing required top-level schema field '{field}'.",
                        source_references=[],
                    )
                )

        # Check duplicate item IDs within sections
        seen_ids: set[str] = set()
        item_groups = [
            ("modules", "learning_module", "module_id"),
            ("checklists", "checklist_item", "item_id"),
            ("tasks", "task_item", "task_id"),
            ("quizzes", "quiz_question", "question_id"),
            ("assessments", "assessment", "assessment_id"),
        ]

        for key, item_type, id_field in item_groups:
            for item in payload.get(key, []):
                item_id = str(item.get(id_field, "UNKNOWN"))
                if item_id in seen_ids:
                    results.append(
                        ItemValidationResult(
                            item_id=item_id,
                            item_type=item_type,
                            verification_status=VerificationStatus.VERIFIED_WITH_WARNING,
                            details=f"Duplicate ID '{item_id}' detected across plan entities.",
                            source_references=[],
                        )
                    )
                seen_ids.add(item_id)

        return results
