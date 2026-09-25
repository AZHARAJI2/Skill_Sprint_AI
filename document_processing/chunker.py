"""Turn parsed sections into DocumentChunk entities with traceability metadata."""

from __future__ import annotations

from src.documents.models import DocumentChunk
from document_processing.parser import ParsedDocument, ParsedSection


class DocumentChunker:
    """Creates one chunk per numbered section so later phases can cite source_section_id."""

    def chunk(self, document_pk: int, parsed: ParsedDocument) -> list[DocumentChunk]:
        """Map each ParsedSection to a persistence DocumentChunk."""
        chunks: list[DocumentChunk] = []
        for index, section in enumerate(parsed.sections):
            chunks.append(self._from_section(document_pk, parsed.document_id, index, section))
        return chunks

    def _from_section(
        self, document_pk: int, document_id: str, index: int, section: ParsedSection
    ) -> DocumentChunk:
        return DocumentChunk(
            document_pk=document_pk,
            document_id=document_id,
            section_id=section.section_id,
            heading=section.heading,
            content=section.content,
            page_number=section.page_number,
            paragraph_ref=section.paragraph_ref,
            chunk_index=index,
            is_mandatory=section.is_mandatory,
            is_optional=section.is_optional,
            is_role_specific=section.is_role_specific,
            flags=section.flags,
        )
