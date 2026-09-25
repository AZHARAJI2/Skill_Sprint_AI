"""Persist uploaded bytes to the configured upload directory."""

from __future__ import annotations

from pathlib import Path

from config.settings import settings


class DocumentUploader:
    """Writes validated files to disk under data/uploads/{document_id}/."""

    def save(self, document_id: str, original_name: str, raw_bytes: bytes) -> Path:
        """Save bytes and return the absolute path of the stored file."""
        settings.ensure_runtime_dirs()
        target_dir = settings.upload_dir / document_id
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = Path(original_name).name
        dest = target_dir / safe_name
        dest.write_bytes(raw_bytes)
        return dest
