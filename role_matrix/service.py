"""Human-reviewed role requirement creation for the onboarding matrix."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from datetime import datetime

from role_matrix.models import RequirementMatrixEntry, RoleRequirementDraft
from role_matrix.repository import RoleMatrixRepository, RoleRequirementDraftRepository
from schemas.common_schema import STAGE_ORDER
from src.documents.repository import ChunkRepository, DocumentRepository
from src.employees.service import RoleService
from src.errors import AppError
from src.reviews.repository import AuditRepository


class RoleRequirementService:
    """Submit, review, and activate source-linked role requirements."""

    _PRIORITIES = frozenset({"High", "Medium", "Low"})

    def __init__(self, session: Session) -> None:
        self.matrix = RoleMatrixRepository(session)
        self.drafts = RoleRequirementDraftRepository(session)
        self.roles = RoleService(session)
        self.documents = DocumentRepository(session)
        self.chunks = ChunkRepository(session)
        self.audit = AuditRepository(session)

    def submit(
        self,
        *,
        role_title: str,
        requirement_text: str,
        mandatory: bool,
        priority: str,
        due_stage: str,
        source_document_id: str,
        source_section_id: str,
        competency: str,
        assessment_requirement: str,
        actor: str,
    ) -> RoleRequirementDraft:
        """Save one proposed requirement for human review, not active generation."""
        role = next((item for item in self.roles.list_roles() if item.title == role_title), None)
        if role is None:
            raise AppError("Create the job role before adding its training requirements.", status_code=400)
        if priority not in self._PRIORITIES:
            raise AppError("Priority must be High, Medium, or Low.", status_code=400)
        if due_stage not in STAGE_ORDER:
            raise AppError("Choose a valid onboarding stage.", status_code=400)
        if not all(
            value.strip()
            for value in (requirement_text, source_document_id, source_section_id, competency, assessment_requirement)
        ):
            raise AppError("Complete every requirement field before saving.", status_code=400)
        if not any(document.document_id == source_document_id for document in self.documents.list_active()):
            raise AppError("Choose an active uploaded source document.", status_code=400)
        if not any(
            chunk.document_id == source_document_id and chunk.section_id == source_section_id
            for chunk in self.chunks.list_unique_sections()
        ):
            raise AppError("Choose a section that exists in the selected source document.", status_code=400)

        draft = RoleRequirementDraft(
            role_title=role.title,
            department=role.department,
            requirement_text=requirement_text.strip(),
            mandatory=mandatory,
            priority=priority,
            due_stage=due_stage,
            source_document_id=source_document_id.strip(),
            source_section_id=source_section_id.strip(),
            competency=competency.strip(),
            assessment_requirement=assessment_requirement.strip(),
            submitted_by=actor,
        )
        self.drafts.add(draft)
        self.audit.record(
            actor,
            "role_requirement_submitted",
            "role_requirement_draft",
            str(draft.id),
            {"role": role.title, "source": f"{source_document_id}§{source_section_id}"},
        )
        return draft

    def list_drafts(self, status: str | None = None) -> list[RoleRequirementDraft]:
        """Return draft requirements for the setup and review views."""
        return self.drafts.list_by_status(status)

    def approve(self, draft_id: int, reviewer: str, comment: str | None = None) -> RequirementMatrixEntry:
        """Approve a pending draft and publish it to the active role matrix."""
        draft = self._get_pending(draft_id)
        self._ensure_not_duplicate(draft)
        entry = RequirementMatrixEntry(
            requirement_id=self._next_requirement_id(),
            role=draft.role_title,
            department=draft.department,
            requirement_text=draft.requirement_text,
            mandatory=draft.mandatory,
            priority=draft.priority,
            due_stage=draft.due_stage,
            source_document_id=draft.source_document_id,
            source_section_id=draft.source_section_id,
            competency=draft.competency,
            assessment_requirement=draft.assessment_requirement,
        )
        self.matrix.add(entry)
        draft.status = "approved"
        draft.reviewer = reviewer
        draft.review_comment = comment.strip() if comment else None
        draft.reviewed_at = datetime.utcnow()
        self.audit.record(
            reviewer,
            "role_requirement_approved",
            "role_requirement",
            entry.requirement_id,
            {"draft_id": draft.id, "role": entry.role, "source": f"{entry.source_document_id}§{entry.source_section_id}"},
        )
        return entry

    def reject(self, draft_id: int, reviewer: str, comment: str) -> RoleRequirementDraft:
        """Reject a pending draft with a required reviewer reason."""
        if not comment or not comment.strip():
            raise AppError("A rejection reason is required.", status_code=400)
        draft = self._get_pending(draft_id)
        draft.status = "rejected"
        draft.reviewer = reviewer
        draft.review_comment = comment.strip()
        draft.reviewed_at = datetime.utcnow()
        self.audit.record(
            reviewer,
            "role_requirement_rejected",
            "role_requirement_draft",
            str(draft.id),
            {"role": draft.role_title, "reason": draft.review_comment},
        )
        return draft

    def _get_pending(self, draft_id: int) -> RoleRequirementDraft:
        """Fetch a draft that has not already received a final decision."""
        draft = self.drafts.get(draft_id)
        if draft is None:
            raise AppError("Requirement draft not found.", status_code=404)
        if draft.status != "pending_review":
            raise AppError("This requirement draft has already been reviewed.", status_code=409)
        return draft

    def _ensure_not_duplicate(self, draft: RoleRequirementDraft) -> None:
        """Prevent publishing the same approved requirement twice."""
        duplicate = next(
            (
                entry
                for entry in self.matrix.get_by_role(draft.role_title)
                if entry.role == draft.role_title
                and entry.requirement_text == draft.requirement_text
                and entry.source_document_id == draft.source_document_id
                and entry.source_section_id == draft.source_section_id
            ),
            None,
        )
        if duplicate:
            raise AppError("An identical approved requirement already exists for this role.", status_code=409)

    def _next_requirement_id(self) -> str:
        """Generate the next matrix ID from persisted rows without hard-coding roles."""
        highest = 0
        for entry in self.matrix.list_all():
            match = re.fullmatch(r"R(\d+)", entry.requirement_id or "")
            if match:
                highest = max(highest, int(match.group(1)))
        return f"R{highest + 1:03d}"
