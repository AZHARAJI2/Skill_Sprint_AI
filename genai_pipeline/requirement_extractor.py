"""Classify matrix rows into Must Know/Complete/Demonstrate/Acknowledge/Recommended/Optional/N/A."""

from __future__ import annotations

import re

from role_matrix.models import RequirementMatrixEntry
from schemas.common_schema import DifficultyLevel, DueStage, RequirementClassification, STAGE_ORDER
from schemas.plan_schema import ClassifiedRequirement


class RequirementExtractor:
    """Python classification of matrix entries — never guessed by the LLM."""

    _ACKNOWLEDGE = re.compile(r"acknowledge|signed acknowledgment|signed review", re.I)
    _COMPLETE = re.compile(r"complet|certificate|training completion", re.I)
    _DEMONSTRATE = re.compile(r"verbal|1:1|tabletop|walkthrough|shadow|practice|confirmation", re.I)
    _QUIZ = re.compile(r"quiz|pass ≥|pass >=", re.I)

    def extract(
        self,
        entries: list[RequirementMatrixEntry],
        experience_level: str,
        employee_role: str,
    ) -> list[ClassifiedRequirement]:
        """Return classified requirements for the employee's role (plus All Roles)."""
        classified: list[ClassifiedRequirement] = []
        for entry in entries:
            classified.append(
                ClassifiedRequirement(
                    requirement_id=entry.requirement_id,
                    role=entry.role,
                    classification=self.classify(entry),
                    requirement_text=entry.requirement_text,
                    mandatory=bool(entry.mandatory),
                    priority=entry.priority,
                    due_stage=self._canonical_stage(entry.due_stage),
                    source_document_id=entry.source_document_id,
                    source_section_id=entry.source_section_id,
                    competency=entry.competency,
                    assessment_requirement=entry.assessment_requirement,
                    difficulty=self.difficulty_for(entry.due_stage, experience_level),
                )
            )
        classified.sort(key=lambda item: (STAGE_ORDER.index(item.due_stage), not item.mandatory, item.requirement_id))
        return classified

    def classify(self, entry: RequirementMatrixEntry) -> RequirementClassification:
        """Map mandatory flag + assessment wording onto the required taxonomy."""
        assessment = entry.assessment_requirement or ""
        if re.search(r"\bn/?a\b|not applicable", assessment, re.I):
            return RequirementClassification.NOT_APPLICABLE
        if not entry.mandatory:
            if (entry.priority or "").lower() == "low":
                return RequirementClassification.OPTIONAL
            return RequirementClassification.RECOMMENDED
        if self._ACKNOWLEDGE.search(assessment):
            return RequirementClassification.MUST_ACKNOWLEDGE
        if self._COMPLETE.search(assessment):
            return RequirementClassification.MUST_COMPLETE
        if self._DEMONSTRATE.search(assessment):
            return RequirementClassification.MUST_DEMONSTRATE
        if self._QUIZ.search(assessment):
            return RequirementClassification.MUST_KNOW
        return RequirementClassification.MUST_KNOW

    @staticmethod
    def difficulty_for(due_stage: str, experience_level: str) -> DifficultyLevel:
        """Beginner content first; Advanced never appears on Day 1."""
        stage = RequirementExtractor._canonical_stage(due_stage)
        experience = (experience_level or "Beginner").title()
        if stage in {DueStage.DAY_1.value, DueStage.WEEK_1.value}:
            return DifficultyLevel.BEGINNER if experience != "Advanced" else DifficultyLevel.INTERMEDIATE
        if stage in {DueStage.WEEK_2.value, DueStage.FIRST_30_DAYS.value}:
            if experience == "Beginner":
                return DifficultyLevel.BEGINNER
            return DifficultyLevel.INTERMEDIATE
        if experience == "Beginner":
            return DifficultyLevel.INTERMEDIATE
        return DifficultyLevel.ADVANCED

    @staticmethod
    def _canonical_stage(raw: str) -> str:
        lookup = {stage.lower(): stage for stage in STAGE_ORDER}
        return lookup.get((raw or "").strip().lower(), DueStage.WEEK_1.value)
