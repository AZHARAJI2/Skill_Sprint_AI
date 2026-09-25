"""Assessment and rubric generation with Python-enforced structure."""

from __future__ import annotations

from pydantic import BaseModel, Field

from genai_pipeline.base_provider import BaseGenAIProvider, GenerationConfig
from genai_pipeline.prompt_manager import PromptManager
from genai_pipeline.retry_manager import RetryManager
from schemas.assessment_schema import Assessment
from schemas.plan_schema import GeneratedPlan


class AssessmentBatch(BaseModel):
    """Schema for a dedicated assessment-generation LLM call."""

    assessments: list[Assessment] = Field(min_length=1)


class AssessmentGenerator:
    """Generate assessments/rubrics via GenAI; preserve assembler citations and types."""

    def __init__(self, provider: BaseGenAIProvider, prompt_manager: PromptManager | None = None) -> None:
        self.provider = provider
        self.prompt_manager = prompt_manager or PromptManager()

    def enrich(self, plan: GeneratedPlan, source_chunks_block: str) -> list[Assessment]:
        """Replace rubric wording when the model returns a valid batch; otherwise keep assembler assessments."""
        template = self.prompt_manager.load("assessment", "v1")
        prompt = self.prompt_manager.render(
            template,
            requirements_json=plan.model_dump_json(),
            source_chunks_block=source_chunks_block,
            role_title=plan.role_title,
            experience_level=plan.experience_level,
        )
        try:
            response = RetryManager(self.provider).run(
                prompt, schema=AssessmentBatch, config=GenerationConfig(temperature=0.2)
            )
            batch = AssessmentBatch.model_validate(response.parsed)
            by_id = {item.assessment_id: item for item in plan.assessments}
            merged: list[Assessment] = []
            for item in batch.assessments:
                original = by_id.get(item.assessment_id)
                if original is None:
                    continue
                merged.append(
                    item.model_copy(
                        update={
                            "source_document_id": original.source_document_id,
                            "source_section_id": original.source_section_id,
                            "requirement_ids": original.requirement_ids,
                            "assessment_type": original.assessment_type,
                            "stage": original.stage,
                            "grounding_status": original.grounding_status,
                        }
                    )
                )
            return merged or plan.assessments
        except Exception:
            return plan.assessments
