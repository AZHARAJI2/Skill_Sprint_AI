"""Tests for document validation, parsing, chunking, and full corpus ingest."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.settings import settings
from document_processing.parser import DocumentParser
from document_processing.validator import DocumentFileValidator
from src.documents.metrics import CorpusMetricsService
from src.documents.repository import DocumentRevisionRepository
from src.documents.service import DocumentService
from src.errors import AppError


def test_reject_unsupported_and_empty_files(tmp_path: Path) -> None:
    """File-type and empty-document checks fail closed."""
    validator = DocumentFileValidator()
    exe = tmp_path / "malware.exe"
    exe.write_bytes(b"not-a-document")
    result = validator.validate(exe, exe.read_bytes())
    assert result.ok is False
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    result = validator.validate(empty, b"")
    assert result.ok is False
    assert any("Empty" in err for err in result.errors)


def test_parse_handbook_retains_metadata() -> None:
    """Parser keeps document_id, version, dates, and numbered sections."""
    path = settings.sample_documents_dir / "handbook" / "HANDBOOK-01_Employee-Handbook.docx"
    parsed = DocumentParser().parse(path, path.read_bytes())
    assert parsed.document_id == "HANDBOOK-01"
    assert parsed.version == "v2"
    assert parsed.effective_date is not None
    ids = {section.section_id for section in parsed.sections}
    assert "1.1" in ids
    assert any(section.is_mandatory for section in parsed.sections)
    assert any((section.flags or {}).get("adversarial") for section in parsed.sections)


def test_ingest_rejects_duplicate_hash(session) -> None:
    """Identical bytes cannot be stored twice."""
    path = settings.sample_documents_dir / "handbook" / "HANDBOOK-01_Employee-Handbook.docx"
    service = DocumentService(session)
    first = service.ingest_file(path)
    assert first.document_id == "HANDBOOK-01"
    with pytest.raises(AppError) as exc:
        service.ingest_file(path)
    assert exc.value.status_code in {400, 409}


def test_ingest_full_sample_corpus(session) -> None:
    """VG-1.1 / VG-1.3: all sample files go through upload→validate→parse→chunk→store."""
    stored = DocumentService(session).ingest_directory(settings.sample_documents_dir)
    metrics = CorpusMetricsService(session).compute()
    assert len(stored) == 38
    assert metrics["file_count"] == 38
    assert metrics["unique_document_ids"] >= 24
    assert metrics["mandatory_sections"] >= 102
    assert metrics["optional_sections"] >= 28
    assert metrics["role_specific_sections"] >= 65
    assert metrics["conflict_mentioned_sections"] >= 10
    assert metrics["adversarial_sections"] >= 11
    version_signal = metrics["version_change_sections"] + metrics["obsolete_revision_count"]
    assert version_signal >= 10


def test_pol02_version_control(session) -> None:
    """VG-1.4: POL-02 v2 is active; superseded v1 is recorded as obsolete for docx and pdf."""
    service = DocumentService(session)
    docx = settings.sample_documents_dir / "policies" / "POL-02_Leave-Policy.docx"
    pdf = settings.sample_documents_dir / "policies" / "POL-02_Leave-Policy.pdf"
    d1 = service.ingest_file(docx)
    d2 = service.ingest_file(pdf)
    assert d1.version == "v2"
    assert d2.version == "v2"
    assert d1.status == "active"
    assert d2.status == "active"
    revisions = DocumentRevisionRepository(session).list_by_document_id("POL-02")
    statuses = {rev.version: rev.status for rev in revisions}
    assert statuses.get("v2") == "active"
    assert statuses.get("v1") == "obsolete"
