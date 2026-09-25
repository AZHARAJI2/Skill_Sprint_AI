"""Repository for Role Requirement Matrix rows."""

from __future__ import annotations

from sqlalchemy.orm import Session

from database.base import BaseRepository
from role_matrix.models import RequirementMatrixEntry


class RoleMatrixRepository(BaseRepository[RequirementMatrixEntry]):
    """Query helpers used by Phase 2 generation and Phase 3 validation."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, RequirementMatrixEntry)

    def get_by_requirement_id(self, requirement_id: str) -> RequirementMatrixEntry | None:
        """Fetch a single matrix row by requirement_id."""
        return (
            self.session.query(RequirementMatrixEntry)
            .filter(RequirementMatrixEntry.requirement_id == requirement_id)
            .one_or_none()
        )

    def get_by_role(self, role: str) -> list[RequirementMatrixEntry]:
        """Rows for a job role plus company-wide 'All Roles' rows."""
        return list(
            self.session.query(RequirementMatrixEntry)
            .filter(RequirementMatrixEntry.role.in_([role, "All Roles"]))
            .all()
        )

    def get_mandatory(self) -> list[RequirementMatrixEntry]:
        """All mandatory matrix rows."""
        return list(
            self.session.query(RequirementMatrixEntry).filter(RequirementMatrixEntry.mandatory.is_(True)).all()
        )

    def get_by_source_doc(self, source_document_id: str) -> list[RequirementMatrixEntry]:
        """Rows citing a given source document."""
        return list(
            self.session.query(RequirementMatrixEntry)
            .filter(RequirementMatrixEntry.source_document_id == source_document_id)
            .all()
        )

    def count(self) -> int:
        """Total stored matrix rows."""
        return int(self.session.query(RequirementMatrixEntry).count())

    def delete_all(self) -> None:
        """Remove all matrix rows (used when reloading the seed CSV)."""
        self.session.query(RequirementMatrixEntry).delete()
        self.session.flush()
