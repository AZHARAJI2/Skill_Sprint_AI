"""Phase 3 Step 46: Requirement-level Python vs GenAI Comparison Engine (≥100 comparisons)."""

from __future__ import annotations

from typing import Any


class ComparisonEngine:
    """Produces requirement-level comparisons between Python matrix expectations and GenAI outputs.
    
    Adheres strictly to Step 46:
    (Requirement ID, Python expected, GenAI result, Match/Mismatch, Source, Status)
    """

    def compare_requirements(
        self,
        matrix_entries: list[Any],
        plan: dict[str, Any] | Any,
    ) -> list[dict[str, Any]]:
        payload = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else plan
        comparisons: list[dict[str, Any]] = []

        # Index GenAI outputs by requirement ID
        genai_covered_ids: set[str] = set()
        genai_item_map: dict[str, list[dict[str, Any]]] = {}

        for mod in payload.get("modules", []):
            for r_id in mod.get("requirement_ids", []):
                genai_covered_ids.add(r_id)
                genai_item_map.setdefault(r_id, []).append({
                    "type": "module",
                    "id": mod.get("module_id"),
                    "title": mod.get("title"),
                    "stage": mod.get("stage"),
                    "doc": mod.get("source_document_id"),
                    "sec": mod.get("source_section_id"),
                })

        for task in payload.get("tasks", []):
            src_req = task.get("source_requirement_id")
            if src_req:
                genai_covered_ids.add(src_req)
                genai_item_map.setdefault(src_req, []).append({
                    "type": "task",
                    "id": task.get("task_id"),
                    "title": task.get("description", "")[:50],
                    "stage": task.get("due_stage"),
                    "doc": task.get("source_document_id"),
                    "sec": task.get("source_section_id"),
                })

        # Produce comparison record for every matrix entry
        for row in matrix_entries:
            r_id = getattr(row, "requirement_id", None) or (row.get("requirement_id") if isinstance(row, dict) else "")
            if not r_id:
                continue

            r_role = getattr(row, "role", "") or (row.get("role", "") if isinstance(row, dict) else "")
            r_text = getattr(row, "requirement_text", "") or (row.get("requirement_text", "") if isinstance(row, dict) else "")
            r_mand = getattr(row, "mandatory", False) if hasattr(row, "mandatory") else (row.get("mandatory", False) if isinstance(row, dict) else False)
            r_stage = getattr(row, "due_stage", "") or (row.get("due_stage", "") if isinstance(row, dict) else "")
            r_doc = getattr(row, "source_document_id", "") or (row.get("source_document_id", "") if isinstance(row, dict) else "")
            r_sec = getattr(row, "source_section_id", "") or (row.get("source_section_id", "") if isinstance(row, dict) else "")

            is_covered = r_id in genai_covered_ids
            items = genai_item_map.get(r_id, [])

            if is_covered:
                match_status = "Match"
                status_label = "Covered"
                first_item = items[0]
                genai_result = f"Covered in {first_item['type']} {first_item['id']} at stage '{first_item.get('stage')}'"
            else:
                match_status = "Mismatch" if r_mand else "Match"
                status_label = "Missing Mandatory" if r_mand else "Optional Not Scheduled"
                genai_result = "Not included in generated onboarding plan"

            comparisons.append({
                "requirement_id": r_id,
                "role": r_role,
                "python_expected": f"{r_text} [Mandatory: {r_mand}, Stage: {r_stage}]",
                "genai_result": genai_result,
                "match_status": match_status,
                "source": f"{r_doc} §{r_sec}",
                "status": status_label,
            })

        return comparisons
