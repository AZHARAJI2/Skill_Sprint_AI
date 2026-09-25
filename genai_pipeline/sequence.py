"""Enforce stage and difficulty ordering after generation."""

from __future__ import annotations

from schemas.common_schema import DifficultyLevel, STAGE_ORDER
from schemas.plan_schema import GeneratedPlan


class PrerequisiteEnforcer:
    """No advanced item before required beginner content; assessments after matching content stages."""

    _DIFFICULTY_RANK = {
        DifficultyLevel.BEGINNER: 0,
        DifficultyLevel.INTERMEDIATE: 1,
        DifficultyLevel.ADVANCED: 2,
    }

    def enforce(self, plan: GeneratedPlan) -> GeneratedPlan:
        """Return a copy with modules, tasks, checklists, and assessments stably ordered."""
        modules = sorted(plan.modules, key=lambda item: (self._stage_rank(item.stage), self._DIFFICULTY_RANK[item.difficulty], item.module_id))
        checklists = sorted(plan.checklists, key=lambda item: (self._stage_rank(item.due_stage), item.item_id))
        tasks = sorted(plan.tasks, key=lambda item: (self._stage_rank(item.due_stage), self._DIFFICULTY_RANK[item.difficulty], item.task_id))
        quizzes = sorted(plan.quizzes, key=lambda item: (self._DIFFICULTY_RANK[item.difficulty], item.question_id))
        assessments = sorted(plan.assessments, key=lambda item: (self._stage_rank(item.stage), item.assessment_id))
        modules = [
            item.model_copy(update={"difficulty": DifficultyLevel.BEGINNER})
            if item.stage == "Day 1" and item.difficulty == DifficultyLevel.ADVANCED
            else item
            for item in modules
        ]
        tasks = [
            item.model_copy(update={"difficulty": DifficultyLevel.BEGINNER})
            if item.due_stage == "Day 1" and item.difficulty == DifficultyLevel.ADVANCED
            else item
            for item in tasks
        ]
        return plan.model_copy(
            update={
                "modules": modules,
                "checklists": checklists,
                "tasks": tasks,
                "quizzes": quizzes,
                "assessments": assessments,
            }
        )

    @staticmethod
    def _stage_rank(stage: str) -> int:
        try:
            return STAGE_ORDER.index(stage)
        except ValueError:
            return 99
