"""PlanGenerationService: Pipeline 1 orchestration using Phase 1 repositories only."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from config.logging_config import get_logger
from genai_pipeline.base_provider import BaseGenAIProvider
from genai_pipeline.gemini_provider import GeminiProvider
from genai_pipeline.plan_assembler import PlanAssembler
from genai_pipeline.plan_generator import PlanGenerator
from genai_pipeline.prompt_manager import PromptManager
from genai_pipeline.requirement_extractor import RequirementExtractor
from genai_pipeline.quiz_generator import DistractorValidator
from role_matrix.repository import RoleMatrixRepository
from schemas.plan_schema import GeneratedPlan
from src.documents.repository import ChunkRepository, DocumentRepository
from src.employees.service import EmployeeService
from src.errors import AppError
from src.plans.models import (
    AssessmentRecord,
    ChecklistItemRecord,
    GenerationMetadata,
    LearningModuleRecord,
    OnboardingPlan,
    PromptTemplate,
    QuizQuestionRecord,
    TaskRecord,
)
from src.plans.repository import (
    GenerationMetadataRepository,
    PlanRepository,
    PromptTemplateRepository,
)
from src.reviews.repository import AuditRepository

logger = get_logger("plan_generation")


class PlanGenerationService:
    """Build a personalized, source-grounded onboarding plan for one employee."""

    def __init__(self, session: Session, provider: BaseGenAIProvider | None = None) -> None:
        self.session = session
        self.employees = EmployeeService(session)
        self.matrix = RoleMatrixRepository(session)
        self.chunks = ChunkRepository(session)
        self.documents = DocumentRepository(session)
        self.plans = PlanRepository(session)
        self.templates = PromptTemplateRepository(session)
        self.metadata = GenerationMetadataRepository(session)
        self.audit = AuditRepository(session)
        self.provider = provider
        self.extractor = RequirementExtractor()
        self.assembler = PlanAssembler()
        self.prompt_manager = PromptManager()
        self.distractors = DistractorValidator()

    def generate_for_employee(self, employee_id: int, actor: str = "system") -> OnboardingPlan:
        """Run Pipeline 1 and persist the structured plan plus generation metadata."""
        provider = self.provider or GeminiProvider()
        generator = PlanGenerator(provider, self.prompt_manager)
        employee = self.employees.get(employee_id)
        role = employee.role
        if role is None:
            raise AppError("Employee has no job role assigned", status_code=400)
        entries = self.matrix.get_by_role(role.title)
        if not entries:
            raise AppError(f"No matrix rows for role {role.title}", status_code=400)

        classified = self.extractor.extract(entries, employee.experience_level, role.title)
        needed_docs = {item.source_document_id for item in classified}
        chunks = [chunk for chunk in self.chunks.list_all() if chunk.document_id in needed_docs]
        excerpts = self.assembler.excerpts_from_chunks(chunks)
        assembled = self.assembler.build(
            employee_code=employee.employee_code,
            role_title=role.title,
            experience_level=employee.experience_level,
            classified=classified,
            excerpts=excerpts,
            responsible_person=employee.reporting_manager or "Reporting manager",
        )
        assembled = assembled.model_copy(
            update={"quizzes": [self.distractors.validate(q, excerpts.get((q.source_document_id, q.source_section_id))) for q in assembled.quizzes]}
        )

        employee_json = json.dumps(
            {
                "employee_code": employee.employee_code,
                "name": employee.name,
                "role_title": role.title,
                "department": employee.department,
                "experience_level": employee.experience_level,
                "location": employee.location,
                "joining_date": employee.joining_date.isoformat() if employee.joining_date else None,
                "reporting_manager": employee.reporting_manager,
                "competencies": employee.required_competencies,
            }
        )
        requirements_json = json.dumps([item.model_dump(mode="json") for item in classified])
        source_chunks_block = self._fence_chunks(classified, excerpts)
        valid_sources = {(item.source_document_id, item.source_section_id) for item in classified} | set(excerpts.keys())
        mandatory_ids = {item.requirement_id for item in classified if item.mandatory}
        enrich = isinstance(provider, GeminiProvider)

        self._record_prompt_templates()
        plan, telemetry = generator.generate(
            assembled=assembled,
            employee_json=employee_json,
            requirements_json=requirements_json,
            source_chunks_block=source_chunks_block,
            valid_sources=valid_sources,
            mandatory_ids=mandatory_ids,
            excerpts=excerpts,
            enrich=enrich,
        )
        stored = self._persist(employee.id, role.id, plan, telemetry, actor)
        logger.info(
            "plan_generated employee=%s role=%s plan_id=%s model=%s recovered=%s",
            employee.employee_code,
            role.title,
            stored.id,
            telemetry.get("model_used"),
            telemetry.get("recovered_from_assembler"),
        )
        return stored

    def get_plan(self, plan_id: int) -> OnboardingPlan:
        """Fetch a stored plan or raise 404."""
        plan = self.plans.get(plan_id)
        if plan is None:
            raise AppError("Plan not found", status_code=404)
        return plan

    def list_for_employee(self, employee_id: int) -> list[OnboardingPlan]:
        """List generated plans for an employee."""
        self.employees.get(employee_id)
        return self.plans.list_by_employee(employee_id)

    def _fence_chunks(self, classified, excerpts) -> str:
        blocks: list[str] = []
        seen: set[tuple[str, str]] = set()
        for item in classified:
            key = (item.source_document_id, item.source_section_id)
            if key in seen:
                continue
            seen.add(key)
            excerpt = excerpts.get(key)
            text = (excerpt.text if excerpt else "")[:500]
            scan = self.assembler.injection_guard.scan(text, document_id=key[0], section_id=key[1])
            blocks.append(scan.fenced_text)
            if len(blocks) >= 40:
                break
        return "\n\n".join(blocks)

    def _record_prompt_templates(self) -> None:
        for name in ("onboarding_plan", "learning_module", "quiz_generation", "assessment", "scenario_task"):
            version = "v2" if name == "onboarding_plan" else "v1"
            template = self.prompt_manager.load(name, version)
            self.templates.upsert(template.name, template.version, template.system + "\n" + template.user, template.variables)


    def _persist(self, employee_id: int, role_id: int, plan: GeneratedPlan, telemetry: dict, actor: str) -> OnboardingPlan:
        versions = {doc.document_id: doc.version for doc in self.documents.list_active()}
        header = OnboardingPlan(
            employee_id=employee_id,
            role_id=role_id,
            prompt_version=telemetry.get("prompt_version"),
            model_used=telemetry.get("model_used"),
            source_doc_versions=versions,
            status="generated",
            verification_status=None,
            structured_json=plan.model_dump(mode="json"),
        )
        self.plans.add(header)
        for module in plan.modules:
            self.session.add(
                LearningModuleRecord(
                    plan_id=header.id,
                    title=module.title,
                    purpose=module.purpose,
                    payload=module.model_dump(mode="json"),
                    stage=module.stage,
                    difficulty=module.difficulty.value,
                    source_document_id=module.source_document_id,
                    source_section_id=module.source_section_id,
                )
            )
        for item in plan.checklists:
            self.session.add(
                ChecklistItemRecord(
                    plan_id=header.id,
                    payload=item.model_dump(mode="json"),
                    source_document_id=item.source_document_id,
                    source_section_id=item.source_section_id,
                )
            )
        for task in plan.tasks:
            self.session.add(
                TaskRecord(
                    plan_id=header.id,
                    payload=task.model_dump(mode="json"),
                    source_requirement_id=task.source_requirement_id,
                    due_stage=task.due_stage,
                )
            )
        for quiz in plan.quizzes:
            self.session.add(
                QuizQuestionRecord(
                    plan_id=header.id,
                    payload=quiz.model_dump(mode="json"),
                    source_document_id=quiz.source_document_id,
                    source_section_id=quiz.source_section_id,
                )
            )
        for assessment in plan.assessments:
            self.session.add(
                AssessmentRecord(
                    plan_id=header.id,
                    payload=assessment.model_dump(mode="json"),
                    assessment_type=assessment.assessment_type.value,
                )
            )
        template_row = (
            self.session.query(PromptTemplate)
            .filter(PromptTemplate.name == "onboarding_plan", PromptTemplate.version == "v1")
            .one_or_none()
        )
        self.metadata.add(
            GenerationMetadata(
                plan_id=header.id,
                prompt_template_id=template_row.id if template_row else None,
                model_name=telemetry.get("model_used"),
                api_version="google-genai",
                source_doc_versions=versions,
                retry_count=int(telemetry.get("retry_count") or 0),
                response_time_ms=float(telemetry.get("response_time_ms") or 0),
                log_payload={
                    "recovered_from_assembler": telemetry.get("recovered_from_assembler"),
                    "prompt_version": telemetry.get("prompt_version"),
                },
            )
        )
        self.audit.record(
            actor,
            "plan_generated",
            "onboarding_plan",
            str(header.id),
            {"role_id": role_id, "prompt_version": telemetry.get("prompt_version"), "model": telemetry.get("model_used")},
        )
        self.session.flush()
        return header
