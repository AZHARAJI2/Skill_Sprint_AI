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


class DueStage(str, Enum):
    """Canonical onboarding stages. Content must be spread across these, never all Day 1."""

    DAY_1 = "Day 1"
    WEEK_1 = "Week 1"
    WEEK_2 = "Week 2"
    FIRST_30_DAYS = "First 30 Days"
    FIRST_60_DAYS = "First 60 Days"
    FIRST_90_DAYS = "First 90 Days"


class DifficultyLevel(str, Enum):
    """Task/module/quiz difficulty reflecting role plus experience."""

    BEGINNER = "Beginner"
    INTERMEDIATE = "Intermediate"
    ADVANCED = "Advanced"


class QuestionType(str, Enum):
    """Supported quiz formats."""

    MCQ = "MCQ"
    MULTIPLE_RESPONSE = "MR"
    TRUE_FALSE = "TF"
    SCENARIO = "Scenario"


class AssessmentType(str, Enum):
    """Assessment categories required by the specification."""

    KNOWLEDGE = "knowledge"
    PRACTICAL = "practical"
    SCENARIO = "scenario"
    ROLE_SPECIFIC = "role-specific"


class RequirementClassification(str, Enum):
    """How a matrix row must be treated in a generated plan (step 11)."""

    MUST_KNOW = "Must Know"
    MUST_COMPLETE = "Must Complete"
    MUST_DEMONSTRATE = "Must Demonstrate"
    MUST_ACKNOWLEDGE = "Must Acknowledge"
    RECOMMENDED = "Recommended"
    OPTIONAL = "Optional"
    NOT_APPLICABLE = "N/A"


class GroundingStatus(str, Enum):
    """Not used on Pipeline 1 JSON. Source support is Phase 3 ItemValidationResult.verification_status."""

    SOURCE_SUPPORTED = "source_supported"
    INSTRUCTIONAL_WORDING = "instructional_wording"
    UNSUPPORTED_FACTUAL = "unsupported_factual"
    INJECTION_FLAGGED = "injection_flagged"
    MANUAL_REVIEW = "manual_review"


class DistractorValidationStatus(str, Enum):
    """Quiz distractor check. Phase 2 only emits pending_verification; Phase 3 sets the final value."""

    PENDING_VERIFICATION = "pending_verification"
    PASSED = "passed"
    FAILED_NOT_IN_SOURCE = "failed_not_in_source"
    FAILED_CONTRADICTORY = "failed_contradictory"
    REPAIRED = "repaired"


STAGE_ORDER: tuple[str, ...] = tuple(stage.value for stage in DueStage)
