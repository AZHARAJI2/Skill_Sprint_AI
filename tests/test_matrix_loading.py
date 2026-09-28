"""Tests for Role Requirement Matrix CSV loading and rejection rules."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from config.settings import settings
from role_matrix.load_matrix import MatrixLoader
from role_matrix.repository import RoleMatrixRepository
from src.errors import AppError


def test_load_approved_seed_csv(session) -> None:
    """VG-1.2: load all valid rows from the human-reviewed seed CSV."""
    result = MatrixLoader().load(session, settings.matrix_csv_path)
    repo = RoleMatrixRepository(session)
    assert result.loaded == 178
    assert result.rejected == []
    assert repo.count() == 178
    assert repo.get_by_requirement_id("R001") is not None
    assert len(repo.get_mandatory()) >= 50
    assert len(repo.get_by_role("Recruiter")) >= 1


def test_reject_malformed_and_duplicate_ids(session, tmp_path: Path) -> None:
    """Malformed IDs, missing columns in a row, and duplicate IDs are rejected."""
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text(
        "requirement_id,role,department,requirement_text,mandatory,priority,due_stage,"
        "source_document_id,source_section_id,competency,assessment_requirement\n"
        "R001,All Roles,Company-wide,Valid,TRUE,High,Day 1,HANDBOOK-01,1.1,Policy,Quiz\n"
        "bad-id,All Roles,Company-wide,Bad id,TRUE,High,Day 1,HANDBOOK-01,1.1,Policy,Quiz\n"
        "R002,All Roles,Company-wide,,TRUE,High,Day 1,HANDBOOK-01,1.1,Policy,Quiz\n"
        "R001,All Roles,Company-wide,Duplicate,TRUE,High,Day 1,HANDBOOK-01,1.1,Policy,Quiz\n"
        "R003,All Roles,Company-wide,OK,TRUE,High,Day 1,HANDBOOK-01,1.1,Policy,Quiz\n",
        encoding="utf-8",
    )
    result = MatrixLoader().load(session, csv_path)
    assert result.loaded == 2
    assert any("malformed requirement_id" in item for item in result.rejected)
    assert any("duplicate requirement_id" in item for item in result.rejected)
    assert any("missing requirement_text" in item for item in result.rejected)
    assert RoleMatrixRepository(session).count() == 2


def test_missing_file_raises(session, tmp_path: Path) -> None:
    """Loader fails clearly when the CSV path does not exist."""
    with pytest.raises(AppError) as exc:
        MatrixLoader().load(session, tmp_path / "missing.csv")
    assert exc.value.status_code == 404


def test_uploaded_matrix_frame_appends_and_rejects_existing_ids(session) -> None:
    """A ready CSV import preserves the active matrix and cannot overwrite an existing ID."""
    frame = pd.DataFrame(
        [
            {
                "requirement_id": "R900",
                "role": "Test Analyst",
                "department": "Test",
                "requirement_text": "Complete approved training.",
                "mandatory": "TRUE",
                "priority": "High",
                "due_stage": "Week 1",
                "source_document_id": "ROLE-99",
                "source_section_id": "1.1",
                "competency": "Testing",
                "assessment_requirement": "Manager confirmation",
            }
        ]
    )
    loader = MatrixLoader()
    assert loader.load_frame(session, frame, replace_existing=False).loaded == 1
    with pytest.raises(AppError) as exc:
        loader.load_frame(session, frame, replace_existing=False)
    assert exc.value.status_code == 409
