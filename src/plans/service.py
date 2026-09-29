"""PlanGenerationService: Pipeline 1 orchestration using Phase 1 repositories only."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from config.logging_config import get_logger
from config.settings import settings
from genai_pipeline.base_provider import BaseGenAIProvider
from genai_pipeline.commandcode_provider import CommandCodeProvider
from genai_pipeline.deepseek_provider import DeepSeekProvider
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
        provider = self.provider or (
            GeminiProvider()
            if settings.genai_provider == "gemini"
            else DeepSeekProvider()
            if settings.genai_provider == "deepseek"
            else CommandCodeProvider()
        )
        generator = PlanGenerator(provider, self.prompt_manager)
        employee = self.employees.get(employee_id)
        role = employee.role
        if role is None:
            raise AppError("Employee has no job role assigned", status_code=400)
        entries = self.matrix.get_by_role(role.title)
        if not entries:
            raise AppError(f"No matrix rows for role {role.title}", status_code=400)

        generation_inputs = self._build_generation_inputs(employee, role, entries)
        # Enrichment remains opt-in in PlanGenerator. Any provider that
        # implements BaseGenAIProvider can use the same parallel enrichers.
        enrich = True

        self._record_prompt_templates()
        plan, telemetry = generator.generate(
            **generation_inputs,
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

    def _build_generation_inputs(self, employee, role, entries) -> dict:
        """Build bounded, source-grounded input for full or selective generation.

        ``entries`` may contain the complete role matrix or only the
        requirements affected by a policy update.  The same pipeline therefore
        supports real selective regeneration without hard-coded plan content.
        """
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
            update={
                "quizzes": [
                    self.distractors.validate(
                        quiz,
                        excerpts.get((quiz.source_document_id, quiz.source_section_id)),
                    )
                    for quiz in assembled.quizzes
                ]
            }
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
        source_chunks_by_reference = self._fenced_chunk_blocks(classified, excerpts)
        return {
            "assembled": assembled,
            "employee_json": employee_json,
            "requirements_json": json.dumps([item.model_dump(mode="json") for item in classified]),
            "source_chunks_block": "\n\n".join(source_chunks_by_reference.values()),
            "source_chunks_by_reference": source_chunks_by_reference,
            "valid_sources": {(item.source_document_id, item.source_section_id) for item in classified} | set(excerpts.keys()),
            "mandatory_ids": {item.requirement_id for item in classified if item.mandatory},
            "excerpts": excerpts,
        }

    def regenerate_affected_items(
        self,
        plan_id: int,
        document_id: str,
        *,
        actor: str = "system",
    ) -> OnboardingPlan:
        """Regenerate only content that cites one updated source document.

        Pipeline 1 receives only the changed document's role requirements.
        The resulting items replace only items that cite that document in the
        existing plan; every unrelated module, task, checklist, quiz and
        assessment remains unchanged.  Pipeline 2 must be run immediately
        afterwards by the caller before the refreshed plan is approved.
        """
        plan = self.get_plan(plan_id)
        employee = self.employees.get(plan.employee_id)
        role = employee.role
        if role is None:
            raise AppError("Employee has no job role assigned", status_code=400)
        affected_entries = [
            entry
            for entry in self.matrix.get_by_role(role.title)
            if entry.source_document_id == document_id
        ]
        if not affected_entries:
            raise AppError(
                f"No role requirements for {role.title} cite {document_id}",
                status_code=400,
            )

        provider = self.provider or (
            GeminiProvider()
            if settings.genai_provider == "gemini"
            else DeepSeekProvider()
            if settings.genai_provider == "deepseek"
            else CommandCodeProvider()
        )
        generated, telemetry = PlanGenerator(provider, self.prompt_manager).generate(
            **self._build_generation_inputs(employee, role, affected_entries),
            enrich=True,
        )
        if generated.generation_status == "failed_after_retries":
            raise AppError(
                "Selective regeneration did not produce a complete GenAI result; the original plan was preserved.",
                status_code=502,
                details={"plan_id": plan_id, "document_id": document_id},
            )

        self._replace_document_items(plan, generated, document_id)
        current_versions = {doc.document_id: doc.version for doc in self.documents.list_active()}
        plan.source_doc_versions = current_versions
        plan.prompt_version = telemetry.get("prompt_version")
        plan.model_used = telemetry.get("model_used")
        plan.status = "regenerated_pending_validation"
        plan.verification_status = "Manual Review Required"
        self._record_generation_metadata(plan, telemetry, current_versions)
        self.audit.record(
            actor,
            "selective_regeneration_completed",
            "onboarding_plan",
            str(plan.id),
            {
                "document_id": document_id,
                "preserved_unaffected_content": True,
                "model": telemetry.get("model_used"),
            },
        )
        self.session.flush()
        return plan

    def _replace_document_items(
        self,
        plan: OnboardingPlan,
        refreshed: GeneratedPlan,
        document_id: str,
    ) -> None:
        """Replace persisted artifacts only when they cite ``document_id``."""
        payload = dict(plan.structured_json or {})
        collection_specs = (
            ("modules", LearningModuleRecord),
            ("checklists", ChecklistItemRecord),
            ("tasks", TaskRecord),
            ("quizzes", QuizQuestionRecord),
            ("assessments", AssessmentRecord),
        )
        for collection, model in collection_specs:
            existing_items = payload.get(collection, [])
            preserved = [
                item
                for item in existing_items
                if item.get("source_document_id") != document_id
            ]
            replacements = [
                item.model_dump(mode="json")
                for item in getattr(refreshed, collection)
                if item.source_document_id == document_id
            ]
            payload[collection] = preserved + replacements

            records = self.session.query(model).filter(model.plan_id == plan.id).all()
            for record in records:
                source_document_id = getattr(record, "source_document_id", None)
                if source_document_id is None:
                    source_document_id = (record.payload or {}).get("source_document_id")
                if source_document_id == document_id:
                    self.session.delete(record)

        existing_covered = set(payload.get("covered_requirement_ids") or [])
        refreshed_ids = {row.requirement_id for row in refreshed.classified_requirements}
        payload["covered_requirement_ids"] = sorted(existing_covered | refreshed_ids)
        plan.structured_json = payload
        self._add_artifacts(plan.id, refreshed)

    def _add_artifacts(self, plan_id: int, plan: GeneratedPlan) -> None:
        """Persist child rows for a plan payload; used for a full or selective result."""
        for module in plan.modules:
            self.session.add(LearningModuleRecord(
                plan_id=plan_id, title=module.title, purpose=module.purpose,
                payload=module.model_dump(mode="json"), stage=module.stage,
                difficulty=module.difficulty.value, source_document_id=module.source_document_id,
                source_section_id=module.source_section_id,
            ))
        for item in plan.checklists:
            self.session.add(ChecklistItemRecord(
                plan_id=plan_id, payload=item.model_dump(mode="json"),
                source_document_id=item.source_document_id, source_section_id=item.source_section_id,
            ))
        for task in plan.tasks:
            self.session.add(TaskRecord(
                plan_id=plan_id, payload=task.model_dump(mode="json"),
                source_requirement_id=task.source_requirement_id, due_stage=task.due_stage,
            ))
        for quiz in plan.quizzes:
            self.session.add(QuizQuestionRecord(
                plan_id=plan_id, payload=quiz.model_dump(mode="json"),
                source_document_id=quiz.source_document_id, source_section_id=quiz.source_section_id,
            ))
        for assessment in plan.assessments:
            self.session.add(AssessmentRecord(
                plan_id=plan_id, payload=assessment.model_dump(mode="json"),
                assessment_type=assessment.assessment_type.value,
            ))

    def _record_generation_metadata(self, plan: OnboardingPlan, telemetry: dict, versions: dict) -> None:
        """Record every full or selective Pipeline 1 generation with its prompt metadata."""
        prompt_name, _, prompt_version = (telemetry.get("prompt_version") or "").rpartition("_")
        template_row = (
            self.session.query(PromptTemplate)
            .filter(PromptTemplate.name == prompt_name, PromptTemplate.version == prompt_version)
            .one_or_none()
        )
        self.metadata.add(GenerationMetadata(
            plan_id=plan.id,
            prompt_template_id=template_row.id if template_row else None,
            model_name=telemetry.get("model_used"),
            api_version=telemetry.get("api_version") or "unknown",
            source_doc_versions=versions,
            retry_count=int(telemetry.get("retry_count") or 0),
            response_time_ms=float(telemetry.get("response_time_ms") or 0),
            log_payload={
                "recovered_from_assembler": telemetry.get("recovered_from_assembler"),
                "prompt_version": telemetry.get("prompt_version"),
                "stage_failures": telemetry.get("stage_failures", []),
            },
        ))

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

    def _fenced_chunk_blocks(self, classified, excerpts) -> dict[tuple[str, str], str]:
        """Fence one short approved excerpt per source reference for token-efficient prompts."""
        blocks: dict[tuple[str, str], str] = {}
        seen: set[tuple[str, str]] = set()
        for item in classified:
            key = (item.source_document_id, item.source_section_id)
            if key in seen:
                continue
            seen.add(key)
            excerpt = excerpts.get(key)
            text = (excerpt.text if excerpt else "")[:settings.genai_excerpt_char_limit]
            scan = self.assembler.injection_guard.scan(text, document_id=key[0], section_id=key[1])
            blocks[key] = scan.fenced_text
            if len(blocks) >= settings.genai_max_prompt_excerpts:
                break
        return blocks

    def _record_prompt_templates(self) -> None:
        for name in ("onboarding_plan", "learning_module", "quiz_generation", "assessment", "scenario_task"):
            version = "v3" if name == "onboarding_plan" else "v1"
            template = self.prompt_manager.load(name, version)
            self.templates.upsert(template.name, template.version, template.system + "\n" + template.user, template.variables)


    def _persist(self, employee_id: int, role_id: int, plan: GeneratedPlan, telemetry: dict, actor: str) -> OnboardingPlan:
        versions = {doc.document_id: doc.version for doc in self.documents.list_active()}
        generation_failed = plan.generation_status == "failed_after_retries"
        header = OnboardingPlan(
            employee_id=employee_id,
            role_id=role_id,
            prompt_version=telemetry.get("prompt_version"),
            model_used=telemetry.get("model_used"),
            source_doc_versions=versions,
            # A source-grounded assembler fallback is useful for review, but it
            # must never be presented as an approved, actionable training plan.
            status="manual_review_required" if generation_failed else "generated",
            verification_status="Manual Review Required" if generation_failed else None,
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
        prompt_name, _, prompt_version = (telemetry.get("prompt_version") or "").rpartition("_")
        template_row = (
            self.session.query(PromptTemplate)
            .filter(PromptTemplate.name == prompt_name, PromptTemplate.version == prompt_version)
            .one_or_none()
        )
        self.metadata.add(
            GenerationMetadata(
                plan_id=header.id,
                prompt_template_id=template_row.id if template_row else None,
                model_name=telemetry.get("model_used"),
                api_version=telemetry.get("api_version") or "unknown",
                source_doc_versions=versions,
                retry_count=int(telemetry.get("retry_count") or 0),
                response_time_ms=float(telemetry.get("response_time_ms") or 0),
                log_payload={
                    "recovered_from_assembler": telemetry.get("recovered_from_assembler"),
                    "prompt_version": telemetry.get("prompt_version"),
                    "stage_failures": telemetry.get("stage_failures", []),
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
