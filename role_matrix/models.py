"""SQLAlchemy persistence for the Role Requirement Matrix (one row per requirement_id)."""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
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
