"""Search service — Phase 4, Task 61.

Cross-entity search and filtering across:
  - Employees (name, code, department, role, status)
  - Documents (title, document_id, category, department)
  - Learning Modules (title, purpose, stage)
  - Onboarding Plans (employee, status, verification_status)
  - Requirement Matrix Entries (requirement_id, role, text)

All searches are pure SQL LIKE queries — no GenAI, no embeddings.
"""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from role_matrix.models import RequirementMatrixEntry
from src.documents.models import Document
from src.employees.models import Employee, EmployeeRole
from src.plans.models import LearningModuleRecord, OnboardingPlan


class SearchService:
    """Cross-entity search and filtering (Task 61)."""

    def __init__(self, session: Session) -> None:
        """Inject the shared database session."""
        self._session = session

    def search(
        self,
        query: str,
        entity: str = "",
        department: str = "",
        limit: int = 50,
    ) -> dict[str, list[dict]]:
        """Run a cross-entity search and return grouped results.

        Args:
            query: Search term.  Applied as a case-insensitive LIKE pattern.
            entity: Optional filter to a single entity type
                    ('employee', 'document', 'module', 'plan', 'requirement').
            department: Optional department filter (applies to employees and docs).
            limit: Maximum rows per entity type.

        Returns:
            Dict with keys: employees, documents, modules, plans, requirements.
            Each value is a list of dicts serialisable to JSON.
        """
        text = query.strip() if query else ""
        if not text and not entity and not department:
            return {"employees": [], "documents": [], "modules": [], "plans": [], "requirements": []}

        # Filter-only search (no text): match everything, then narrow by
        # entity/department so the dropdowns work standalone.
        q = f"%{text}%" if text else "%"
        results: dict[str, list[dict]] = {
            "employees": [], "documents": [], "modules": [], "plans": [], "requirements": [],
        }

        if not entity or entity == "employee":
            results["employees"] = self._search_employees(q, department, limit)
        if not entity or entity == "document":
            results["documents"] = self._search_documents(q, department, limit)
        if not entity or entity == "module":
            results["modules"] = self._search_modules(q, limit)
        if not entity or entity == "plan":
            results["plans"] = self._search_plans(q, limit)
        if not entity or entity == "requirement":
            results["requirements"] = self._search_requirements(q, limit)

        return results

    def available_departments(self) -> list[str]:
        """Return all distinct department names for the filter dropdown."""
        rows = (
            self._session.query(Employee.department)
            .distinct()
            .order_by(Employee.department)
            .all()
        )
        return [r[0] for r in rows if r[0]]

    # ------------------------------------------------------------------
    # Per-entity searches
    # ------------------------------------------------------------------

    def _search_employees(self, q: str, department: str, limit: int) -> list[dict]:
        """Search employees by name, code, department, or training status."""
        stmt = (
            self._session.query(Employee, EmployeeRole)
            .join(EmployeeRole, Employee.role_id == EmployeeRole.id, isouter=True)
            .filter(
                or_(
                    Employee.name.ilike(q),
                    Employee.employee_code.ilike(q),
                    Employee.department.ilike(q),
                    Employee.training_status.ilike(q),
                )
            )
        )
        if department:
            stmt = stmt.filter(Employee.department == department)
        rows = stmt.limit(limit).all()
        return [
            {
                "employee_code": emp.employee_code,
                "name": emp.name,
                "department": emp.department,
                "training_status": emp.training_status,
                "role_title": role.title if role else None,
                "experience_level": emp.experience_level,
            }
            for emp, role in rows
        ]

    def _search_documents(self, q: str, department: str, limit: int) -> list[dict]:
        """Search documents by title, document_id, category, or department."""
        stmt = self._session.query(Document).filter(
            or_(
                Document.title.ilike(q),
                Document.document_id.ilike(q),
                Document.category.ilike(q),
                Document.department.ilike(q),
            )
        )
        if department:
            stmt = stmt.filter(Document.department == department)
        rows = stmt.limit(limit).all()
        return [
            {
                "document_id": doc.document_id,
                "title": doc.title,
                "category": doc.category,
                "department": doc.department,
                "version": doc.version,
                "status": doc.status,
            }
            for doc in rows
        ]

    def _search_modules(self, q: str, limit: int) -> list[dict]:
        """Search learning modules by title or purpose."""
        rows = (
            self._session.query(LearningModuleRecord)
            .filter(
                or_(
                    LearningModuleRecord.title.ilike(q),
                    LearningModuleRecord.purpose.ilike(q),
                )
            )
            .limit(limit)
            .all()
        )
        return [
            {
                "plan_id": m.plan_id,
                "title": m.title,
                "purpose": m.purpose,
                "stage": m.stage,
                "difficulty": m.difficulty,
                "source_document_id": m.source_document_id,
                "source_section_id": m.source_section_id,
            }
            for m in rows
        ]

    def _search_plans(self, q: str, limit: int) -> list[dict]:
        """Search plans by status or verification_status (numeric plan IDs are matched by cast)."""
        rows = (
            self._session.query(OnboardingPlan)
            .filter(
                or_(
                    OnboardingPlan.status.ilike(q),
                    OnboardingPlan.verification_status.ilike(q),
                    OnboardingPlan.model_used.ilike(q),
                )
            )
            .limit(limit)
            .all()
        )
        return [
            {
                "id": p.id,
                "employee_id": p.employee_id,
                "role_id": p.role_id,
                "status": p.status,
                "verification_status": p.verification_status,
                "model_used": p.model_used,
                "prompt_version": p.prompt_version,
            }
            for p in rows
        ]

    def _search_requirements(self, q: str, limit: int) -> list[dict]:
        """Search matrix requirement entries by ID, role, or text."""
        rows = (
            self._session.query(RequirementMatrixEntry)
            .filter(
                or_(
                    RequirementMatrixEntry.requirement_id.ilike(q),
                    RequirementMatrixEntry.role.ilike(q),
                    RequirementMatrixEntry.requirement_text.ilike(q),
                    RequirementMatrixEntry.competency.ilike(q),
                )
            )
            .limit(limit)
            .all()
        )
        return [
            {
                "requirement_id": r.requirement_id,
                "role": r.role,
                "department": r.department,
                "requirement_text": r.requirement_text,
                "mandatory": r.mandatory,
                "priority": r.priority,
                "due_stage": r.due_stage,
                "source_document_id": r.source_document_id,
                "competency": r.competency,
            }
            for r in rows
        ]
