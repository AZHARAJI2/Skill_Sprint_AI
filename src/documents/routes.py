"""Document upload, list, chunk, ingest-sample, and metrics endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from config.settings import settings
from database.base import get_session
from src.auth.dependencies import require_role
from src.auth.models import User
from src.documents.metrics import CorpusMetricsService
from src.documents.repository import ChunkRepository, DocumentRepository, DocumentRevisionRepository
from src.documents.service import DocumentService

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager")),
) -> dict:
    """Upload one PDF/DOCX/TXT/MD/CSV file through the ingest pipeline."""
    raw = await file.read()
    document = DocumentService(session).ingest_bytes(file.filename or "upload.bin", raw, actor=user.username)
    return _document_payload(document)


@router.post("/ingest-sample")
def ingest_sample(
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager")),
) -> dict:
    """Run every file in sample_documents/ through the live ingest pipeline."""
    stored = DocumentService(session).ingest_directory(settings.sample_documents_dir, actor=user.username)
    metrics = CorpusMetricsService(session).compute()
    return {"ingested": len(stored), "metrics": metrics}


@router.get("")
def list_documents(
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer", "Manager")),
) -> list[dict]:
    """List stored documents."""
    del user
    return [_document_payload(doc) for doc in DocumentRepository(session).list_all()]


@router.get("/metrics")
def corpus_metrics(
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer")),
) -> dict:
    """Parsed-count verification against the competition minimums."""
    del user
    return CorpusMetricsService(session).compute()


@router.get("/revisions/{document_id}")
def list_revisions(
    document_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer")),
) -> list[dict]:
    """Show active vs obsolete logical versions for one document_id."""
    del user
    rows = DocumentRevisionRepository(session).list_by_document_id(document_id)
    return [
        {
            "document_id": r.document_id,
            "version": r.version,
            "status": r.status,
            "effective_date": r.effective_date.isoformat() if r.effective_date else None,
            "notes": r.notes,
        }
        for r in rows
    ]


@router.get("/{document_pk}/chunks")
def list_chunks(
    document_pk: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("Admin", "Training Manager", "Reviewer")),
) -> list[dict]:
    """Return chunks for one stored file row."""
    del user
    doc = DocumentRepository(session).get(document_pk)
    if doc is None:
        from src.errors import AppError

        raise AppError("Document not found", status_code=404)
    chunks = ChunkRepository(session).list_by_document_id(doc.document_id)
    return [
        {
            "id": c.id,
            "document_id": c.document_id,
            "section_id": c.section_id,
            "heading": c.heading,
            "page_number": c.page_number,
            "paragraph_ref": c.paragraph_ref,
            "is_mandatory": c.is_mandatory,
            "is_optional": c.is_optional,
            "is_role_specific": c.is_role_specific,
            "content": c.content,
            "flags": c.flags,
        }
        for c in chunks
        if c.document_pk == document_pk
    ]


def _document_payload(document) -> dict:
    return {
        "id": document.id,
        "document_id": document.document_id,
        "title": document.title,
        "name": document.name,
        "file_type": document.file_type,
        "version": document.version,
        "status": document.status,
        "effective_date": document.effective_date.isoformat() if document.effective_date else None,
        "department": document.department,
        "category": document.category,
        "file_hash": document.file_hash,
    }
