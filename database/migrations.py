"""Create all tables from imported SQLAlchemy models."""

from __future__ import annotations

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
from role_matrix.models import RequirementMatrixEntry  # noqa: F401


def create_schema(bind=None) -> None:
    """Create every mapped table. Safe to call repeatedly (create_all is idempotent)."""
    Base.metadata.create_all(bind=bind or engine)
