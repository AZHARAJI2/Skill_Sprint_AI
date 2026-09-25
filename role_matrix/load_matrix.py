"""Load, validate, and persist the human-reviewed Role Requirement Matrix CSV."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from config.logging_config import get_logger
from role_matrix.models import RequirementMatrixEntry
from role_matrix.repository import RoleMatrixRepository
from src.errors import AppError
from src.reviews.repository import AuditRepository

logger = get_logger("load_matrix")

REQUIRED_COLUMNS = (
    "requirement_id",
    "role",
    "department",
    "requirement_text",
    "mandatory",
    "priority",
    "due_stage",
    "source_document_id",
    "source_section_id",
    "competency",
    "assessment_requirement",
)
REQUIREMENT_ID_RE = re.compile(r"^R\d{3,}$")
DOCUMENT_ID_RE = re.compile(r"^[A-Z]+-\d+$")
SECTION_ID_RE = re.compile(r"^\d+\.\d+$")


@dataclass
class MatrixLoadResult:
    """Summary of a CSV load attempt."""

    loaded: int
    rejected: list[str] = field(default_factory=list)


def _parse_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value).strip().upper()
    if text in {"TRUE", "1", "YES", "Y"}:
        return True
    if text in {"FALSE", "0", "NO", "N"}:
        return False
    return None


class MatrixLoader:
    """Reads the approved seed CSV, rejects malformed rows, and populates role_requirements."""

    def load(self, session: Session, csv_path: Path, replace_existing: bool = True) -> MatrixLoadResult:
        """Validate every row then insert. Does not author requirement content."""
        if not csv_path.exists():
            raise AppError(f"Matrix CSV not found: {csv_path}", status_code=404)
        frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        missing_cols = [col for col in REQUIRED_COLUMNS if col not in frame.columns]
        if missing_cols:
            raise AppError("Matrix CSV missing required columns", status_code=400, details=missing_cols)

        rejected: list[str] = []
        seen_ids: set[str] = set()
        entries: list[RequirementMatrixEntry] = []
        for index, row in frame.iterrows():
            row_no = int(index) + 2
            requirement_id = str(row["requirement_id"]).strip()
            errors: list[str] = []
            if not REQUIREMENT_ID_RE.match(requirement_id):
                errors.append(f"malformed requirement_id '{requirement_id}'")
            if requirement_id in seen_ids:
                errors.append(f"duplicate requirement_id '{requirement_id}'")
            for col in REQUIRED_COLUMNS:
                if str(row[col]).strip() == "":
                    errors.append(f"missing {col}")
            mandatory = _parse_bool(row["mandatory"])
            if mandatory is None:
                errors.append(f"invalid mandatory value '{row['mandatory']}'")
            source_document_id = str(row["source_document_id"]).strip()
            source_section_id = str(row["source_section_id"]).strip()
            if source_document_id and not DOCUMENT_ID_RE.match(source_document_id):
                errors.append(f"malformed source_document_id '{source_document_id}'")
            if source_section_id and not SECTION_ID_RE.match(source_section_id):
                errors.append(f"malformed source_section_id '{source_section_id}'")
            if errors:
                rejected.append(f"row {row_no}: {'; '.join(errors)}")
                continue
            seen_ids.add(requirement_id)
            entries.append(
                RequirementMatrixEntry(
                    requirement_id=requirement_id,
                    role=str(row["role"]).strip(),
                    department=str(row["department"]).strip(),
                    requirement_text=str(row["requirement_text"]).strip(),
                    mandatory=bool(mandatory),
                    priority=str(row["priority"]).strip(),
                    due_stage=str(row["due_stage"]).strip(),
                    source_document_id=source_document_id,
                    source_section_id=source_section_id,
                    competency=str(row["competency"]).strip(),
                    assessment_requirement=str(row["assessment_requirement"]).strip(),
                )
            )

        if rejected:
            logger.warning("matrix_rows_rejected count=%s details=%s", len(rejected), rejected)
        if not entries:
            raise AppError("No valid matrix rows to load", status_code=400, details=rejected)

        repo = RoleMatrixRepository(session)
        if replace_existing:
            repo.delete_all()
        for entry in entries:
            repo.add(entry)

        AuditRepository(session).record(
            actor="system",
            action="matrix_loaded",
            entity_type="role_requirements",
            entity_id=str(csv_path),
            details={"loaded": len(entries), "rejected": rejected},
        )
        logger.info("matrix_loaded count=%s rejected=%s path=%s", len(entries), len(rejected), csv_path)
        return MatrixLoadResult(loaded=len(entries), rejected=rejected)


def load_matrix(session: Session, csv_path: Path, replace_existing: bool = True) -> MatrixLoadResult:
    """Module-level entry point used by seed scripts and API routes."""
    return MatrixLoader().load(session, csv_path, replace_existing=replace_existing)
