"""Pipeline 1 orchestration: context → prompt → GenAI → Python validate/repair → generated plan."""

from __future__ import annotations

import json

from config.logging_config import get_logger
from config.settings import settings
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

logger = get_logger("plan_generator")


class PlanGenerator:
    """Run the GenAI plan call in phased stage groups and merge onto the Python-assembled backbone."""

    STAGE_GROUPS: list[tuple[str, set[str]]] = [
        ("Day 1 + Week 1", {"Day 1", "Week 1"}),
        ("Week 2 + First 30 Days", {"Week 2", "First 30 Days"}),
        ("First 60 Days + First 90 Days", {"First 60 Days", "First 90 Days"}),
    ]

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
        """Generate plan incrementally across stage groups. Failure after retries marks ungenerated items."""
        del requirements_json
        try:
            template = self.prompt_manager.load("onboarding_plan", "v2")
        except Exception:
            template = self.prompt_manager.load("onboarding_plan", "v1")

        telemetry = {
            "prompt_version": template.version_label,
            "model_used": None,
            "retry_count": 0,
            "response_time_ms": 0.0,
            "recovered_from_assembler": False,
            "stage_failures": [],
        }

        req_stage_map = {r.requirement_id: r.due_stage for r in assembled.classified_requirements}
        merged_groups: list[GeneratedPlan] = []
        failed_stage_groups: list[str] = []

        for group_name, stages in self.STAGE_GROUPS:
            stage_reqs = [r for r in assembled.classified_requirements if r.due_stage in stages]
            stage_modules = [m for m in assembled.modules if m.stage in stages]
            stage_checklists = [c for c in assembled.checklists if c.due_stage in stages]
            stage_tasks = [t for t in assembled.tasks if t.due_stage in stages]
            stage_quizzes = [q for q in assembled.quizzes if req_stage_map.get(q.requirement_id) in stages]
            stage_assessments = [a for a in assembled.assessments if a.stage in stages]
            stage_covered_ids = [r.requirement_id for r in stage_reqs]

            if not stage_reqs and not stage_modules and not stage_checklists and not stage_tasks:
                continue

            sub_stages = sorted(
                list(
                    {m.stage for m in stage_modules}
                    | {c.due_stage for c in stage_checklists}
                    | {t.due_stage for t in stage_tasks}
                )
            )

            sub_assembled = GeneratedPlan(
                schema_version=template.version_label,
                role_title=assembled.role_title,
                employee_code=assembled.employee_code,
                experience_level=assembled.experience_level,
                classified_requirements=stage_reqs,
                modules=stage_modules,
                checklists=stage_checklists,
                tasks=stage_tasks,
                quizzes=stage_quizzes,
                assessments=stage_assessments,
                stages_used=sub_stages,
                covered_requirement_ids=stage_covered_ids,
            )

            prompt_kwargs = {
                "employee_json": employee_json,
                "requirements_json": json.dumps([r.model_dump(mode="json") for r in stage_reqs]),
                "source_chunks_block": source_chunks_block,
                "role_title": assembled.role_title,
            }
            if "stage_group" in template.variables:
                prompt_kwargs["stage_group"] = group_name

            prompt = self.prompt_manager.render(template, **prompt_kwargs)

            try:
                cfg = GenerationConfig(
                    temperature=0.15,
                    thinking_budget=getattr(settings, "gemini_thinking_budget", 0),
                )
                response = RetryManager(self.provider).run(prompt, schema=GeneratedPlan, config=cfg)
                telemetry["model_used"] = response.model_name
                telemetry["retry_count"] += response.retry_count
                telemetry["response_time_ms"] += response.response_time_ms
                model_plan = GeneratedPlan.model_validate(response.parsed)
                group_merged = self._merge(sub_assembled, model_plan)
                merged_groups.append(group_merged)
            except AppError as exc:
                if exc.status_code in {401, 403, 503}:
                    raise
                telemetry["recovered_from_assembler"] = True
                telemetry["model_used"] = getattr(self.provider, "model", None) or getattr(
                    self.provider, "model_name", "unknown"
                )
                telemetry["stage_failures"].append({
                    "stage_group": group_name,
                    "error": str(exc),
                    "details": getattr(exc, "details", None),
                })
                logger.error("stage_group_generation_failed group=%s error=%s", group_name, exc)
                failed_stage_groups.append(group_name)
                failed_sub = self._mark_as_failed(sub_assembled)
                merged_groups.append(failed_sub)

        # Pure Python merge across all stage groups
        all_modules = []
        all_checklists = []
        all_tasks = []
        all_quizzes = []
        all_assessments = []
        all_covered_ids = []

        for g in merged_groups:
            all_modules.extend(g.modules)
            all_checklists.extend(g.checklists)
            all_tasks.extend(g.tasks)
            all_quizzes.extend(g.quizzes)
            all_assessments.extend(g.assessments)
            all_covered_ids.extend(g.covered_requirement_ids)

        if not all_modules:
            all_modules = assembled.modules
            all_checklists = assembled.checklists
            all_tasks = assembled.tasks
            all_quizzes = assembled.quizzes
            all_assessments = assembled.assessments
            all_covered_ids = assembled.covered_requirement_ids

        covered_unique = list(dict.fromkeys(all_covered_ids or assembled.covered_requirement_ids))
        stages_used = sorted(
            list(
                {m.stage for m in all_modules}
                | {c.due_stage for c in all_checklists}
                | {t.due_stage for t in all_tasks}
            )
        )

        overall_gen_status = "failed_after_retries" if failed_stage_groups else None

        plan = GeneratedPlan(
            schema_version=template.version_label,
            role_title=assembled.role_title,
            employee_code=assembled.employee_code,
            experience_level=assembled.experience_level,
            classified_requirements=assembled.classified_requirements,
            modules=all_modules,
            checklists=all_checklists,
            tasks=all_tasks,
            quizzes=all_quizzes,
            assessments=all_assessments,
            stages_used=stages_used or assembled.stages_used,
            covered_requirement_ids=covered_unique,
            generation_status=overall_gen_status,
        )

        if enrich and not failed_stage_groups and not telemetry["recovered_from_assembler"]:
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
    def _mark_as_failed(sub_assembled: GeneratedPlan) -> GeneratedPlan:
        """Mark items in a failed stage group with generation_status='failed_after_retries'
        and prefix titles with '[UNGENERATED - PENDING REVIEW]'."""
        prefix = "[UNGENERATED - PENDING REVIEW] "
        modules = [
            m.model_copy(
                update={
                    "title": f"{prefix}{m.title}" if not m.title.startswith(prefix) else m.title,
                    "generation_status": "failed_after_retries",
                }
            )
            for m in sub_assembled.modules
        ]
        checklists = [
            c.model_copy(
                update={
                    "activity": f"{prefix}{c.activity}" if not c.activity.startswith(prefix) else c.activity,
                    "generation_status": "failed_after_retries",
                }
            )
            for c in sub_assembled.checklists
        ]
        tasks = [
            t.model_copy(
                update={
                    "description": f"{prefix}{t.description}" if not t.description.startswith(prefix) else t.description,
                    "generation_status": "failed_after_retries",
                }
            )
            for t in sub_assembled.tasks
        ]
        quizzes = [
            q.model_copy(
                update={
                    "question_text": f"{prefix}{q.question_text}" if not q.question_text.startswith(prefix) else q.question_text,
                    "generation_status": "failed_after_retries",
                }
            )
            for q in sub_assembled.quizzes
        ]
        assessments = [
            a.model_copy(
                update={
                    "title": f"{prefix}{a.title}" if not a.title.startswith(prefix) else a.title,
                    "generation_status": "failed_after_retries",
                }
            )
            for a in sub_assembled.assessments
        ]
        return sub_assembled.model_copy(
            update={
                "modules": modules,
                "checklists": checklists,
                "tasks": tasks,
                "quizzes": quizzes,
                "assessments": assessments,
                "generation_status": "failed_after_retries",
            }
        )

    @staticmethod
    def _merge(assembled: GeneratedPlan, model_plan: GeneratedPlan) -> GeneratedPlan:
        """Keep assembler coverage and citations; take model wording when IDs match."""
        module_map = {item.module_id: item for item in model_plan.modules}
        quiz_map = {item.question_id: item for item in model_plan.quizzes}
        task_map = {item.task_id: item for item in model_plan.tasks}
        assessment_map = {item.assessment_id: item for item in model_plan.assessments}
        checklist_map = {item.item_id: item for item in model_plan.checklists}

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
            quizzes.append(
                other.model_copy(
                    update={
                        "source_document_id": item.source_document_id,
                        "source_section_id": item.source_section_id,
                        "requirement_id": item.requirement_id,
                        "distractor_validation_status": item.distractor_validation_status,
                    }
                )
                if other
                else item
            )

        tasks = []
        for item in assembled.tasks:
            other = task_map.get(item.task_id)
            tasks.append(
                other.model_copy(
                    update={
                        "source_document_id": item.source_document_id,
                        "source_section_id": item.source_section_id,
                        "source_requirement_id": item.source_requirement_id,
                        "due_stage": item.due_stage,
                        "role_title": item.role_title,
                    }
                )
                if other
                else item
            )

        assessments = []
        for item in assembled.assessments:
            other = assessment_map.get(item.assessment_id)
            assessments.append(
                other.model_copy(
                    update={
                        "source_document_id": item.source_document_id,
                        "source_section_id": item.source_section_id,
                        "requirement_ids": item.requirement_ids,
                        "stage": item.stage,
                    }
                )
                if other
                else item
            )

        checklists = []
        for item in assembled.checklists:
            other = checklist_map.get(item.item_id)
            checklists.append(
                other.model_copy(
                    update={
                        "source_document_id": item.source_document_id,
                        "source_section_id": item.source_section_id,
                        "requirement_id": item.requirement_id,
                        "due_stage": item.due_stage,
                        "responsible_person": item.responsible_person,
                    }
                )
                if other
                else item
            )

        return assembled.model_copy(
            update={
                "modules": modules,
                "checklists": checklists,
                "tasks": tasks,
                "quizzes": quizzes,
                "assessments": assessments,
            }
        )

