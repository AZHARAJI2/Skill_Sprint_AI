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
from src.plans.service import PlanGenerationService
from src.plans.validation_service import PlanValidationService
from src.plans.models import OnboardingPlan
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


def seed_all(ingest_documents: bool = True, seed_demo_plans: bool = True) -> dict:
    """Create the reproducible evaluator dataset, including ten transparent demo plans.

    Demo plans are calculated from the committed document corpus and role
    matrix at seed time.  They are explicitly marked as source-grounded draft
    data, never presented as a live GenAI result or an approved training plan.
    This keeps a public GitHub clone evaluable without committing a mutable
    database file or fabricated GenAI output.
    """
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
        account_rows = []
        for employee in demo_employees:
            account, initial_password = auth.provision_employee_account(employee, actor="seed")
            account_rows.append(
                {
                    "employee_code": employee.employee_code,
                    "username": account.username,
                    "password_issued": bool(initial_password),
                }
            )
        summary["employee_accounts"] = account_rows
        matrix = load_matrix(session, settings.matrix_csv_path, replace_existing=True)
        summary["matrix_loaded"] = matrix.loaded
        summary["matrix_rejected"] = matrix.rejected
        if ingest_documents:
            stored = DocumentService(session).ingest_directory(settings.sample_documents_dir, actor="seed")
            summary["files_ingested"] = len(stored)
            summary["metrics"] = CorpusMetricsService(session).compute()
        if seed_demo_plans:
            summary["demo_plans"] = _seed_demo_plans(session, demo_employees)
        session.commit()
        logger.info("seed_complete summary=%s", summary)
        return summary
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _seed_demo_plans(session, employees) -> dict:
    """Create one reproducible, source-grounded draft plan for every demo role.

    The ten plans are derived from the same live matrix and parsed sources used
    by production. They are intentionally review-only until a real GenAI run
    and the independent Python validation complete; no plan text, score or API
    response is hard-coded in the repository.
    """
    generation = PlanGenerationService(session)
    validation = PlanValidationService(session)
    created: list[int] = []
    existing_employee_ids = {
        row[0]
        for row in session.query(OnboardingPlan.employee_id)
        .filter(OnboardingPlan.model_used == "seed-source-grounded-draft")
        .all()
    }
    for employee in employees:
        if employee.id in existing_employee_ids:
            continue
        role = employee.role
        if role is None:
            continue
        inputs = generation._build_generation_inputs(
            employee,
            role,
            generation.matrix.get_by_role(role.title),
        )
        draft = inputs["assembled"].model_copy(update={"generation_status": "seed_source_grounded_draft"})
        generation._record_prompt_templates()
        plan = generation._persist(
            employee.id,
            role.id,
            draft,
            {
                "prompt_version": "onboarding_plan_v3",
                "model_used": "seed-source-grounded-draft",
                "api_version": "not-a-live-genai-response",
                "retry_count": 0,
                "response_time_ms": 0.0,
                "recovered_from_assembler": False,
                "stage_failures": [],
            },
            actor="seed",
        )
        validation.validate(plan.id, actor="seed")
        # Never let a deterministic demonstration draft become an approved
        # GenAI plan merely because its matrix coverage happens to be complete.
        plan.status = "manual_review_required"
        plan.verification_status = "Manual Review Required — demo source-grounded draft"
        created.append(plan.id)
    return {"created": len(created), "plan_ids": created, "source": "matrix-and-documents"}


if __name__ == "__main__":
    print(seed_all())
