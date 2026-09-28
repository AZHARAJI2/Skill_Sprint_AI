"""Role Requirement Matrix load and query API."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config.settings import settings
from database.base import get_session
from role_matrix.load_matrix import load_matrix
from role_matrix.load_matrix import MatrixLoader
from role_matrix.repository import RoleMatrixRepository
from src.auth.dependencies import require_role
from src.auth.models import User
from src.errors import AppError
from role_matrix.service import RoleRequirementService

router = APIRouter(prefix="/api/matrix", tags=["matrix"])


class RoleRequirementCreate(BaseModel):
    """Proposed training requirement linked to one uploaded source section."""

    role_title: str
    requirement_text: str
    mandatory: bool = True
    priority: str = "High"
    due_stage: str
    source_document_id: str
    source_section_id: str
    competency: str
    assessment_requirement: str


@router.post("/requirements")
def create_role_requirement(
    body: RoleRequirementCreate,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager")),
) -> dict:
    """Submit a source-verified requirement for human review."""
    draft = RoleRequirementService(session).submit(actor=user.username, **body.model_dump())
    return {
        "draft_id": draft.id,
        "status": draft.status,
        "role": draft.role_title,
        "source_document_id": draft.source_document_id,
        "source_section_id": draft.source_section_id,
    }


class RoleRequirementReview(BaseModel):
    """Reviewer note recorded with an approval or rejection."""

    comment: str | None = None


@router.get("/requirements/drafts")
def list_requirement_drafts(
    status: str | None = Query(default=None),
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer")),
) -> list[dict]:
    """List proposed requirements and their human-review status."""
    del user
    return [_draft_payload(draft) for draft in RoleRequirementService(session).list_drafts(status)]


@router.post("/requirements/drafts/{draft_id}/approve")
def approve_requirement_draft(
    draft_id: int,
    body: RoleRequirementReview,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Reviewer")),
) -> dict:
    """Publish a reviewed draft into the active role matrix."""
    entry = RoleRequirementService(session).approve(draft_id, reviewer=user.username, comment=body.comment)
    return {"status": "approved", "requirement_id": entry.requirement_id, "role": entry.role}


@router.post("/requirements/drafts/{draft_id}/reject")
def reject_requirement_draft(
    draft_id: int,
    body: RoleRequirementReview,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Reviewer")),
) -> dict:
    """Reject a draft and preserve the review reason."""
    draft = RoleRequirementService(session).reject(draft_id, reviewer=user.username, comment=body.comment or "")
    return {"status": draft.status, "draft_id": draft.id}


def _draft_payload(draft) -> dict:
    """Return a draft requirement without ORM internals."""
    return {
        "id": draft.id,
        "role_title": draft.role_title,
        "department": draft.department,
        "requirement_text": draft.requirement_text,
        "mandatory": draft.mandatory,
        "priority": draft.priority,
        "due_stage": draft.due_stage,
        "source_document_id": draft.source_document_id,
        "source_section_id": draft.source_section_id,
        "competency": draft.competency,
        "assessment_requirement": draft.assessment_requirement,
        "status": draft.status,
        "submitted_by": draft.submitted_by,
        "reviewer": draft.reviewer,
        "review_comment": draft.review_comment,
        "submitted_at": draft.submitted_at.isoformat() if draft.submitted_at else None,
        "reviewed_at": draft.reviewed_at.isoformat() if draft.reviewed_at else None,
    }


@router.post("/load")
def load_seed_matrix(
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager")),
) -> dict:
    """Load the approved seed CSV into role_requirements with row validation."""
    del user
    result = load_matrix(session, settings.matrix_csv_path, replace_existing=True)
    return {"loaded": result.loaded, "rejected": result.rejected}


@router.get("/template")
def download_matrix_template(
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer")),
) -> FileResponse:
    """Download the blank CSV structure for an approved role-requirement matrix."""
    del user
    template = settings.project_root / "role_matrix" / "role_requirement_matrix_template.csv"
    return FileResponse(template, media_type="text/csv", filename="role_requirement_matrix_template.csv")


@router.post("/import")
async def import_approved_matrix(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Reviewer")),
) -> dict:
    """Append a pre-approved requirements CSV after structural validation and audit logging."""
    filename = file.filename or "role-requirement-matrix.csv"
    if Path(filename).suffix.lower() != ".csv":
        raise AppError("Role requirement matrix imports must be CSV files.", status_code=400)
    raw = await file.read()
    if not raw:
        raise AppError("The CSV file is empty.", status_code=400)
    if len(raw) > settings.max_upload_bytes:
        raise AppError("The CSV file exceeds the 20 MB upload limit.", status_code=413)
    try:
        frame = pd.read_csv(io.StringIO(raw.decode("utf-8-sig")), dtype=str, keep_default_na=False)
    except (UnicodeDecodeError, pd.errors.ParserError) as exc:
        raise AppError("Could not read this CSV file. Save it as UTF-8 CSV and try again.", status_code=400) from exc
    result = MatrixLoader().load_frame(
        session,
        frame,
        replace_existing=False,
        actor=user.username,
        source_name=filename,
    )
    return {
        "loaded": result.loaded,
        "rejected": result.rejected,
        "message": f"Imported {result.loaded} approved requirement(s). Existing matrix rows were kept.",
    }


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
