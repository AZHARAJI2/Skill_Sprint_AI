"""Phase 3 Step 30: Source traceability validation engine and Traceability Score computation."""

from __future__ import annotations

from typing import Any

from python_validation.base import BaseValidator
from schemas.common_schema import DocumentStatus, VerificationStatus
from schemas.plan_schema import GeneratedPlan
from schemas.validation_schema import ItemValidationResult


class TraceabilityValidator(BaseValidator):
    """Validates source grounding and citations across all generated plan items."""

    def __init__(self) -> None:
        self.last_traceability_score: float = 0.0
        self.valid_items_count: int = 0
        self.total_items_count: int = 0

    def validate(
        self,
        plan: GeneratedPlan | dict[str, Any],
        matrix: list[Any] | None = None,
        documents: list[Any] | None = None,
        chunks: list[Any] | None = None,
    ) -> list[ItemValidationResult]:
        payload = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else plan
        results: list[ItemValidationResult] = []

        # 1. Build lookup maps for known documents and sections
        active_doc_ids: set[str] = set()
        obsolete_doc_ids: set[str] = set()
        valid_sections_by_doc: dict[str, set[str]] = {}

        if documents:
            for doc in documents:
                d_id = getattr(doc, "document_id", None) or (doc.get("document_id") if isinstance(doc, dict) else None)
                status = getattr(doc, "status", None) or (doc.get("status") if isinstance(doc, dict) else "active")
                if d_id:
                    if status == DocumentStatus.OBSOLETE or status == "obsolete":
                        obsolete_doc_ids.add(d_id)
                    else:
                        active_doc_ids.add(d_id)

        if chunks:
            for chunk in chunks:
                c_doc = getattr(chunk, "document_id", None) or (chunk.get("document_id") if isinstance(chunk, dict) else None)
                c_sec = getattr(chunk, "section_id", None) or (chunk.get("section_id") if isinstance(chunk, dict) else None)
                if c_doc and c_sec:
                    valid_sections_by_doc.setdefault(c_doc, set()).add(c_sec)
                    if c_doc not in obsolete_doc_ids:
                        active_doc_ids.add(c_doc)

        standard_docs = {
            "HANDBOOK-01", "POL-01", "POL-02", "POL-03", "POL-04", "POL-05",
            "SOP-01", "SOP-02", "SOP-03", "SOP-04", "SOP-05",
            "COMP-01", "FAQ-01", "FAQ-02",
            "ROLE-01", "ROLE-02", "ROLE-03", "ROLE-04", "ROLE-05",
            "ROLE-06", "ROLE-07", "ROLE-08", "ROLE-09", "ROLE-10"
        }
        if not active_doc_ids and not obsolete_doc_ids:
            active_doc_ids = standard_docs

        # 2. Iterate through all items
        item_groups = [
            ("modules", "learning_module", "module_id"),
            ("checklists", "checklist_item", "item_id"),
            ("tasks", "task_item", "task_id"),
            ("quizzes", "quiz_question", "question_id"),
            ("assessments", "assessment", "assessment_id"),
        ]

        valid_count = 0
        total_count = 0

        for key, item_type, id_field in item_groups:
            items = payload.get(key, [])
            for item in items:
                total_count += 1
                item_id = str(item.get(id_field, "UNKNOWN"))
                doc_id = item.get("source_document_id") or ""
                sec_id = item.get("source_section_id") or ""

                if not doc_id:
                    results.append(
                        ItemValidationResult(
                            item_id=item_id,
                            item_type=item_type,
                            verification_status=VerificationStatus.SOURCE_SUPPORT_MISSING,
                            details=f"Item {item_id} is missing source_document_id citation.",
                            source_references=[],
                        )
                    )
                    continue

                if doc_id in obsolete_doc_ids:
                    results.append(
                        ItemValidationResult(
                            item_id=item_id,
                            item_type=item_type,
                            verification_status=VerificationStatus.OUTDATED_SOURCE,
                            details=f"Item {item_id} cites obsolete document '{doc_id}'.",
                            source_references=[f"{doc_id}§{sec_id}"],
                        )
                    )
                    continue

                if active_doc_ids and doc_id not in active_doc_ids:
                    results.append(
                        ItemValidationResult(
                            item_id=item_id,
                            item_type=item_type,
                            verification_status=VerificationStatus.SOURCE_SUPPORT_MISSING,
                            details=f"Item {item_id} cites non-existent document '{doc_id}'.",
                            source_references=[f"{doc_id}§{sec_id}"],
                        )
                    )
                    continue

                if doc_id in valid_sections_by_doc and sec_id and sec_id not in valid_sections_by_doc[doc_id]:
                    results.append(
                        ItemValidationResult(
                            item_id=item_id,
                            item_type=item_type,
                            verification_status=VerificationStatus.SOURCE_SUPPORT_MISSING,
                            details=f"Item {item_id} cites section '{sec_id}' which does not exist in document '{doc_id}'.",
                            source_references=[f"{doc_id}§{sec_id}"],
                        )
                    )
                    continue

                valid_count += 1

        self.valid_items_count = valid_count
        self.total_items_count = total_count
        self.last_traceability_score = round(
            (valid_count / max(total_count, 1)) * 100.0, 2
        ) if total_count > 0 else 100.0

        return results
