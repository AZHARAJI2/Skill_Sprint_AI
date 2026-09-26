"""Contradiction detection and policy precedence engine (Phase 3)."""

from contradiction_checks.contradiction_detector import (
    KNOWN_CONFLICT_PAIRS,
    ContradictionValidator,
)
from contradiction_checks.precedence import (
    DocumentPrecedenceRank,
    get_document_precedence,
    resolve_precedence,
)

__all__ = [
    "ContradictionValidator",
    "KNOWN_CONFLICT_PAIRS",
    "DocumentPrecedenceRank",
    "get_document_precedence",
    "resolve_precedence",
]
