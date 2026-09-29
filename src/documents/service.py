"""Orchestrates upload → validate → parse → chunk → version control → persist."""

from __future__ import annotations

from pathlib import Path
import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config.logging_config import get_logger
from document_processing.chunker import DocumentChunker
from document_processing.parser import DocumentParser
from document_processing.uploader import DocumentUploader
from document_processing.validator import DocumentFileValidator
from document_validation.version_control import DocumentVersionController
from src.documents.models import Document
from src.documents.repository import ChunkRepository, DocumentRepository
from src.employees.service import RoleService
from src.errors import AppError
from src.reviews.repository import AuditRepository
from security.injection_guard import InjectionGuard

logger = get_logger("document_service")


class DocumentService:
    """Single entry point for ingesting company documents from disk or HTTP uploads."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.documents = DocumentRepository(session)
        self.chunks = ChunkRepository(session)
        self.parser = DocumentParser()
        self.chunker = DocumentChunker()
        self.uploader = DocumentUploader()
        self.versions = DocumentVersionController()
        self.audit = AuditRepository(session)
        self.injection_guard = InjectionGuard()

    def ingest_file(self, path: Path, actor: str = "system") -> Document:
        """Read a file from disk and run the full ingest pipeline."""
        raw = path.read_bytes()
        return self.ingest_bytes(path.name, raw, actor=actor, original_path=str(path))

    def ingest_bytes(
        self,
        filename: str,
        raw_bytes: bytes,
        actor: str = "system",
        original_path: str | None = None,
        category_override: str | None = None,
    ) -> Document:
        """Validate, parse, store, chunk, and apply version control for one file."""
        validator = DocumentFileValidator(existing_hashes=self.documents.list_hashes())
        check = validator.require_ok(Path(filename), raw_bytes)
        parsed = self.parser.parse(Path(filename), raw_bytes)
        if not (parsed.full_text or "").strip():
            raise AppError("Empty document (no extractable text)", status_code=400, details=filename)

        # Every upload is untrusted input.  Scan the full extracted text before
        # persistence so a payload cannot disappear merely because it is not
        # part of a numbered section.  Section findings are retained on the
        # corresponding chunk for traceability and reporting.
        document_scan = self.injection_guard.scan(parsed.full_text, document_id=parsed.document_id)
        section_findings: list[dict] = []
        for section in parsed.sections:
            section_scan = self.injection_guard.scan(
                section.content,
                document_id=parsed.document_id,
                section_id=section.section_id,
            )
            section.flags = dict(section.flags or {})
            section.flags["prompt_injection_detected"] = section_scan.is_injection
            if section_scan.findings:
                section.flags["prompt_injection_findings"] = [
                    {"signature": finding.signature, "snippet": finding.snippet}
                    for finding in section_scan.findings
                ]
                section_findings.extend(
                    {
                        "section_id": section.section_id,
                        "signature": finding.signature,
                        "snippet": finding.snippet,
                    }
                    for finding in section_scan.findings
                )

        stored_path = self.uploader.save(parsed.document_id, filename, raw_bytes)
        document = Document(
            document_id=parsed.document_id,
            title=parsed.title,
            name=filename,
            file_type=parsed.file_type,
            version=parsed.version,
            effective_date=parsed.effective_date,
            expiry_date=parsed.expiry_date,
            department=parsed.department,
            category=category_override or parsed.category,
            status="active",
            file_hash=check.file_hash,
            file_path=str(stored_path),
            extra_metadata={
                "original_path": original_path,
                "upload_scope": category_override,
                "superseded_versions": parsed.superseded_versions,
                "section_count": len(parsed.sections),
                "prompt_injection_scan": {
                    "detected": document_scan.is_injection,
                    "findings": [
                        {"signature": finding.signature, "snippet": finding.snippet}
                        for finding in document_scan.findings
                    ],
                    "section_findings": section_findings,
                },
            },
        )
        try:
            with self.session.begin_nested():
                self.documents.add(document)
                self.session.flush()
                for chunk in self.chunker.chunk(document.id, parsed):
                    self.chunks.add(chunk)
                self.versions.apply(self.session, document, parsed)
        except IntegrityError as exc:
            raise AppError(
                "Duplicate document (same hash or same document_id+version+file_type)",
                status_code=409,
                details=str(exc.orig) if getattr(exc, "orig", None) else str(exc),
            ) from exc

        self.audit.record(
            actor=actor,
            action="document_ingested",
            entity_type="document",
            entity_id=parsed.document_id,
            details={
                "filename": filename,
                "version": parsed.version,
                "file_type": parsed.file_type,
                "sections": len(parsed.sections),
                "hash": check.file_hash,
            },
        )
        if document_scan.is_injection:
            self.audit.record(
                actor=actor,
                action="prompt_injection_detected",
                entity_type="document",
                entity_id=parsed.document_id,
                details={
                    "filename": filename,
                    "finding_count": len(document_scan.findings),
                    "section_findings": section_findings,
                    "handling": "stored_as_untrusted_data_and_redacted_from_generation_context",
                },
            )
        logger.info(
            "document_ingested document_id=%s version=%s type=%s sections=%s",
            parsed.document_id,
            parsed.version,
            parsed.file_type,
            len(parsed.sections),
        )
        self._create_role_from_description(document, actor)
        return document

    def _create_role_from_description(self, document: Document, actor: str) -> None:
        """Create a draft-ready job role when an uploaded ROLE document is unambiguous.

        The document remains only a source. Training requirements still require
        separate human review before they enter the active role matrix.
        """
        if not document.document_id.startswith("ROLE-") or not document.department:
            return
        title = re.sub(r"\s+Role\s+Description\s*$", "", document.title, flags=re.IGNORECASE).strip()
        if not title or title.casefold() == document.title.casefold():
            return
        role = RoleService(self.session).ensure_role(
            title=title,
            department=document.department,
            description=f"Created from approved source document {document.document_id}.",
            actor=actor,
        )
        self.audit.record(
            actor,
            "role_ready_for_requirements",
            "role",
            role.title,
            {"source_document_id": document.document_id, "auto_created": True},
        )

    def sync_roles_from_active_descriptions(self, actor: str) -> list[str]:
        """Create missing job roles from role descriptions uploaded before auto-setup existed."""
        created: list[str] = []
        for document in self.documents.list_active():
            if not document.document_id.startswith("ROLE-") or not document.department:
                continue
            title = re.sub(r"\s+Role\s+Description\s*$", "", document.title, flags=re.IGNORECASE).strip()
            if not title or title.casefold() == document.title.casefold():
                continue
            existed = any(role.title == title for role in RoleService(self.session).list_roles())
            self._create_role_from_description(document, actor)
            if not existed:
                created.append(title)
        return created

    def ingest_directory(self, root: Path, actor: str = "system") -> list[Document]:
        """Ingest every supported file under root (used for sample_documents end-to-end)."""
        stored: list[Document] = []
        files = sorted(
            p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".pdf", ".docx", ".txt", ".md", ".csv"}
        )
        errors: list[str] = []
        for path in files:
            try:
                stored.append(self.ingest_file(path, actor=actor))
            except AppError as exc:
                errors.append(f"{path.name}: {exc.message} {exc.details or ''}".strip())
                logger.error("ingest_failed file=%s error=%s", path, exc.message)
        if errors and not stored:
            raise AppError("Corpus ingest failed for every file", status_code=400, details=errors)
        if errors:
            logger.warning("ingest_partial_failures count=%s details=%s", len(errors), errors)
        return stored
