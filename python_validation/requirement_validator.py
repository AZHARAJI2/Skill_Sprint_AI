"""Phase 3 Steps 28 & 29: Requirement coverage validation engine and Coverage Score computation."""

from __future__ import annotations

from typing import Any

from python_validation.base import BaseValidator
from schemas.common_schema import VerificationStatus
from schemas.plan_schema import GeneratedPlan
from schemas.validation_schema import ItemValidationResult


class CoverageValidator(BaseValidator):
    """Validates mandatory and optional role requirements coverage from the matrix."""

    def __init__(self) -> None:
        self.last_coverage_score: float = 0.0
        self.covered_mandatory_ids: set[str] = set()
        self.missing_mandatory_ids: set[str] = set()
        self.unsupported_ids: set[str] = set()
        self.duplicate_ids: set[str] = set()

    def validate(
        self,
        plan: GeneratedPlan | dict[str, Any],
        matrix: list[Any] | None = None,
        documents: list[Any] | None = None,
        chunks: list[Any] | None = None,
    ) -> list[ItemValidationResult]:
        payload = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else plan
        results: list[ItemValidationResult] = []

        role_title = payload.get("role_title", "")
        classified = payload.get("classified_requirements", [])

        # 1. Extract matrix mandatory requirements for this role + All Roles
        matrix_mandatory_reqs: dict[str, Any] = {}
        matrix_all_reqs: dict[str, Any] = {}

        if matrix:
            for row in matrix:
                r_id = getattr(row, "requirement_id", None) or (row.get("requirement_id") if isinstance(row, dict) else None)
                r_role = getattr(row, "role", None) or (row.get("role") if isinstance(row, dict) else None)
                r_mand = getattr(row, "mandatory", None) if hasattr(row, "mandatory") else (row.get("mandatory") if isinstance(row, dict) else False)
                if r_id:
                    matrix_all_reqs[r_id] = row
                    if (r_role in ("All Roles", role_title)) and r_mand:
                        matrix_mandatory_reqs[r_id] = row
        elif classified:
            for cr in classified:
                r_id = cr.get("requirement_id")
                r_mand = cr.get("mandatory", False)
                matrix_all_reqs[r_id] = cr
                if r_mand:
                    matrix_mandatory_reqs[r_id] = cr

        # 2. Extract requirement IDs covered in generated plan
        covered_ids: set[str] = set()
        id_usage_count: dict[str, int] = {}

        for mod in payload.get("modules", []):
            for r_id in mod.get("requirement_ids", []):
                covered_ids.add(r_id)
                id_usage_count[r_id] = id_usage_count.get(r_id, 0) + 1

        for task in payload.get("tasks", []):
            src_req = task.get("source_requirement_id")
            if src_req:
                covered_ids.add(src_req)
                id_usage_count[src_req] = id_usage_count.get(src_req, 0) + 1

        if "covered_requirement_ids" in payload:
            for r_id in payload["covered_requirement_ids"]:
                covered_ids.add(r_id)

        # 3. Categorize into Covered, Missing, Unsupported, Duplicate
        mandatory_ids_set = set(matrix_mandatory_reqs.keys())
        self.covered_mandatory_ids = mandatory_ids_set.intersection(covered_ids)
        self.missing_mandatory_ids = mandatory_ids_set.difference(covered_ids)

        all_matrix_ids = set(matrix_all_reqs.keys())
        self.unsupported_ids = covered_ids.difference(all_matrix_ids) if all_matrix_ids else set()
        self.duplicate_ids = {r_id for r_id, count in id_usage_count.items() if count > 3}

        # 4. Compute Coverage Score = Covered Mandatory / Total Mandatory * 100
        total_mandatory_count = len(mandatory_ids_set)
        if total_mandatory_count > 0:
            self.last_coverage_score = round(
                (len(self.covered_mandatory_ids) / total_mandatory_count) * 100.0, 2
            )
        else:
            self.last_coverage_score = 100.0

        # 5. Flag Missing Mandatory Requirements
        for m_id in sorted(self.missing_mandatory_ids):
            req_info = matrix_mandatory_reqs.get(m_id, {})
            text = (
                getattr(req_info, "requirement_text", "")
                if hasattr(req_info, "requirement_text")
                else req_info.get("requirement_text", "")
            )
            doc_id = (
                getattr(req_info, "source_document_id", "")
                if hasattr(req_info, "source_document_id")
                else req_info.get("source_document_id", "")
            )
            sec_id = (
                getattr(req_info, "source_section_id", "")
                if hasattr(req_info, "source_section_id")
                else req_info.get("source_section_id", "")
            )

            results.append(
                ItemValidationResult(
                    item_id=m_id,
                    item_type="mandatory_requirement",
                    verification_status=VerificationStatus.REQUIREMENT_MISSING,
                    details=f"Mandatory requirement '{m_id}' ({text[:50]}...) is not covered in the plan.",
                    source_references=[f"{doc_id}§{sec_id}"] if doc_id else [],
                )
            )

        # 6. Flag Unsupported Requirements
        for u_id in sorted(self.unsupported_ids):
            results.append(
                ItemValidationResult(
                    item_id=u_id,
                    item_type="unsupported_requirement",
                    verification_status=VerificationStatus.UNSUPPORTED_REQUIREMENT,
                    details=f"Requirement '{u_id}' is referenced in plan items but does not exist in the role matrix.",
                    source_references=[],
                )
            )

        # 7. Flag Duplicate Requirements
        for d_id in sorted(self.duplicate_ids):
            results.append(
                ItemValidationResult(
                    item_id=d_id,
                    item_type="duplicate_requirement",
                    verification_status=VerificationStatus.VERIFIED_WITH_WARNING,
                    details=f"Requirement '{d_id}' is redundantly covered across {id_usage_count[d_id]} separate items.",
                    source_references=[],
                )
            )

        return results


# Export alias
RequirementCoverageValidator = CoverageValidator
