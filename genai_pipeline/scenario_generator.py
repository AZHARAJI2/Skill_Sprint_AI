"""Scenario-task generator: GenAI wording on top of assembler-cited process tasks."""

from __future__ import annotations

from pydantic import BaseModel, Field

from genai_pipeline.base_provider import BaseGenAIProvider, GenerationConfig
from genai_pipeline.prompt_manager import PromptManager
from genai_pipeline.retry_manager import RetryManager
from schemas.plan_schema import GeneratedPlan, TaskItem


class ScenarioTaskBatch(BaseModel):
    """Schema for a dedicated scenario-task LLM call."""

    tasks: list[TaskItem] = Field(min_length=1)


class ScenarioTaskGenerator:
    """Refresh scenario task wording while preserving citations and due stages."""

    def __init__(self, provider: BaseGenAIProvider, prompt_manager: PromptManager | None = None) -> None:
        self.provider = provider
        self.prompt_manager = prompt_manager or PromptManager()

    def enrich(self, plan: GeneratedPlan, source_chunks_block: str) -> list[TaskItem]:
        """Merge model-written scenario descriptions onto assembler tasks when IDs match."""
        template = self.prompt_manager.load("scenario_task", "v1")
        prompt = self.prompt_manager.render(
            template,
            requirements_json=plan.model_dump_json(),
            source_chunks_block=source_chunks_block,
            role_title=plan.role_title,
        )
        try:
            response = RetryManager(self.provider).run(
                prompt, schema=ScenarioTaskBatch, config=GenerationConfig(temperature=0.2)
            )
            batch = ScenarioTaskBatch.model_validate(response.parsed)
            by_id = {item.task_id: item for item in plan.tasks}
            merged: list[TaskItem] = []
            for item in batch.tasks:
                original = by_id.get(item.task_id)
                if original is None:
                    continue
                merged.append(
                    item.model_copy(
                        update={
                            "source_document_id": original.source_document_id,
                            "source_section_id": original.source_section_id,
                            "source_requirement_id": original.source_requirement_id,
                            "due_stage": original.due_stage,
                            "role_title": original.role_title,
                            "is_scenario": original.is_scenario,
                            "grounding_status": original.grounding_status,
                        }
                    )
                )
            if not merged:
                return plan.tasks
            kept_ids = {item.task_id for item in merged}
            remainder = [item for item in plan.tasks if item.task_id not in kept_ids]
            return merged + remainder
        except Exception:
            return plan.tasks
