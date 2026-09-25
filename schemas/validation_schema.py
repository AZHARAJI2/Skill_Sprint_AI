"""Pydantic models for Pipeline 2 reports. Phase 2 defines the contract; Phase 3 fills scores."""

from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.common_schema import VerificationStatus


class ItemValidationResult(BaseModel):
    """Per-item verification record consumed by the review queue."""

    item_id: str
    item_type: str
    verification_status: VerificationStatus
    details: str
    source_references: list[str] = Field(default_factory=list)


class ValidationReport(BaseModel):
    """Aggregated Pipeline 2 output. Scores are computed later; this schema is the shared type."""

    plan_id: int
    coverage_score: float | None = None
    traceability_score: float | None = None
    consistency_score: float | None = None
    missing_count: int = 0
    unsupported_count: int = 0
    contradiction_count: int = 0
    per_item_results: list[ItemValidationResult] = Field(default_factory=list)
    overall_status: VerificationStatus | None = None
