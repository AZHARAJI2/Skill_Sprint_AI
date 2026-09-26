"""Phase 3 Step 33 & 34: Contradiction detection engine and resolution via precedence rules."""

from __future__ import annotations

from typing import Any

from contradiction_checks.precedence import (
    DocumentPrecedenceRank,
    get_document_precedence,
    resolve_precedence,
)
from python_validation.base import BaseValidator
from schemas.common_schema import VerificationStatus
from schemas.plan_schema import GeneratedPlan
from schemas.validation_schema import ItemValidationResult

# The 10 canonical contradiction conflict pairs from NovaCart dataset
KNOWN_CONFLICT_PAIRS = [
    {
        "id": "CP-01",
        "doc_a": "FAQ-02", "sec_a": "1.1", "claim_a": "14-day refund window",
        "doc_b": "SOP-02", "sec_b": "1.2", "claim_b": "30-day refund window (v2)",
        "ruling": "SOP-02 §1.2 takes precedence over FAQ-02 §1.1 (SOP > FAQ)",
        "superseded": ("FAQ-02", "1.1"),
        "authoritative": ("SOP-02", "1.2"),
    },
    {
        "id": "CP-02",
        "doc_a": "HANDBOOK-01", "sec_a": "2.4", "claim_a": "Doctor note required after 3 days",
        "doc_b": "POL-02", "sec_b": "2.3", "claim_b": "Doctor note required after 2 days",
        "ruling": "POL-02 §2.3 takes precedence over HANDBOOK-01 §2.4 (Policy > Handbook)",
        "superseded": ("HANDBOOK-01", "2.4"),
        "authoritative": ("POL-02", "2.3"),
    },
    {
        "id": "CP-03",
        "doc_a": "FAQ-01", "sec_a": "3.1", "claim_a": "Escalate to team lead first",
        "doc_b": "SOP-01", "sec_b": "3.1", "claim_b": "Escalate directly to on-call SRE (v2)",
        "ruling": "SOP-01 §3.1 takes precedence over FAQ-01 §3.1 (SOP > FAQ)",
        "superseded": ("FAQ-01", "3.1"),
        "authoritative": ("SOP-01", "3.1"),
    },
    {
        "id": "CP-04",
        "doc_a": "POL-03", "sec_a": "1.2", "claim_a": "General 1-year data retention",
        "doc_b": "POL-05", "sec_b": "2.1", "claim_b": "90-day deletion upon customer request",
        "ruling": "POL-05 §2.1 (Data Privacy specific deletion) overrides general POL-03 retention",
        "superseded": ("POL-03", "1.2"),
        "authoritative": ("POL-05", "2.1"),
    },
    {
        "id": "CP-05",
        "doc_a": "HANDBOOK-01", "sec_a": "2.1", "claim_a": "Mandatory core hours 10am-3pm",
        "doc_b": "ROLE-02", "sec_b": "2.1", "claim_b": "On-call engineers work flexible hours at discretion",
        "ruling": "ROLE-02 §2.1 role exception overrides general HANDBOOK core hours",
        "superseded": ("HANDBOOK-01", "2.1"),
        "authoritative": ("ROLE-02", "2.1"),
    },
    {
        "id": "CP-06",
        "doc_a": "SOP-03", "sec_a": "1.2", "claim_a": "Manager approval only for payment data access",
        "doc_b": "POL-03", "sec_b": "2.3", "claim_b": "Manager plus Security approval required (v2)",
        "ruling": "POL-03 §2.3 takes precedence over SOP-03 §1.2 (Policy > SOP)",
        "superseded": ("SOP-03", "1.2"),
        "authoritative": ("POL-03", "2.3"),
    },
    {
        "id": "CP-07",
        "doc_a": "POL-04", "sec_a": "2.1", "claim_a": "Report conduct violation to manager or HR",
        "doc_b": "COMP-01", "sec_b": "1.1", "claim_b": "Bypass manager if manager is implicated in violation",
        "ruling": "COMP-01 §1.1 bypass rule overrides general reporting line when manager is implicated",
        "superseded": ("POL-04", "2.1"),
        "authoritative": ("COMP-01", "1.1"),
    },
    {
        "id": "CP-08",
        "doc_a": "FAQ-01", "sec_a": "2.1", "claim_a": "VP approval needed for remote work",
        "doc_b": "POL-01", "sec_b": "4.1", "claim_b": "Direct manager approval only for remote work (v2)",
        "ruling": "POL-01 §4.1 takes precedence over FAQ-01 §2.1 (Policy > FAQ)",
        "superseded": ("FAQ-01", "2.1"),
        "authoritative": ("POL-01", "4.1"),
    },
    {
        "id": "CP-09",
        "doc_a": "SOP-05", "sec_a": "1.3", "claim_a": "AP Clerk self-approves invoices up to $1,000",
        "doc_b": "SOP-05", "sec_b": "1.1", "claim_b": "All vendor invoices require Financial Analyst approval (v2)",
        "ruling": "SOP-05 §1.1 v2 update supersedes previous unreviewed self-approval",
        "superseded": ("SOP-05", "1.3"),
        "authoritative": ("SOP-05", "1.1"),
    },
    {
        "id": "CP-10",
        "doc_a": "FAQ-01", "sec_a": "2.2", "claim_a": "15 vacation days annual accrual",
        "doc_b": "POL-02", "sec_b": "1.1", "claim_b": "20 vacation days annual accrual (v2)",
        "ruling": "POL-02 §1.1 takes precedence over FAQ-01 §2.2 (Policy > FAQ)",
        "superseded": ("FAQ-01", "2.2"),
        "authoritative": ("POL-02", "1.1"),
    },
]


class ContradictionValidator(BaseValidator):
    """Detects contradictions against authoritative policies and applies precedence hierarchy."""

    def __init__(self, conflict_pairs: list[dict[str, Any]] | None = None) -> None:
        self.conflict_pairs = conflict_pairs or KNOWN_CONFLICT_PAIRS
        self.superseded_map: dict[tuple[str, str], dict[str, Any]] = {}
        for cp in self.conflict_pairs:
            sup = cp.get("superseded")
            if sup:
                self.superseded_map[sup] = cp

    def validate(
        self,
        plan: GeneratedPlan | dict[str, Any],
        matrix: list[Any] | None = None,
        documents: list[Any] | None = None,
        chunks: list[Any] | None = None,
    ) -> list[ItemValidationResult]:
        payload = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else plan
        results: list[ItemValidationResult] = []

        item_groups = [
            ("modules", "learning_module", "module_id"),
            ("checklists", "checklist_item", "item_id"),
            ("tasks", "task_item", "task_id"),
            ("quizzes", "quiz_question", "question_id"),
            ("assessments", "assessment", "assessment_id"),
        ]

        for key, item_type, id_field in item_groups:
            items = payload.get(key, [])
            for item in items:
                item_id = str(item.get(id_field, "UNKNOWN"))
                doc_id = item.get("source_document_id") or ""
                sec_id = item.get("source_section_id") or ""
                citation = (doc_id, sec_id)

                if citation in self.superseded_map:
                    cp = self.superseded_map[citation]
                    auth_doc, auth_sec = cp["authoritative"]
                    results.append(
                        ItemValidationResult(
                            item_id=item_id,
                            item_type=item_type,
                            verification_status=VerificationStatus.CONTRADICTION_DETECTED,
                            details=(
                                f"Contradiction detected ({cp['id']}): Item relies on {doc_id} §{sec_id} "
                                f"({cp['claim_a']}) which is superseded by higher-precedence source {auth_doc} §{auth_sec} "
                                f"({cp['claim_b']}). Ruling: {cp['ruling']}."
                            ),
                            source_references=[f"{doc_id}§{sec_id}", f"{auth_doc}§{auth_sec}"],
                        )
                    )

                text_content = (
                    f"{item.get('title', '')} {item.get('description', '')} "
                    f"{item.get('completion_criteria', '')} {item.get('question_text', '')}"
                ).lower()

                if "14 days" in text_content and ("refund" in text_content or "return" in text_content):
                    results.append(
                        ItemValidationResult(
                            item_id=item_id,
                            item_type=item_type,
                            verification_status=VerificationStatus.CONTRADICTION_DETECTED,
                            details="Contradiction detected: States 14-day refund window from FAQ-02 instead of authoritative 30-day window per SOP-02 §1.2.",
                            source_references=[f"{doc_id}§{sec_id}", "SOP-02§1.2"],
                        )
                    )
                elif "15 vacation days" in text_content or "15 days of vacation" in text_content:
                    results.append(
                        ItemValidationResult(
                            item_id=item_id,
                            item_type=item_type,
                            verification_status=VerificationStatus.CONTRADICTION_DETECTED,
                            details="Contradiction detected: States 15 vacation days from FAQ-01 instead of authoritative 20 vacation days per POL-02 §1.1.",
                            source_references=[f"{doc_id}§{sec_id}", "POL-02§1.1"],
                        )
                    )

        return results
