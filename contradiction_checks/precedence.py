"""Phase 3 Step 34: Policy precedence rules and hierarchy resolution."""

from __future__ import annotations

from enum import IntEnum


class DocumentPrecedenceRank(IntEnum):
    """Configurable precedence hierarchy:
    Latest Approved Policy > Department SOP > Compliance Procedures > FAQ > Informal Guidance
    """

    INFORMAL_GUIDANCE = 1   # HANDBOOK-*, etc.
    FAQ = 2                 # FAQ-*
    COMPLIANCE_PROCEDURES = 3 # COMP-*
    DEPARTMENT_SOP = 4       # SOP-*
    APPROVED_POLICY = 5      # POL-*


def get_document_precedence(document_id: str) -> DocumentPrecedenceRank:
    """Determine document precedence rank by document ID prefix."""
    doc_upper = (document_id or "").upper()
    if doc_upper.startswith("POL"):
        return DocumentPrecedenceRank.APPROVED_POLICY
    elif doc_upper.startswith("SOP"):
        return DocumentPrecedenceRank.DEPARTMENT_SOP
    elif doc_upper.startswith("COMP"):
        return DocumentPrecedenceRank.COMPLIANCE_PROCEDURES
    elif doc_upper.startswith("FAQ"):
        return DocumentPrecedenceRank.FAQ
    elif doc_upper.startswith("HANDBOOK"):
        return DocumentPrecedenceRank.INFORMAL_GUIDANCE
    return DocumentPrecedenceRank.INFORMAL_GUIDANCE


def resolve_precedence(doc_a: str, doc_b: str) -> str:
    """Return the document ID with higher precedence."""
    rank_a = get_document_precedence(doc_a)
    rank_b = get_document_precedence(doc_b)
    if rank_a >= rank_b:
        return doc_a
    return doc_b
