"""Learning-module generator: prefers GenAI JSON, falls back to assembler modules after retry cap."""

from __future__ import annotations

from pydantic import BaseModel, Field

from genai_pipeline.base_provider import BaseGenAIProvider, GenerationConfig
from genai_pipeline.prompt_manager import PromptManager
from genai_pipeline.retry_manager import RetryManager
from schemas.module_schema import LearningModule
from schemas.plan_schema import GeneratedPlan


class ModuleBatch(BaseModel):
    """Schema for a dedicated module-generation LLM call."""

    modules: list[LearningModule] = Field(min_length=1)


class ModuleGenerator:
    """Generate or refresh learning modules while preserving source citations."""

    def __init__(self, provider: BaseGenAIProvider, prompt_manager: PromptManager | None = None) -> None:
        self.provider = provider
        self.prompt_manager = prompt_manager or PromptManager()

    def enrich(self, plan: GeneratedPlan, source_chunks_block: str) -> list[LearningModule]:
        """Ask the model to improve module wording; keep assembler modules if the call is invalid."""
        template = self.prompt_manager.load("learning_module", "v1")
        prompt = self.prompt_manager.render(
            template,
            requirements_json=plan.model_dump_json(),
            source_chunks_block=source_chunks_block,
            role_title=plan.role_title,
            experience_level=plan.experience_level,
        )
        try:
            response = RetryManager(self.provider).run(prompt, schema=ModuleBatch, config=GenerationConfig(temperature=0.2))
            batch = ModuleBatch.model_validate(response.parsed)
            batch_map = {module.module_id: module for module in batch.modules}
            merged: list[LearningModule] = []
            for original in plan.modules:
                enriched = batch_map.get(original.module_id)
                if enriched is not None:
                    merged.append(
                        enriched.model_copy(
                            update={
                                "source_document_id": original.source_document_id,
                                "source_section_id": original.source_section_id,
                                "requirement_ids": original.requirement_ids,
                                "stage": original.stage,
                                "grounding_status": original.grounding_status,
                            }
                        )
                    )
                else:
                    merged.append(original)
            return merged
        except Exception:
            return plan.modules
