"""SQLAlchemy models for review decisions, audit trail, and persisted validation reports."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from database.base import Base


class ValidationReportRecord(Base):
    """Persisted Pipeline 2 ValidationReport (JSON payload + scores)."""

    __tablename__ = "validation_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("onboarding_plans.id"), index=True)
    coverage_score: Mapped[float | None] = mapped_column(nullable=True)
    traceability_score: Mapped[float | None] = mapped_column(nullable=True)
    consistency_score: Mapped[float | None] = mapped_column(nullable=True)
    missing_count: Mapped[int] = mapped_column(Integer, default=0)
    unsupported_count: Mapped[int] = mapped_column(Integer, default=0)
    contradiction_count: Mapped[int] = mapped_column(Integer, default=0)
    overall_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReviewDecision(Base):
    """Reviewer action preserved alongside the original validation result."""

    __tablename__ = "review_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(String(64), index=True)
    item_type: Mapped[str] = mapped_column(String(64))
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(32))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reviewer_override: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditEntry(Base):
    """Append-only audit trail for GenAI calls, validation decisions, overrides, and ingest events."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(128), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    log_level: Mapped[str] = mapped_column(String(16), default="INFO")
