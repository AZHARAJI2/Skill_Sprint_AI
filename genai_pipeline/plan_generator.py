"""Pipeline 1 orchestration: context → prompt → GenAI → Python validate/repair → generated plan."""

from __future__ import annotations

from genai_pipeline.assessment_generator import AssessmentGenerator
from genai_pipeline.base_provider import BaseGenAIProvider, GenerationConfig
from genai_pipeline.module_generator import ModuleGenerator
from genai_pipeline.prompt_manager import PromptManager
from genai_pipeline.quiz_generator import QuizGenerator
from genai_pipeline.retry_manager import RetryManager
from genai_pipeline.scenario_generator import ScenarioTaskGenerator
from genai_pipeline.schema_validator import OutputSchemaValidator
from genai_pipeline.sequence import PrerequisiteEnforcer
from schemas.plan_schema import GeneratedPlan
from src.errors import AppError


class PlanGenerator:
    """Run the GenAI plan call and merge it onto the Python-assembled backbone."""

    def __init__(self, provider: BaseGenAIProvider, prompt_manager: PromptManager | None = None) -> None:
        self.provider = provider
        self.prompt_manager = prompt_manager or PromptManager()
        self.modules = ModuleGenerator(provider, self.prompt_manager)
        self.quizzes = QuizGenerator(provider, self.prompt_manager)
        self.assessments = AssessmentGenerator(provider, self.prompt_manager)
        self.scenarios = ScenarioTaskGenerator(provider, self.prompt_manager)
        self.sequence = PrerequisiteEnforcer()
        self.schema = OutputSchemaValidator()

    def generate(
        self,
        *,
        assembled: GeneratedPlan,
        employee_json: str,
        requirements_json: str,
        source_chunks_block: str,
        valid_sources: set[tuple[str, str]],
        mandatory_ids: set[str],
        excerpts: dict | None = None,
        enrich: bool = True,
    ) -> tuple[GeneratedPlan, dict]:
        """Return (plan, telemetry). Recovery after retry cap keeps the assembler plan."""
        template = self.prompt_manager.load("onboarding_plan", "v1")
        prompt = self.prompt_manager.render(
            template,
            employee_json=employee_json,
            requirements_json=requirements_json,
            source_chunks_block=source_chunks_block,
            role_title=assembled.role_title,
        )
        telemetry = {
            "prompt_version": template.version_label,
            "model_used": None,
            "retry_count": 0,
            "response_time_ms": 0.0,
            "recovered_from_assembler": False,
        }
        try:
            response = RetryManager(self.provider).run(
                prompt, schema=GeneratedPlan, config=GenerationConfig(temperature=0.15)
            )
            telemetry["model_used"] = response.model_name
            telemetry["retry_count"] = response.retry_count
            telemetry["response_time_ms"] = response.response_time_ms
            model_plan = GeneratedPlan.model_validate(response.parsed)
            plan = self._merge(assembled, model_plan)
        except AppError as exc:
            if exc.status_code in {401, 403, 503}:
                raise
            telemetry["recovered_from_assembler"] = True
            telemetry["model_used"] = getattr(self.provider, "model", None) or getattr(
                self.provider, "model_name", "unknown"
            )
            plan = assembled

        if enrich and not telemetry["recovered_from_assembler"]:
            plan = plan.model_copy(
                update={
                    "modules": self.modules.enrich(plan, source_chunks_block),
                    "quizzes": self.quizzes.enrich(plan, source_chunks_block, excerpts or {}),
                    "assessments": self.assessments.enrich(plan, source_chunks_block),
                    "tasks": self.scenarios.enrich(plan, source_chunks_block),
                }
            )
        plan = self.sequence.enforce(plan)
        plan = self.schema.validate(
            plan.model_dump(mode="json"),
            expected_role=assembled.role_title,
            valid_sources=valid_sources,
            mandatory_ids=mandatory_ids,
        )
        return plan, telemetry

    @staticmethod
    def _merge(assembled: GeneratedPlan, model_plan: GeneratedPlan) -> GeneratedPlan:
        """Keep assembler coverage and citations; take model wording when IDs match."""
        module_map = {item.module_id: item for item in model_plan.modules}
        quiz_map = {item.question_id: item for item in model_plan.quizzes}
        task_map = {item.task_id: item for item in model_plan.tasks}
        modules = []
        for item in assembled.modules:
            other = module_map.get(item.module_id)
            if other:
                modules.append(
                    other.model_copy(
                        update={
                            "source_document_id": item.source_document_id,
                            "source_section_id": item.source_section_id,
                            "requirement_ids": item.requirement_ids,
                            "stage": item.stage,
                        }
                    )
                )
            else:
                modules.append(item)
        quizzes = []
        for item in assembled.quizzes:
            other = quiz_map.get(item.question_id)
            quizzes.append(other.model_copy(update={
                "source_document_id": item.source_document_id,
                "source_section_id": item.source_section_id,
                "requirement_id": item.requirement_id,
                "distractor_validation_status": item.distractor_validation_status,
            }) if other else item)
        tasks = []
        for item in assembled.tasks:
            other = task_map.get(item.task_id)
            tasks.append(other.model_copy(update={
                "source_document_id": item.source_document_id,
                "source_section_id": item.source_section_id,
                "source_requirement_id": item.source_requirement_id,
                "due_stage": item.due_stage,
                "role_title": item.role_title,
            }) if other else item)
        return assembled.model_copy(update={"modules": modules, "quizzes": quizzes, "tasks": tasks})
