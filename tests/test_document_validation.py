"""Document version-control unit tests."""

from __future__ import annotations

from config.settings import settings
from src.documents.repository import DocumentRepository, DocumentRevisionRepository
from src.documents.service import DocumentService


def test_older_logical_version_marked_obsolete(session) -> None:
    """When v2 is ingested, recorded v1 from revision history is obsolete."""
    path = settings.sample_documents_dir / "sops" / "SOP-01_Engineering-Deployment-SOP.docx"
    DocumentService(session).ingest_file(path)
    files = DocumentRepository(session).list_by_document_id("SOP-01")
    assert files[0].status == "active"
    revisions = DocumentRevisionRepository(session).list_by_document_id("SOP-01")
    assert any(rev.version == "v1" and rev.status == "obsolete" for rev in revisions)
    assert any(rev.version == "v2" and rev.status == "active" for rev in revisions)
