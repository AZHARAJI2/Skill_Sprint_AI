"""Audit trail repository."""

from __future__ import annotations

from sqlalchemy.orm import Session

from database.base import BaseRepository
from src.reviews.models import AuditEntry


class AuditRepository(BaseRepository[AuditEntry]):
    """Append-only writes for ingest, auth, matrix load, and later GenAI/validation events."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, AuditEntry)

    def record(
        self,
        actor: str,
        action: str,
        entity_type: str,
        entity_id: str | None,
        details: dict | None,
        log_level: str = "INFO",
    ) -> AuditEntry:
        """Insert one audit row."""
        entry = AuditEntry(
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
            log_level=log_level,
        )
        return self.add(entry)
