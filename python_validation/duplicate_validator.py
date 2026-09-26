"""Phase 3 Step 35: Duplicate learning detection across modules, tasks, and quizzes."""

from __future__ import annotations

import re
from typing import Any

from python_validation.base import BaseValidator
from schemas.common_schema import VerificationStatus
from schemas.plan_schema import GeneratedPlan
from schemas.validation_schema import ItemValidationResult


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"\b\w{3,}\b", text.lower())
    return set(words)


def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    if not set_a or not set_b:
        return 0.0
    return len(set_a.intersection(set_b)) / len(set_a.union(set_b))


class DuplicateValidator(BaseValidator):
    """Detects semantically duplicate or near-identical learning content."""

    def __init__(self, similarity_threshold: float = 0.85) -> None:
        self.threshold = similarity_threshold

    def validate(
        self,
        plan: GeneratedPlan | dict[str, Any],
        matrix: list[Any] | None = None,
        documents: list[Any] | None = None,
        chunks: list[Any] | None = None,
    ) -> list[ItemValidationResult]:
        payload = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else plan
        results: list[ItemValidationResult] = []

        item_categories = [
            ("modules", "learning_module", "module_id", "title"),
            ("tasks", "task_item", "task_id", "description"),
            ("checklists", "checklist_item", "item_id", "activity"),
            ("quizzes", "quiz_question", "question_id", "question_text"),
        ]

        for cat_key, item_type, id_field, text_field in item_categories:
            items = payload.get(cat_key, [])
            seen_items: list[tuple[str, str, set[str]]] = []

            for item in items:
                item_id = str(item.get(id_field, "UNKNOWN"))
                text = str(item.get(text_field) or "")
                tokens = _tokenize(text)

                if not tokens:
                    continue

                for prev_id, prev_text, prev_tokens in seen_items:
                    sim = _jaccard_similarity(tokens, prev_tokens)
                    if sim >= self.threshold or (len(text) > 15 and text.strip().lower() == prev_text.strip().lower()):
                        results.append(
                            ItemValidationResult(
                                item_id=item_id,
                                item_type=item_type,
                                verification_status=VerificationStatus.VERIFIED_WITH_WARNING,
                                details=f"Near-duplicate {item_type} detected: highly similar to item {prev_id} (similarity: {sim:.2f}).",
                                source_references=[f"{item.get('source_document_id', '')}§{item.get('source_section_id', '')}"],
                            )
                        )
                        break

                seen_items.append((item_id, text, tokens))

        return results
