"""VG-1.6: every architecture entity has a SQLAlchemy table."""

from __future__ import annotations

from sqlalchemy import inspect


def test_all_architecture_tables_exist(session) -> None:
    """Schema created in Phase 1 includes tables later phases will write to."""
    tables = set(inspect(session.get_bind()).get_table_names())
    required = {
        "documents",
        "document_chunks",
        "document_revisions",
        "employees",
        "roles",
        "role_requirements",
        "users",
        "onboarding_plans",
        "learning_modules",
        "checklists",
        "tasks",
        "quizzes",
        "assessments",
        "validation_reports",
        "review_decisions",
        "audit_log",
        "prompt_templates",
        "generation_metadata",
    }
    missing = required - tables
    assert not missing, f"missing tables: {missing}"
