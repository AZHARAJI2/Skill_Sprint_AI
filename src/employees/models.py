"""Job-role and employee profile SQLAlchemy models (no unnecessary PII)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from database.base import Base


class EmployeeRole(Base):
    """A NovaCart job role (Software Engineer, Recruiter, ...), not an RBAC app role."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    department: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    employees: Mapped[list[Employee]] = relationship(back_populates="role")


class Employee(Base):
    """Employee onboarding profile used to personalize plans in later phases."""

    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), index=True)
    department: Mapped[str] = mapped_column(String(128))
    experience_level: Mapped[str] = mapped_column(String(32), default="Beginner")
    location: Mapped[str | None] = mapped_column(String(128), nullable=True)
    joining_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reporting_manager: Mapped[str | None] = mapped_column(String(128), nullable=True)
    required_competencies: Mapped[list | None] = mapped_column(JSON, nullable=True)
    prior_experience: Mapped[str | None] = mapped_column(Text, nullable=True)
    training_status: Mapped[str] = mapped_column(String(32), default="not_started")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    role: Mapped[EmployeeRole] = relationship(back_populates="employees")
