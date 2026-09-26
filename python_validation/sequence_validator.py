"""Phase 3 Step 27: Learning sequence and prerequisite validation."""

from __future__ import annotations

from typing import Any

from python_validation.base import BaseValidator
from schemas.common_schema import DifficultyLevel, DueStage, VerificationStatus
from schemas.plan_schema import GeneratedPlan
from schemas.validation_schema import ItemValidationResult

STAGE_ORDER: dict[str, int] = {
    DueStage.DAY_1.value: 1,
    DueStage.WEEK_1.value: 2,
    DueStage.WEEK_2.value: 3,
    DueStage.FIRST_30_DAYS.value: 4,
    DueStage.FIRST_60_DAYS.value: 5,
    DueStage.FIRST_90_DAYS.value: 6,
}

DIFFICULTY_RANK: dict[str, int] = {
    DifficultyLevel.BEGINNER.value: 1,
    DifficultyLevel.INTERMEDIATE.value: 2,
    DifficultyLevel.ADVANCED.value: 3,
}


class SequenceValidator(BaseValidator):
    """Validates learning sequence, prerequisite ordering, and assessment placement."""

    def validate(
        self,
        plan: GeneratedPlan | dict[str, Any],
        matrix: list[Any] | None = None,
        documents: list[Any] | None = None,
        chunks: list[Any] | None = None,
    ) -> list[ItemValidationResult]:
        payload = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else plan
        results: list[ItemValidationResult] = []

        modules = payload.get("modules", [])
        tasks = payload.get("tasks", [])
        quizzes = payload.get("quizzes", [])
        assessments = payload.get("assessments", [])

        # 1. Map requirements to stage where they are taught
        req_to_stage: dict[str, int] = {}
        for mod in modules:
            mod_stage = STAGE_ORDER.get(mod.get("stage", ""), 99)
            for r_id in mod.get("requirement_ids", []):
                if r_id not in req_to_stage or mod_stage < req_to_stage[r_id]:
                    req_to_stage[r_id] = mod_stage

        # 2. Check: Assessment before content
        for quiz in quizzes:
            quiz_stage_val = quiz.get("stage") or quiz.get("due_stage")
            q_id = str(quiz.get("question_id", "QUIZ"))
            source_doc = quiz.get("source_document_id", "")
            source_sec = quiz.get("source_section_id", "")

            if quiz_stage_val and quiz_stage_val in STAGE_ORDER:
                q_stage_num = STAGE_ORDER[quiz_stage_val]
                for r_id, m_stage_num in req_to_stage.items():
                    if m_stage_num > q_stage_num and r_id in quiz.get("explanation", ""):
                        results.append(
                            ItemValidationResult(
                                item_id=q_id,
                                item_type="quiz_question",
                                verification_status=VerificationStatus.MANUAL_REVIEW_REQUIRED,
                                details=f"Quiz question scheduled at stage '{quiz_stage_val}' tests requirement {r_id} taught at a later stage.",
                                source_references=[f"{source_doc}§{source_sec}"],
                            )
                        )

        # 3. Check: Advanced before basic difficulty sequencing within modules
        seen_difficulties: dict[str, list[tuple[int, int, str]]] = {}
        for mod in modules:
            m_id = str(mod.get("module_id", "MOD"))
            m_stage_num = STAGE_ORDER.get(mod.get("stage", ""), 99)
            m_diff_str = mod.get("difficulty", "Beginner")
            m_diff_num = DIFFICULTY_RANK.get(m_diff_str, 1)

            title = mod.get("title", "")
            comp = title.split("—")[0].strip() if "—" in title else "General"
            if comp not in seen_difficulties:
                seen_difficulties[comp] = []

            for prev_stage, prev_diff, prev_id in seen_difficulties[comp]:
                if prev_stage < m_stage_num and prev_diff > m_diff_num:
                    results.append(
                        ItemValidationResult(
                            item_id=m_id,
                            item_type="learning_module",
                            verification_status=VerificationStatus.VERIFIED_WITH_WARNING,
                            details=f"Module '{title}' ({m_diff_str}) appears after advanced module {prev_id} in earlier stage for competency '{comp}'.",
                            source_references=[f"{mod.get('source_document_id', '')}§{mod.get('source_section_id', '')}"],
                        )
                    )
            seen_difficulties[comp].append((m_stage_num, m_diff_num, m_id))

        # 4. Check: Invalid or skipped due stages
        valid_stages = set(STAGE_ORDER.keys())
        for task in tasks:
            t_stage = task.get("due_stage")
            t_id = str(task.get("task_id", "TASK"))
            if t_stage and t_stage not in valid_stages:
                results.append(
                    ItemValidationResult(
                        item_id=t_id,
                        item_type="task_item",
                        verification_status=VerificationStatus.MANUAL_REVIEW_REQUIRED,
                        details=f"Task '{task.get('description', '')[:40]}' has invalid due stage '{t_stage}'.",
                        source_references=[f"{task.get('source_document_id', '')}§{task.get('source_section_id', '')}"],
                    )
                )

        return results
