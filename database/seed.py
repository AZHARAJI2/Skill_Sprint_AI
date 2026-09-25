"""Seed job roles, demo users/employees, matrix, and the sample document corpus."""

from __future__ import annotations

from datetime import date

from config.logging_config import configure_logging, get_logger
from config.settings import settings
from database.base import SessionLocal
from database.migrations import create_schema
from role_matrix.load_matrix import load_matrix
from src.auth.service import AuthService
from src.documents.metrics import CorpusMetricsService
from src.documents.service import DocumentService
from src.employees.service import EmployeeService, RoleService
from src.reviews.models import AuditEntry  # noqa: F401 — ensure mapper is registered

NOVA_CART_ROLES = [
    ("Software Engineer", "Engineering"),
    ("DevOps/Infrastructure Engineer", "Engineering"),
    ("QA Engineer", "Engineering"),
    ("Customer Support Representative", "Customer Support"),
    ("Payments Operations Specialist", "Finance"),
    ("HR Generalist", "People & Culture"),
    ("Recruiter", "People & Culture"),
    ("Financial Analyst", "Finance"),
    ("Accounts Payable Clerk", "Finance"),
    ("Warehouse Operations Coordinator", "Warehouse"),
]


def seed_all(ingest_documents: bool = True) -> dict:
    """Create schema, seed roles/users, load the matrix, and ingest sample_documents."""
    configure_logging()
    logger = get_logger("seed")
    settings.ensure_runtime_dirs()
    create_schema()
    session = SessionLocal()
    summary: dict = {}
    try:
        role_service = RoleService(session)
        roles = {title: role_service.ensure_role(title, department) for title, department in NOVA_CART_ROLES}
        employee_service = EmployeeService(session)
        demo_employees = []
        for index, (title, department) in enumerate(NOVA_CART_ROLES, start=1):
            code = f"EMP-{index:03d}"
            existing = employee_service.employees.get_by_code(code)
            if existing:
                demo_employees.append(existing)
                continue
            demo_employees.append(
                employee_service.create(
                    employee_code=code,
                    name=f"Demo {title}",
                    role_id=roles[title].id,
                    department=department,
                    experience_level="Beginner",
                    location="Remote",
                    joining_date=date(2026, 9, 1),
                    reporting_manager="Manager Demo",
                    required_competencies=["Policy Awareness"],
                    prior_experience="None",
                    training_status="not_started",
                    actor="seed",
                )
            )
        auth = AuthService(session)
        auth.ensure_user("admin", "admin123", "Admin")
        auth.ensure_user("trainer", "trainer123", "Training Manager")
        auth.ensure_user("reviewer", "reviewer123", "Reviewer")
        auth.ensure_user("manager", "manager123", "Manager")
        auth.ensure_user("employee", "employee123", "Employee", employee_id=demo_employees[0].id)
        matrix = load_matrix(session, settings.matrix_csv_path, replace_existing=True)
        summary["matrix_loaded"] = matrix.loaded
        summary["matrix_rejected"] = matrix.rejected
        if ingest_documents:
            stored = DocumentService(session).ingest_directory(settings.sample_documents_dir, actor="seed")
            summary["files_ingested"] = len(stored)
            summary["metrics"] = CorpusMetricsService(session).compute()
        session.commit()
        logger.info("seed_complete summary=%s", summary)
        return summary
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    print(seed_all())
