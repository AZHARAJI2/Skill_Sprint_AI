"""Repositories for documents, chunks, and logical revisions."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from database.base import BaseRepository
from src.documents.models import Document, DocumentChunk, DocumentRevision


class DocumentRepository(BaseRepository[Document]):
    """Data access for uploaded document files."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Document)

    def get_by_hash(self, file_hash: str) -> Document | None:
        """Return the document with this SHA-256 hash, if any."""
        return self.session.query(Document).filter(Document.file_hash == file_hash).one_or_none()

    def list_by_document_id(self, document_id: str) -> list[Document]:
        """Return all stored files for a logical document_id."""
        return list(self.session.query(Document).filter(Document.document_id == document_id).all())

    def list_hashes(self) -> set[str]:
        """Return every stored file hash for duplicate detection."""
        rows = self.session.query(Document.file_hash).all()
        return {row[0] for row in rows}

    def list_active(self) -> list[Document]:
        """Return files currently marked active."""
        return list(self.session.query(Document).filter(Document.status == "active").all())


class ChunkRepository(BaseRepository[DocumentChunk]):
    """Data access for parsed chunks."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, DocumentChunk)

    def list_by_document_id(self, document_id: str) -> list[DocumentChunk]:
        """Return all chunks for a logical document_id (all formats/versions)."""
        return list(self.session.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all())

    def list_all(self) -> list[DocumentChunk]:
        """Return every stored chunk. Plan generation filters by source document in Python."""
        return list(self.session.query(DocumentChunk).all())

    def list_unique_sections(self) -> list[DocumentChunk]:
        """Return one representative chunk per (document_id, section_id) from DOCX when possible."""
        chunks = list(self.session.query(DocumentChunk).all())
        chosen: dict[tuple[str, str], DocumentChunk] = {}
        for chunk in chunks:
            key = (chunk.document_id, chunk.section_id)
            existing = chosen.get(key)
            if existing is None:
                chosen[key] = chunk
            elif (chunk.document.file_type if chunk.document else "") == "docx":
                chosen[key] = chunk
        return list(chosen.values())


class DocumentRevisionRepository(BaseRepository[DocumentRevision]):
    """Data access for logical document versions (active vs obsolete)."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, DocumentRevision)

    def list_by_document_id(self, document_id: str) -> list[DocumentRevision]:
        """Return all known versions of a document_id."""
        return list(
            self.session.query(DocumentRevision).filter(DocumentRevision.document_id == document_id).all()
        )

    def upsert(
        self,
        document_id: str,
        version: str,
        status: str,
        effective_date: date | None,
        notes: str | None,
    ) -> DocumentRevision:
        """Insert or update a logical version row."""
        existing = (
            self.session.query(DocumentRevision)
            .filter(DocumentRevision.document_id == document_id, DocumentRevision.version == version)
            .one_or_none()
        )
        if existing is None:
            existing = DocumentRevision(
                document_id=document_id,
                version=version,
                status=status,
                effective_date=effective_date,
                notes=notes,
            )
            self.add(existing)
            return existing
        existing.status = status
        if effective_date is not None:
            existing.effective_date = effective_date
        if notes:
            existing.notes = notes
        return existing
