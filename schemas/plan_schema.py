"""Top-level structured JSON schema for a generated onboarding plan (Pipeline 1 output)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.assessment_schema import Assessment
from schemas.common_schema import DifficultyLevel, GroundingStatus, RequirementClassification
from schemas.module_schema import ChecklistItem, LearningModule
from schemas.quiz_schema import QuizQuestion


class ClassifiedRequirement(BaseModel):
    """A matrix row classified for plan generation (computed in Python, not guessed)."""

    requirement_id: str
    role: str
    classification: RequirementClassification
    requirement_text: str
    mandatory: bool
    priority: str
    due_stage: str
    source_document_id: str
    source_section_id: str
    competency: str
    assessment_requirement: str
    difficulty: DifficultyLevel


class TaskItem(BaseModel):
    """Role-specific or scenario task grounded in a matrix requirement."""

    task_id: str
    description: str
    expected_outcome: str
    source_requirement_id: str
    completion_criteria: str
    difficulty: DifficultyLevel
    due_stage: str
    role_title: str
    source_document_id: str
    source_section_id: str
    is_scenario: bool = False
    grounding_status: GroundingStatus = GroundingStatus.SOURCE_SUPPORTED


class GroundingFlag(BaseModel):
    """Unsupported or injection-tainted generated content that must not be silently accepted."""

    item_id: str
    item_type: str
    status: GroundingStatus
    detail: str


class GeneratedPlan(BaseModel):
    """Sole accepted GenAI output shape. Free-form prose is never the plan of record."""

    schema_version: str = "onboarding_plan_v1"
    role_title: str
    employee_code: str
    experience_level: str
    classified_requirements: list[ClassifiedRequirement] = Field(min_length=1)
    modules: list[LearningModule] = Field(min_length=1)
    checklists: list[ChecklistItem] = Field(min_length=1)
    tasks: list[TaskItem] = Field(min_length=1)
    quizzes: list[QuizQuestion] = Field(min_length=1)
    assessments: list[Assessment] = Field(min_length=1)
    stages_used: list[str] = Field(min_length=2)
    grounding_flags: list[GroundingFlag] = Field(default_factory=list)
    covered_requirement_ids: list[str] = Field(min_length=1)
