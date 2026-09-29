"""Validated employee-file import for CSV, XLSX, and JSON uploads."""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy.orm import Session

from config.settings import settings
from src.employees.service import EmployeeService, RoleService
from src.errors import AppError


class EmployeeImportService:
    """Parse and validate employee profiles before creating them as one batch."""

    _ALLOWED_EXTENSIONS = frozenset({".csv", ".xlsx", ".json"})
    _REQUIRED_FIELDS = ("employee_code", "name", "department")
    _EXPERIENCE_LEVELS = {"beginner": "Beginner", "intermediate": "Intermediate", "advanced": "Advanced"}
    _TRAINING_STATUSES = {"not_started", "in_progress", "completed"}
    _FIELD_LIMITS = {
        "employee_code": 32,
        "name": 128,
        "department": 128,
        "location": 128,
        "reporting_manager": 128,
    }

    def __init__(self, session: Session) -> None:
        self.session = session
        self.employee_service = EmployeeService(session)
        self.role_service = RoleService(session)

    def import_file(self, filename: str, raw: bytes, actor: str) -> list:
        """Validate a supported file completely, then create every employee in it.

        The import is all-or-nothing: no profiles are created when any row has an
        error. This prevents a partially imported onboarding population.
        """
        extension = Path(filename).suffix.lower()
        if extension not in self._ALLOWED_EXTENSIONS:
            raise AppError("Employee imports support CSV, XLSX, or JSON files only.", status_code=400)
        if not raw:
            raise AppError("The employee import file is empty.", status_code=400)
        if len(raw) > settings.max_upload_bytes:
            raise AppError("The employee import file exceeds the 20 MB limit.", status_code=400)

        rows = self._parse_file(extension, raw)
        if not rows:
            raise AppError("The employee import file contains no employee rows.", status_code=400)

        roles = self.role_service.list_roles()
        roles_by_id = {role.id: role for role in roles}
        roles_by_title = {role.title.casefold(): role for role in roles}
        profiles, errors = self._validate_rows(rows, roles_by_id, roles_by_title)
        if errors:
            raise AppError(
                "Employee import validation failed. No employee profiles were created.",
                status_code=422,
                details={"rows": errors},
            )

        return [self.employee_service.create(actor=actor, **profile) for profile in profiles]

    def _parse_file(self, extension: str, raw: bytes) -> list[dict[str, Any]]:
        """Read supported tabular files into normalized row dictionaries."""
        try:
            if extension == ".csv":
                text = raw.decode("utf-8-sig")
                return self._rows_from_csv(text)
            if extension == ".json":
                return self._rows_from_json(raw)
            return self._rows_from_xlsx(raw)
        except (
            BadZipFile,
            InvalidFileException,
            OSError,
            UnicodeDecodeError,
            csv.Error,
            json.JSONDecodeError,
            ValueError,
        ) as exc:
            raise AppError("The employee import file could not be read.", status_code=400, details=str(exc)) from exc

    def _rows_from_csv(self, text: str) -> list[dict[str, Any]]:
        """Read a UTF-8 CSV file with a header row."""
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise AppError("CSV imports require a header row.", status_code=400)
        return [self._normalise_keys(row) for row in reader if any(self._value_present(value) for value in row.values())]

    def _rows_from_json(self, raw: bytes) -> list[dict[str, Any]]:
        """Read a JSON object/array/wrapper, including UTF-8 BOM and JSON Lines.

        HR exports commonly use UTF-8 with a BOM or newline-delimited JSON
        (one employee object per line). Both carry the same structured data as
        a standard employee array and are safe to normalize into the existing
        all-or-nothing validation flow.
        """
        text = raw.decode("utf-8-sig")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            rows = self._rows_from_json_lines(text)
            if rows is None:
                raise AppError(
                    "The JSON employee file is invalid. Upload one employee object, "
                    "an employee array, an object with an employees array, or JSON Lines "
                    "(one employee object per line).",
                    status_code=400,
                    details={"line": exc.lineno, "column": exc.colno, "reason": exc.msg},
                ) from exc
            return [self._normalise_keys(row) for row in rows]
        if isinstance(payload, dict):
            rows = payload["employees"] if "employees" in payload else [payload]
        else:
            rows = payload
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise AppError(
                "JSON imports must be one employee object, an array of employees, or an object with an employees array.",
                status_code=400,
            )
        return [self._normalise_keys(row) for row in rows]

    @staticmethod
    def _rows_from_json_lines(text: str) -> list[dict[str, Any]] | None:
        """Parse strict JSON Lines only; return None when the file is malformed."""
        lines = [(number, line.strip()) for number, line in enumerate(text.splitlines(), start=1) if line.strip()]
        if len(lines) < 2:
            return None
        rows: list[dict[str, Any]] = []
        for _number, line in lines:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                return None
            if not isinstance(row, dict):
                return None
            rows.append(row)
        return rows

    def _rows_from_xlsx(self, raw: bytes) -> list[dict[str, Any]]:
        """Read the first worksheet of a standard XLSX workbook."""
        workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True, keep_links=False)
        try:
            sheet = workbook.active
            values = sheet.iter_rows(values_only=True)
            headers = next(values, None)
            if not headers:
                raise AppError("XLSX imports require a header row in the first worksheet.", status_code=400)
            normalized_headers = [self._normalise_key(header) for header in headers]
            if not any(normalized_headers):
                raise AppError("XLSX imports require at least one named column.", status_code=400)
            rows = []
            for values_row in values:
                row = {
                    header: self._xlsx_value(value)
                    for header, value in zip(normalized_headers, values_row, strict=False)
                    if header
                }
                if any(self._value_present(value) for value in row.values()):
                    rows.append(row)
            return rows
        finally:
            workbook.close()

    def _validate_rows(self, rows, roles_by_id, roles_by_title) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Validate every row and resolve its supplied role ID or title."""
        profiles: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        seen_codes: set[str] = set()

        for number, row in enumerate(rows, start=2):
            profile, row_errors = self._validate_row(row, roles_by_id, roles_by_title, seen_codes)
            if row_errors:
                errors.append({"row": number, "employee_code": self._text(row.get("employee_code")), "errors": row_errors})
            else:
                profiles.append(profile)
        return profiles, errors

    def _validate_row(self, row, roles_by_id, roles_by_title, seen_codes) -> tuple[dict[str, Any], list[str]]:
        """Convert one supplied row to the safe employee-create payload."""
        errors: list[str] = []
        profile: dict[str, Any] = {}
        for field in self._REQUIRED_FIELDS:
            value = self._text(row.get(field))
            if not value:
                errors.append(f"{field} is required.")
            elif len(value) > self._FIELD_LIMITS[field]:
                errors.append(f"{field} exceeds {self._FIELD_LIMITS[field]} characters.")
            profile[field] = value

        code_key = profile["employee_code"].casefold()
        if code_key:
            if code_key in seen_codes:
                errors.append("employee_code is duplicated in this file.")
            elif self.employee_service.employees.get_by_code(profile["employee_code"]):
                errors.append("employee_code already exists.")
            seen_codes.add(code_key)

        role = self._resolve_role(row, roles_by_id, roles_by_title, errors)
        if role:
            profile["role_id"] = role.id

        experience = self._text(row.get("experience_level")) or "Beginner"
        normalized_experience = self._EXPERIENCE_LEVELS.get(experience.casefold())
        if normalized_experience is None:
            errors.append("experience_level must be Beginner, Intermediate, or Advanced.")
        else:
            profile["experience_level"] = normalized_experience

        profile["location"] = self._optional_text(row, "location", errors)
        profile["reporting_manager"] = self._optional_text(row, "reporting_manager", errors)
        profile["prior_experience"] = self._text(row.get("prior_experience")) or None
        profile["required_competencies"] = self._competencies(row.get("required_competencies"), errors)
        profile["joining_date"] = self._parse_date(row.get("joining_date"), errors)

        status = (self._text(row.get("training_status")) or "not_started").casefold()
        if status not in self._TRAINING_STATUSES:
            errors.append("training_status must be not_started, in_progress, or completed.")
        else:
            profile["training_status"] = status
        return profile, errors

    def _resolve_role(self, row, roles_by_id, roles_by_title, errors):
        """Resolve a role from role_id, role_title, or the shorter role alias."""
        supplied_id = self._text(row.get("role_id"))
        supplied_title = self._text(row.get("role_title")) or self._text(row.get("role"))
        if supplied_id:
            try:
                role = roles_by_id.get(int(supplied_id))
            except ValueError:
                role = None
            if role:
                return role
            errors.append("role_id does not match an existing job role.")
            return None
        if supplied_title:
            role = roles_by_title.get(supplied_title.casefold())
            if role:
                return role
            errors.append("role_title does not match an existing job role.")
            return None
        errors.append("role_id or role_title is required.")
        return None

    def _optional_text(self, row, field: str, errors: list[str]) -> str | None:
        """Return an optional short text field after enforcing its model limit."""
        value = self._text(row.get(field))
        if value and len(value) > self._FIELD_LIMITS[field]:
            errors.append(f"{field} exceeds {self._FIELD_LIMITS[field]} characters.")
        return value or None

    @staticmethod
    def _competencies(value: Any, errors: list[str]) -> list[str] | None:
        """Accept a JSON list or a semicolon-separated cell in CSV and XLSX."""
        if value is None or value == "":
            return None
        if isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
        elif isinstance(value, str):
            items = [item.strip() for item in value.split(";") if item.strip()]
        else:
            errors.append("required_competencies must be a list or semicolon-separated text.")
            return None
        if any(len(item) > 128 for item in items):
            errors.append("Each required competency must be 128 characters or fewer.")
        return items or None

    @staticmethod
    def _parse_date(value: Any, errors: list[str]) -> date | None:
        """Accept ISO dates only so imported start dates stay unambiguous."""
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value).strip())
        except ValueError:
            errors.append("joining_date must use YYYY-MM-DD.")
            return None

    @classmethod
    def _normalise_keys(cls, row: dict[Any, Any]) -> dict[str, Any]:
        """Normalize common CSV, JSON, and spreadsheet header spellings."""
        return {cls._normalise_key(key): value for key, value in row.items() if cls._normalise_key(key)}

    @staticmethod
    def _normalise_key(value: Any) -> str:
        """Map header spacing and casing to the API's snake_case field names."""
        return str(value or "").strip().casefold().replace(" ", "_").replace("-", "_")

    @staticmethod
    def _xlsx_value(value: Any) -> Any:
        """Keep native date values intact and trim Excel text cells."""
        return value

    @staticmethod
    def _text(value: Any) -> str:
        """Normalize user-provided scalar values to trimmed strings."""
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _value_present(value: Any) -> bool:
        """Tell whether a parsed cell has a meaningful value."""
        return value is not None and str(value).strip() != ""
