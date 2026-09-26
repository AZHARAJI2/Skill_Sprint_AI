"""Phase 3 Steps 44 & 45: GenAI output consistency tester and Consistency Score computation."""

from __future__ import annotations

from typing import Any


class ConsistencyTester:
    """Evaluates consistency across multiple GenAI generation passes on structured attributes only.
    
    Compares structured business fields (learning objectives, stage, difficulty, sources)
    rather than brittle natural language phrasing (Step 45).
    """

    def compare_runs(
        self,
        run_a: dict[str, Any] | Any,
        run_b: dict[str, Any] | Any,
    ) -> dict[str, Any]:
        data_a = run_a.model_dump(mode="json") if hasattr(run_a, "model_dump") else run_a
        data_b = run_b.model_dump(mode="json") if hasattr(run_b, "model_dump") else run_b

        total_checks = 0
        matching_checks = 0
        differences: list[dict[str, Any]] = []

        # 1. Compare modules by ID
        mods_a = {m.get("module_id"): m for m in data_a.get("modules", []) if m.get("module_id")}
        mods_b = {m.get("module_id"): m for m in data_b.get("modules", []) if m.get("module_id")}

        all_mod_ids = set(mods_a.keys()).union(mods_b.keys())
        for m_id in sorted(all_mod_ids):
            total_checks += 3  # stage, difficulty, source_doc
            ma = mods_a.get(m_id)
            mb = mods_b.get(m_id)
            if not ma or not mb:
                differences.append({
                    "item_id": m_id,
                    "attribute": "presence",
                    "val_a": bool(ma),
                    "val_b": bool(mb),
                })
                continue

            if ma.get("stage") == mb.get("stage"):
                matching_checks += 1
            else:
                differences.append({"item_id": m_id, "attribute": "stage", "val_a": ma.get("stage"), "val_b": mb.get("stage")})

            if ma.get("difficulty") == mb.get("difficulty"):
                matching_checks += 1
            else:
                differences.append({"item_id": m_id, "attribute": "difficulty", "val_a": ma.get("difficulty"), "val_b": mb.get("difficulty")})

            if ma.get("source_document_id") == mb.get("source_document_id"):
                matching_checks += 1
            else:
                differences.append({"item_id": m_id, "attribute": "source_document_id", "val_a": ma.get("source_document_id"), "val_b": mb.get("source_document_id")})

        # 2. Compare tasks by source requirement
        tasks_a = {t.get("source_requirement_id"): t for t in data_a.get("tasks", []) if t.get("source_requirement_id")}
        tasks_b = {t.get("source_requirement_id"): t for t in data_b.get("tasks", []) if t.get("source_requirement_id")}

        all_req_ids = set(tasks_a.keys()).union(tasks_b.keys())
        for r_id in sorted(all_req_ids):
            total_checks += 2  # stage, difficulty
            ta = tasks_a.get(r_id)
            tb = tasks_b.get(r_id)
            if not ta or not tb:
                differences.append({"requirement_id": r_id, "attribute": "task_presence", "val_a": bool(ta), "val_b": bool(tb)})
                continue

            if ta.get("due_stage") == tb.get("due_stage"):
                matching_checks += 1
            else:
                differences.append({"requirement_id": r_id, "attribute": "due_stage", "val_a": ta.get("due_stage"), "val_b": tb.get("due_stage")})

            if ta.get("difficulty") == tb.get("difficulty"):
                matching_checks += 1
            else:
                differences.append({"requirement_id": r_id, "attribute": "difficulty", "val_a": ta.get("difficulty"), "val_b": tb.get("difficulty")})

        score = round((matching_checks / max(total_checks, 1)) * 100.0, 2) if total_checks > 0 else 100.0

        return {
            "consistency_score": score,
            "total_checks": total_checks,
            "matching_checks": matching_checks,
            "differences_count": len(differences),
            "differences": differences,
        }
