"""File-level validation before a document is parsed or stored."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from config.logging_config import get_logger
from config.settings import settings
from src.errors import AppError

logger = get_logger("document_validator")

ALLOWED_MIME_HINTS = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
}


@dataclass
class FileValidationResult:
    """Outcome of document-file validation (type, size, emptiness, hash)."""

    ok: bool
    suffix: str
    size_bytes: int
    file_hash: str
    errors: list[str] = field(default_factory=list)


class DocumentFileValidator:
    """Validates file type, size, emptiness, and duplicate hash against existing records."""

    def __init__(self, existing_hashes: set[str] | None = None) -> None:
        self.existing_hashes = existing_hashes or set()

    def validate(self, path: Path, raw_bytes: bytes) -> FileValidationResult:
        """Run the required file checks and log the decision."""
        suffix = path.suffix.lower()
        errors: list[str] = []
        if suffix not in settings.allowed_extensions:
            errors.append(f"Unsupported file type '{suffix}'. Allowed: {sorted(settings.allowed_extensions)}")
        size = len(raw_bytes)
        if size > settings.max_upload_bytes:
            errors.append(f"File exceeds max size {settings.max_upload_bytes} bytes")
        if size == 0:
            errors.append("Empty document (0 bytes)")
        import hashlib

        file_hash = hashlib.sha256(raw_bytes).hexdigest()
        if file_hash in self.existing_hashes:
            errors.append("Duplicate document (identical file hash already stored)")
        result = FileValidationResult(
            ok=not errors,
            suffix=suffix,
            size_bytes=size,
            file_hash=file_hash,
            errors=errors,
        )
        if result.ok:
            logger.info("document_validation_passed file=%s hash=%s size=%s", path.name, file_hash, size)
        else:
            logger.warning("document_validation_failed file=%s errors=%s", path.name, errors)
        return result

    def require_ok(self, path: Path, raw_bytes: bytes) -> FileValidationResult:
        """Validate and raise AppError on failure so callers never parse invalid files."""
        result = self.validate(path, raw_bytes)
        if not result.ok:
            raise AppError("Document validation failed", status_code=400, details=result.errors)
        return result
