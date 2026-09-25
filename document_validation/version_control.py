"""Active vs obsolete document version management."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from config.logging_config import get_logger
from document_processing.parser import ParsedDocument
from src.documents.models import Document, DocumentRevision
from src.documents.repository import DocumentRepository, DocumentRevisionRepository

logger = get_logger("version_control")


class DocumentVersionController:
    """Keeps one active logical version per document_id; older versions become obsolete."""

    def apply(self, session: Session, stored: Document, parsed: ParsedDocument) -> None:
        """Upsert the current revision, mark older file rows obsolete, and record superseded versions."""
        doc_repo = DocumentRepository(session)
        rev_repo = DocumentRevisionRepository(session)

        current = parsed.version
        revision = rev_repo.upsert(
            document_id=parsed.document_id,
            version=current,
            status="active",
            effective_date=parsed.effective_date,
            notes=f"Ingested {stored.file_type} {stored.name}",
        )
        older_files = doc_repo.list_by_document_id(parsed.document_id)
        for other in older_files:
            if other.id == stored.id:
                continue
            if _version_rank(other.version) < _version_rank(current):
                other.status = "obsolete"
                logger.info(
                    "version_marked_obsolete document_id=%s version=%s file=%s",
                    other.document_id,
                    other.version,
                    other.name,
                )
        older_revisions = rev_repo.list_by_document_id(parsed.document_id)
        for other in older_revisions:
            if other.id == revision.id:
                continue
            if _version_rank(other.version) < _version_rank(current):
                other.status = "obsolete"

        for item in parsed.superseded_versions:
            version = item.get("version")
            if not version:
                continue
            effective = None
            raw_date = item.get("effective_date")
            if raw_date:
                try:
                    effective = datetime.strptime(raw_date, "%Y-%m-%d").date()
                except ValueError:
                    effective = None
            rev_repo.upsert(
                document_id=parsed.document_id,
                version=version,
                status="obsolete",
                effective_date=effective,
                notes=item.get("notes"),
            )
            logger.info(
                "superseded_version_recorded document_id=%s version=%s",
                parsed.document_id,
                version,
            )


def _version_rank(version: str) -> int:
    digits = "".join(ch for ch in version if ch.isdigit())
    return int(digits) if digits else 0
