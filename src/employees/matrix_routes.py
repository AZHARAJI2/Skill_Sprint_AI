"""Role Requirement Matrix load and query API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from config.settings import settings
from database.base import get_session
from role_matrix.load_matrix import load_matrix
from role_matrix.repository import RoleMatrixRepository
from src.auth.dependencies import require_role
from src.auth.models import User

router = APIRouter(prefix="/api/matrix", tags=["matrix"])


@router.post("/load")
def load_seed_matrix(
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager")),
) -> dict:
    """Load the approved seed CSV into role_requirements with row validation."""
    del user
    result = load_matrix(session, settings.matrix_csv_path, replace_existing=True)
    return {"loaded": result.loaded, "rejected": result.rejected}


@router.get("")
def list_matrix(
    role: str | None = Query(default=None),
    mandatory_only: bool = Query(default=False),
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer", "Manager")),
) -> dict:
    """Query stored matrix rows."""
    del user
    repo = RoleMatrixRepository(session)
    if role:
        rows = repo.get_by_role(role)
    elif mandatory_only:
        rows = repo.get_mandatory()
    else:
        rows = repo.list_all()
    return {
        "count": len(rows),
        "items": [
            {
                "requirement_id": r.requirement_id,
                "role": r.role,
                "department": r.department,
                "requirement_text": r.requirement_text,
                "mandatory": r.mandatory,
                "priority": r.priority,
                "due_stage": r.due_stage,
                "source_document_id": r.source_document_id,
                "source_section_id": r.source_section_id,
                "competency": r.competency,
                "assessment_requirement": r.assessment_requirement,
            }
            for r in rows
        ],
    }
