"""Draft-to-approval tests for human-reviewed role requirements."""

from __future__ import annotations

from src.documents.models import Document, DocumentChunk
from src.employees.service import RoleService
from role_matrix.repository import RoleMatrixRepository
from role_matrix.service import RoleRequirementService


def _source(session) -> None:
    """Create one active role source and a real parsed section for test review."""
    document = Document(
        document_id="ROLE-99",
        title="Test Analyst Role Description",
        name="ROLE-99.docx",
        file_type="docx",
        version="v1",
        status="active",
        file_hash="role-99-hash",
        file_path="/tmp/ROLE-99.docx",
    )
    session.add(document)
    session.flush()
    session.add(
        DocumentChunk(
            document_pk=document.id,
            document_id="ROLE-99",
            section_id="2.1",
            heading="Monitoring",
            content="Monitor security alerts.",
            page_number=1,
            paragraph_ref="p1",
            chunk_index=0,
        )
    )
    session.flush()


def test_requirement_draft_is_not_active_until_human_approval(session) -> None:
    """Only a reviewed draft reaches the matrix used by plan generation."""
    RoleService(session).create("Test Analyst", "Security")
    _source(session)
    service = RoleRequirementService(session)

    draft = service.submit(
        role_title="Test Analyst",
        requirement_text="Monitor and triage security alerts.",
        mandatory=True,
        priority="High",
        due_stage="Week 1",
        source_document_id="ROLE-99",
        source_section_id="2.1",
        competency="Alert Monitoring",
        assessment_requirement="Manager reviews one alert triage.",
        actor="training.manager",
    )

    assert draft.status == "pending_review"
    assert draft.submitted_by == "training.manager"
    assert RoleMatrixRepository(session).get_by_role("Test Analyst") == []

    active = service.approve(draft.id, reviewer="reviewer", comment="Matches the approved role source.")

    assert active.requirement_id.startswith("R")
    assert RoleMatrixRepository(session).get_by_role("Test Analyst")[-1].requirement_id == active.requirement_id
    assert service.list_drafts()[0].status == "approved"
