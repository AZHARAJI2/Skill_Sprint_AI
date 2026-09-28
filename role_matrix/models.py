"""SQLAlchemy persistence for active and human-reviewed role requirements."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class RequirementMatrixEntry(Base):
    """One validated row from role_requirement_matrix_seed.csv."""

    __tablename__ = "role_requirements"
    __table_args__ = (UniqueConstraint("requirement_id", name="uq_requirement_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    requirement_id: Mapped[str] = mapped_column(String(32), index=True)
    role: Mapped[str] = mapped_column(String(128), index=True)
    department: Mapped[str] = mapped_column(String(128), index=True)
    requirement_text: Mapped[str] = mapped_column(Text)
    mandatory: Mapped[bool] = mapped_column(Boolean, index=True)
    priority: Mapped[str] = mapped_column(String(32))
    due_stage: Mapped[str] = mapped_column(String(64))
    source_document_id: Mapped[str] = mapped_column(String(64), index=True)
    source_section_id: Mapped[str] = mapped_column(String(32), index=True)
    competency: Mapped[str] = mapped_column(String(128))
    assessment_requirement: Mapped[str] = mapped_column(Text)


class RoleRequirementDraft(Base):
    """A source-linked proposed requirement awaiting human approval.

    Drafts never participate in plan generation. Only an approved draft becomes a
    ``RequirementMatrixEntry`` in the active role matrix.
    """

    __tablename__ = "role_requirement_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_title: Mapped[str] = mapped_column(String(128), index=True)
    department: Mapped[str] = mapped_column(String(128))
    requirement_text: Mapped[str] = mapped_column(Text)
    mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[str] = mapped_column(String(32))
    due_stage: Mapped[str] = mapped_column(String(64))
    source_document_id: Mapped[str] = mapped_column(String(64), index=True)
    source_section_id: Mapped[str] = mapped_column(String(32), index=True)
    competency: Mapped[str] = mapped_column(String(128))
    assessment_requirement: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending_review", index=True)
    submitted_by: Mapped[str] = mapped_column(String(128))
    reviewer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
