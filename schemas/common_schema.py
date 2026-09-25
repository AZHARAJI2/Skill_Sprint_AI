"""Shared Pydantic enums and value objects used across API and persistence boundaries."""

from __future__ import annotations

from enum import Enum


class DocumentStatus(str, Enum):
    """Lifecycle of an ingested company document version."""

    ACTIVE = "active"
    OBSOLETE = "obsolete"


class TrainingStatus(str, Enum):
    """Employee onboarding training status."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class AppRole(str, Enum):
    """RBAC application roles (distinct from job titles in the Role table)."""

    EMPLOYEE = "Employee"
    ADMIN = "Admin"
    TRAINING_MANAGER = "Training Manager"
    REVIEWER = "Reviewer"
    MANAGER = "Manager"


class VerificationStatus(str, Enum):
    """Plan/item verification statuses from the competition specification."""

    VERIFIED = "Verified"
    VERIFIED_WITH_WARNING = "Verified with Warning"
    PARTIALLY_VERIFIED = "Partially Verified"
    SOURCE_SUPPORT_MISSING = "Source Support Missing"
    REQUIREMENT_MISSING = "Requirement Missing"
    UNSUPPORTED_REQUIREMENT = "Unsupported Requirement"
    OUTDATED_SOURCE = "Outdated Source"
    CONTRADICTION_DETECTED = "Contradiction Detected"
    MANUAL_REVIEW_REQUIRED = "Manual Review Required"


class ReviewAction(str, Enum):
    """Allowed reviewer actions (Phase 4 consumes this enum)."""

    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"
    REGENERATE = "regenerate"
    COMMENT = "comment"
