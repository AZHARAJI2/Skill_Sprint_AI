"""Create all tables from imported SQLAlchemy models."""

from __future__ import annotations

from sqlalchemy import inspect, text

from database.base import Base, engine
from src.auth.models import User  # noqa: F401
from src.documents.models import Document, DocumentChunk, DocumentRevision  # noqa: F401
from src.employees.models import Employee, EmployeeRole  # noqa: F401
from src.plans.models import (  # noqa: F401
    AssessmentRecord,
    ChecklistItemRecord,
    GenerationMetadata,
    LearningModuleRecord,
    OnboardingPlan,
    PromptTemplate,
    QuizQuestionRecord,
    TaskRecord,
)
from src.reviews.models import AuditEntry, ReviewDecision, ValidationReportRecord
from role_matrix.models import RequirementMatrixEntry, RoleRequirementDraft  # noqa: F401


def create_schema(bind=None) -> None:
    """Create every mapped table and apply safe additive local migrations."""
    target = bind or engine
    Base.metadata.create_all(bind=target)
    _add_review_decision_plan_scope(target)


def _add_review_decision_plan_scope(target) -> None:
    """Add the plan scope to existing review tables without touching audit history."""
    columns = {column["name"] for column in inspect(target).get_columns("review_decisions")}
    if "plan_id" in columns:
        return
    # All supported engines accept this nullable additive column. Keeping it
    # nullable preserves historic review rows created before plan scoping.
    with target.begin() as connection:
        connection.execute(text("ALTER TABLE review_decisions ADD COLUMN plan_id INTEGER"))
