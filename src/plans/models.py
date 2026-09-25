"""SQLAlchemy models for generated onboarding artifacts (tables created in Phase 1; writers live in Phase 2)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from database.base import Base


class OnboardingPlan(Base):
    """Generated personalized onboarding plan header, including generation metadata pointers."""

    __tablename__ = "onboarding_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), index=True)
    generation_timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_doc_versions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    verification_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    structured_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class LearningModuleRecord(Base):
    """Persisted learning module belonging to a plan."""

    __tablename__ = "learning_modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("onboarding_plans.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_section_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


class ChecklistItemRecord(Base):
    """Persisted checklist item belonging to a plan."""

    __tablename__ = "checklists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("onboarding_plans.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    source_document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_section_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


class TaskRecord(Base):
    """Persisted onboarding task belonging to a plan."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("onboarding_plans.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    source_requirement_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    due_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)


class QuizQuestionRecord(Base):
    """Persisted quiz question belonging to a plan."""

    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("onboarding_plans.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    source_document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_section_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


class AssessmentRecord(Base):
    """Persisted assessment belonging to a plan."""

    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("onboarding_plans.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    assessment_type: Mapped[str | None] = mapped_column(String(64), nullable=True)


class PromptTemplate(Base):
    """Versioned prompt template metadata (file contents live in prompt_templates/)."""

    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    version: Mapped[str] = mapped_column(String(32))
    template_text: Mapped[str] = mapped_column(Text)
    variables: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class GenerationMetadata(Base):
    """Audit metadata for each GenAI generation call (Phase 2 writes; Phase 1 creates the table)."""

    __tablename__ = "generation_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("onboarding_plans.id"), nullable=True, index=True)
    prompt_template_id: Mapped[int | None] = mapped_column(ForeignKey("prompt_templates.id"), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    api_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generation_timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    source_doc_versions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    log_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
