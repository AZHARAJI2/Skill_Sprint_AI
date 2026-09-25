"""Python schema + business-rule validation of Pipeline 1 JSON (not Pipeline 2 scoring)."""

from __future__ import annotations

from pydantic import ValidationError

from config.logging_config import get_logger
from schemas.common_schema import STAGE_ORDER
from schemas.plan_schema import GeneratedPlan
from src.errors import AppError

logger = get_logger("output_schema_validator")


class OutputSchemaValidator:
    """Validate generated JSON: types, required fields, source IDs, role, duplicate IDs, mandatory flags."""

    def validate(
        self,
        payload: dict,
        *,
        expected_role: str,
        valid_sources: set[tuple[str, str]],
        mandatory_ids: set[str],
    ) -> GeneratedPlan:
        """Raise AppError with field-level details when the payload is not acceptable."""
        try:
            plan = GeneratedPlan.model_validate(payload)
        except ValidationError as exc:
            logger.warning("plan_schema_invalid errors=%s", exc.errors())
            raise AppError("Generated plan failed Pydantic schema validation", status_code=422, details=exc.errors()) from exc

        if plan.role_title != expected_role:
            raise AppError(
                "Generated plan role does not match the employee role",
                status_code=422,
                details={"expected": expected_role, "got": plan.role_title},
            )

        ids: list[str] = []
        for module in plan.modules:
            ids.append(module.module_id)
            self._check_source(module.source_document_id, module.source_section_id, valid_sources, module.module_id)
        for item in plan.checklists:
            ids.append(item.item_id)
            if item.required_or_optional not in {"required", "optional"}:
                raise AppError("Checklist missing valid mandatory status", status_code=422, details={"item_id": item.item_id})
            self._check_source(item.source_document_id, item.source_section_id, valid_sources, item.item_id)
        for task in plan.tasks:
            ids.append(task.task_id)
            self._check_source(task.source_document_id, task.source_section_id, valid_sources, task.task_id)
        for quiz in plan.quizzes:
            ids.append(quiz.question_id)
            self._check_source(quiz.source_document_id, quiz.source_section_id, valid_sources, quiz.question_id)
        for assessment in plan.assessments:
            ids.append(assessment.assessment_id)
            self._check_source(assessment.source_document_id, assessment.source_section_id, valid_sources, assessment.assessment_id)

        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            raise AppError("Duplicate generated IDs", status_code=422, details={"ids": duplicates})

        covered = set(plan.covered_requirement_ids)
        missing_mandatory = sorted(mandatory_ids - covered)
        if missing_mandatory:
            raise AppError(
                "Generated plan is missing mandatory requirement IDs",
                status_code=422,
                details={"missing": missing_mandatory},
            )

        stages = {item.stage for item in plan.modules} | {item.due_stage for item in plan.checklists} | {
            item.due_stage for item in plan.tasks
        }
        unknown_stages = sorted(stage for stage in stages if stage not in STAGE_ORDER)
        if unknown_stages:
            raise AppError("Invalid due_stage values", status_code=422, details={"stages": unknown_stages})
        if len(stages) < 2:
            raise AppError("Multi-stage plan required; content must not all sit in one stage", status_code=422)

        logger.info("plan_schema_valid role=%s items=%s", plan.role_title, len(ids))
        return plan

    @staticmethod
    def _check_source(document_id: str, section_id: str, valid_sources: set[tuple[str, str]], item_id: str) -> None:
        if (document_id, section_id) not in valid_sources:
            raise AppError(
                "Invalid source citation",
                status_code=422,
                details={"item_id": item_id, "source_document_id": document_id, "source_section_id": section_id},
            )
