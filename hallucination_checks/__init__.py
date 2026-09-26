"""Hallucination and adversarial injection checks (Phase 3)."""

from hallucination_checks.hallucination_detector import (
    ADVERSARIAL_INJECTION_SIGNATURES,
    ADVERSARIAL_SOURCE_SECTIONS,
    HallucinationDetector,
)

__all__ = [
    "HallucinationDetector",
    "ADVERSARIAL_INJECTION_SIGNATURES",
    "ADVERSARIAL_SOURCE_SECTIONS",
]
