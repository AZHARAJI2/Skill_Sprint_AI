"""Phase 3 Step 47: Comprehensive Pure-Python Validation Pipeline."""

from __future__ import annotations

from typing import Any

from python_validation.base import BaseValidator
from python_validation.duplicate_validator import DuplicateValidator
from python_validation.generation_failure_validator import GenerationFailureValidator
from python_validation.requirement_validator import CoverageValidator
from python_validation.role_relevance_validator import RoleRelevanceValidator
from python_validation.schema_validator import SchemaValidator
from python_validation.sequence_validator import SequenceValidator
from python_validation.traceability_validator import TraceabilityValidator
from schemas.common_schema import VerificationStatus
from schemas.plan_schema import GeneratedPlan
from schemas.validation_schema import ItemValidationResult, ValidationReport


class ValidationPipeline:
    """Composes and executes all Phase 3 pure-Python validation rules in sequence.
    
    CRITICAL: 100% deterministic, zero GenAI calls.
    """

    def __init__(self, validators: list[BaseValidator] | None = None) -> None:
        from contradiction_checks.contradiction_detector import ContradictionValidator
        from hallucination_checks.hallucination_detector import HallucinationDetector

        self.req_validator = CoverageValidator()
        self.trace_validator = TraceabilityValidator()
        self.validators = validators or [
            GenerationFailureValidator(),
            SequenceValidator(),
            self.req_validator,
            self.trace_validator,
            ContradictionValidator(),
            HallucinationDetector(),
            DuplicateValidator(),
            RoleRelevanceValidator(),
            SchemaValidator(),
        ]

    def run(
        self,
        plan: GeneratedPlan | dict[str, Any],
        matrix: list[Any] | None = None,
        documents: list[Any] | None = None,
        chunks: list[Any] | None = None,
        plan_id: int = 1,
    ) -> ValidationReport:
        all_results: list[ItemValidationResult] = []

        for validator in self.validators:
            res = validator.validate(plan, matrix=matrix, documents=documents, chunks=chunks)
            if isinstance(res, list):
                all_results.extend(res)
            elif res is not None:
                all_results.append(res)

        coverage_score = getattr(self.req_validator, "last_coverage_score", 100.0)
        traceability_score = getattr(self.trace_validator, "last_traceability_score", 100.0)

        missing_count = sum(
            1 for r in all_results if r.verification_status == VerificationStatus.REQUIREMENT_MISSING
        )
        unsupported_count = sum(
            1 for r in all_results if r.verification_status == VerificationStatus.UNSUPPORTED_REQUIREMENT
        )
        contradiction_count = sum(
            1 for r in all_results if r.verification_status == VerificationStatus.CONTRADICTION_DETECTED
        )
        manual_review_count = sum(
            1 for r in all_results if r.verification_status == VerificationStatus.MANUAL_REVIEW_REQUIRED
        )

        if manual_review_count > 0:
            overall = VerificationStatus.MANUAL_REVIEW_REQUIRED
        elif contradiction_count > 0:
            overall = VerificationStatus.CONTRADICTION_DETECTED
        elif missing_count > 0 or coverage_score < 100.0:
            overall = VerificationStatus.REQUIREMENT_MISSING
        elif any(r.verification_status == VerificationStatus.SOURCE_SUPPORT_MISSING for r in all_results):
            overall = VerificationStatus.SOURCE_SUPPORT_MISSING
        elif any(r.verification_status == VerificationStatus.OUTDATED_SOURCE for r in all_results):
            overall = VerificationStatus.OUTDATED_SOURCE
        elif unsupported_count > 0:
            overall = VerificationStatus.UNSUPPORTED_REQUIREMENT
        elif any(r.verification_status == VerificationStatus.VERIFIED_WITH_WARNING for r in all_results):
            overall = VerificationStatus.VERIFIED_WITH_WARNING
        elif coverage_score >= 100.0 and traceability_score >= 100.0:
            overall = VerificationStatus.VERIFIED
        else:
            overall = VerificationStatus.PARTIALLY_VERIFIED

        return ValidationReport(
            plan_id=plan_id,
            coverage_score=coverage_score,
            traceability_score=traceability_score,
            consistency_score=100.0,
            missing_count=missing_count,
            unsupported_count=unsupported_count,
            contradiction_count=contradiction_count,
            per_item_results=all_results,
            overall_status=overall,
        )
