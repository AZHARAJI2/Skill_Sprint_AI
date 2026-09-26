"""Phase 3 Step 36: Role relevance validation (flags valid but irrelevant content)."""

from __future__ import annotations

from typing import Any

from python_validation.base import BaseValidator
from schemas.common_schema import VerificationStatus
from schemas.plan_schema import GeneratedPlan
from schemas.validation_schema import ItemValidationResult

ROLE_DOC_MAP: dict[str, str] = {
    "Software Engineer": "ROLE-01",
    "DevOps/Infrastructure Engineer": "ROLE-02",
    "QA Engineer": "ROLE-03",
    "Customer Support Representative": "ROLE-04",
    "Payments Operations Specialist": "ROLE-05",
    "HR Generalist": "ROLE-06",
    "Recruiter": "ROLE-07",
    "Financial Analyst": "ROLE-08",
    "Accounts Payable Clerk": "ROLE-09",
    "Warehouse Operations Coordinator": "ROLE-10",
}

OTHER_ROLE_DOCS = {v: k for k, v in ROLE_DOC_MAP.items()}


class RoleRelevanceValidator(BaseValidator):
    """Ensures onboarding plan items are relevant to the target employee role."""

    def validate(
        self,
        plan: GeneratedPlan | dict[str, Any],
        matrix: list[Any] | None = None,
        documents: list[Any] | None = None,
        chunks: list[Any] | None = None,
    ) -> list[ItemValidationResult]:
        payload = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else plan
        results: list[ItemValidationResult] = []

        target_role = payload.get("role_title", "")
        allowed_role_doc = ROLE_DOC_MAP.get(target_role)

        item_groups = [
            ("modules", "learning_module", "module_id"),
            ("tasks", "task_item", "task_id"),
            ("checklists", "checklist_item", "item_id"),
            ("quizzes", "quiz_question", "question_id"),
        ]

        for cat_key, item_type, id_field in item_groups:
            items = payload.get(cat_key, [])
            for item in items:
                item_id = str(item.get(id_field, "UNKNOWN"))
                doc_id = item.get("source_document_id") or ""
                sec_id = item.get("source_section_id") or ""

                if doc_id.startswith("ROLE-") and allowed_role_doc and doc_id != allowed_role_doc:
                    other_role_name = OTHER_ROLE_DOCS.get(doc_id, doc_id)
                    results.append(
                        ItemValidationResult(
                            item_id=item_id,
                            item_type=item_type,
                            verification_status=VerificationStatus.VERIFIED_WITH_WARNING,
                            details=(
                                f"Role-relevance flag: Item {item_id} cites {doc_id} §{sec_id} "
                                f"which is specific to '{other_role_name}', but target employee is '{target_role}'."
                            ),
                            source_references=[f"{doc_id}§{sec_id}"],
                        )
                    )

        return results
