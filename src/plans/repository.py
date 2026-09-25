"""Repositories for onboarding plans, child artifacts, prompt templates, and generation metadata."""

from __future__ import annotations

from sqlalchemy.orm import Session

from database.base import BaseRepository
from src.plans.models import (
    AssessmentRecord,
    ChecklistItemRecord,
    GenerationMetadata,
    LearningModuleRecord,
    OnboardingPlan,
    PromptTemplate,
    QuizQuestionRecord,
    TaskRecord,
)


class PlanRepository(BaseRepository[OnboardingPlan]):
    """Persist and load generated plans."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, OnboardingPlan)

    def list_by_employee(self, employee_id: int) -> list[OnboardingPlan]:
        """Return plans for one employee, newest first."""
        return list(
            self.session.query(OnboardingPlan)
            .filter(OnboardingPlan.employee_id == employee_id)
            .order_by(OnboardingPlan.id.desc())
            .all()
        )


class ModuleRecordRepository(BaseRepository[LearningModuleRecord]):
    """Persist learning-module rows attached to a generated plan."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, LearningModuleRecord)


class ChecklistRecordRepository(BaseRepository[ChecklistItemRecord]):
    """Persist checklist rows attached to a generated plan."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ChecklistItemRecord)


class TaskRecordRepository(BaseRepository[TaskRecord]):
    """Persist task rows attached to a generated plan."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, TaskRecord)


class QuizRecordRepository(BaseRepository[QuizQuestionRecord]):
    """Persist quiz rows attached to a generated plan."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, QuizQuestionRecord)


class AssessmentRecordRepository(BaseRepository[AssessmentRecord]):
    """Persist assessment rows attached to a generated plan."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, AssessmentRecord)


class PromptTemplateRepository(BaseRepository[PromptTemplate]):
    """Store versioned prompt-template snapshots used at generation time."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, PromptTemplate)

    def upsert(self, name: str, version: str, template_text: str, variables: list[str]) -> PromptTemplate:
        """Insert or update a versioned prompt template row."""
        existing = (
            self.session.query(PromptTemplate)
            .filter(PromptTemplate.name == name, PromptTemplate.version == version)
            .one_or_none()
        )
        if existing is None:
            existing = PromptTemplate(
                name=name,
                version=version,
                template_text=template_text,
                variables=variables,
                is_active=True,
            )
            return self.add(existing)
        existing.template_text = template_text
        existing.variables = variables
        existing.is_active = True
        return existing


class GenerationMetadataRepository(BaseRepository[GenerationMetadata]):
    """Store prompt version, model, retries, and source-doc versions per plan."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, GenerationMetadata)
