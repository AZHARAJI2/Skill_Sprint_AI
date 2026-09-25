"""Compute corpus metrics from parsed chunks so VG-1.3 is verified from real files."""

from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from src.documents.models import DocumentChunk
from src.documents.repository import DocumentRepository, DocumentRevisionRepository


class CorpusMetricsService:
    """Aggregates parsed-section counts without trusting the CSV or the markdown index."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def compute(self) -> dict:
        """Return unique-document and unique-section metrics used by verification tests."""
        documents = DocumentRepository(self.session).list_all()
        unique_doc_ids = {d.document_id for d in documents}
        revisions = DocumentRevisionRepository(self.session).list_all()
        chunks = (
            self.session.query(DocumentChunk)
            .options(joinedload(DocumentChunk.document))
            .all()
        )
        has_docx = {doc.document_id for doc in documents if doc.file_type == "docx"}
        canonical = []
        for chunk in chunks:
            if chunk.document is None:
                continue
            if chunk.document_id in has_docx and chunk.document.file_type != "docx":
                continue
            canonical.append(chunk)

        grouped: dict[tuple[str, str], list[DocumentChunk]] = {}
        for chunk in canonical:
            grouped.setdefault((chunk.document_id, chunk.section_id), []).append(chunk)

        def _pick(chunks: list[DocumentChunk]) -> DocumentChunk:
            """Prefer a tagged/richer chunk when the same section_id appears more than once."""
            return sorted(
                chunks,
                key=lambda c: (
                    int(c.is_mandatory),
                    int(c.is_optional),
                    int(c.is_role_specific),
                    len(c.content or ""),
                ),
                reverse=True,
            )[0]

        unique_sections = {key: _pick(group) for key, group in grouped.items()}
        section_list = list(unique_sections.values())
        mandatory = sum(
            1 for key, group in grouped.items() if any(c.is_mandatory for c in group)
        )
        optional = sum(
            1 for key, group in grouped.items() if any(c.is_optional for c in group)
        )
        role_specific = sum(
            1
            for key, group in grouped.items()
            if any(c.is_role_specific or c.document_id.startswith("ROLE-") for c in group)
        )
        conflict = sum(
            1
            for group in grouped.values()
            if any((c.flags or {}).get("conflict_mentioned") for c in group)
        )
        adversarial = sum(
            1 for group in grouped.values() if any((c.flags or {}).get("adversarial") for c in group)
        )
        version_change_sections = sum(
            1
            for group in grouped.values()
            if any((c.flags or {}).get("version_change") for c in group)
        )
        obsolete_revisions = [r for r in revisions if r.status == "obsolete"]
        file_types = {}
        for doc in documents:
            file_types[doc.file_type] = file_types.get(doc.file_type, 0) + 1
        return {
            "file_count": len(documents),
            "unique_document_ids": len(unique_doc_ids),
            "document_ids": sorted(unique_doc_ids),
            "unique_sections": len(section_list),
            "mandatory_sections": mandatory,
            "optional_sections": optional,
            "role_specific_sections": role_specific,
            "conflict_mentioned_sections": conflict,
            "adversarial_sections": adversarial,
            "version_change_sections": version_change_sections,
            "obsolete_revision_count": len(obsolete_revisions),
            "revision_count": len(revisions),
            "files_by_type": file_types,
        }
