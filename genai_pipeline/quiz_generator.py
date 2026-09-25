"""Quiz generation plus Python distractor / correct-answer validation against source excerpts."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from genai_pipeline.base_provider import BaseGenAIProvider, GenerationConfig
from genai_pipeline.plan_assembler import SourceExcerpt
from genai_pipeline.prompt_manager import PromptManager
from genai_pipeline.retry_manager import RetryManager
from schemas.common_schema import DistractorValidationStatus, GroundingStatus
from schemas.plan_schema import GeneratedPlan
from schemas.quiz_schema import QuizQuestion


class QuizBatch(BaseModel):
    """Schema for a dedicated quiz-generation LLM call."""

    quizzes: list[QuizQuestion] = Field(min_length=1)


class DistractorValidator:
    """Validate that the correct option is source-supported and distractors are not contradictory facts."""

    _TOKEN = re.compile(r"[a-z0-9]+")

    def validate(
        self,
        question: QuizQuestion,
        excerpt: SourceExcerpt | None,
    ) -> QuizQuestion:
        """Return a possibly repaired question with an explicit distractor_validation_status."""
        source = (excerpt.text if excerpt else "") + " " + question.explanation
        source_tokens = self._tokens(source)
        correct_values = question.correct_answer if isinstance(question.correct_answer, list) else [question.correct_answer]
        if not any(self._overlap(self._tokens(value), source_tokens) >= 0.08 or value.lower() in source.lower() for value in correct_values):
            if question.requirement_id.lower() not in source.lower() and not any(
                value.lower() in (question.question_text + " " + question.explanation).lower() for value in correct_values
            ):
                return question.model_copy(update={"distractor_validation_status": DistractorValidationStatus.FAILED_NOT_IN_SOURCE})

        distractors = [option for option in question.options if option not in correct_values]
        for distractor in distractors:
            if self._is_contradictory_claim(distractor):
                repaired = self._repair(question, excerpt)
                return repaired.model_copy(update={"distractor_validation_status": DistractorValidationStatus.REPAIRED})
        return question.model_copy(update={"distractor_validation_status": DistractorValidationStatus.PASSED})

    def _is_contradictory_claim(self, distractor: str) -> bool:
        lowered = distractor.lower()
        # Plausible traps ("waived for all new hires") are allowed. Contradictory
        # distractors assert the cited source is fake or does not exist.
        return (
            "no source document exists" in lowered
            or "the cited source is fake" in lowered
            or "this policy is not real" in lowered
        )

    def _repair(self, question: QuizQuestion, excerpt: SourceExcerpt | None) -> QuizQuestion:
        correct = question.correct_answer if isinstance(question.correct_answer, str) else question.correct_answer[0]
        options = [correct, "This requirement is waived for all new hires", "Defer this item until after the first annual review"]
        return question.model_copy(update={"options": options, "correct_answer": correct, "question_type": question.question_type})

    def _tokens(self, text: str) -> set[str]:
        return {token for token in self._TOKEN.findall((text or "").lower()) if len(token) > 2}

    def _overlap(self, left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / len(left)


class QuizGenerator:
    """Generate quizzes via GenAI and always run Python distractor validation."""

    def __init__(self, provider: BaseGenAIProvider, prompt_manager: PromptManager | None = None) -> None:
        self.provider = provider
        self.prompt_manager = prompt_manager or PromptManager()
        self.distractors = DistractorValidator()

    def enrich(
        self,
        plan: GeneratedPlan,
        source_chunks_block: str,
        excerpts: dict[tuple[str, str], SourceExcerpt],
    ) -> list[QuizQuestion]:
        """Merge model-written stems onto assembler questions, then validate options in Python."""
        template = self.prompt_manager.load("quiz_generation", "v1")
        prompt = self.prompt_manager.render(
            template,
            requirements_json=plan.model_dump_json(),
            source_chunks_block=source_chunks_block,
            role_title=plan.role_title,
        )
        quizzes = plan.quizzes
        try:
            response = RetryManager(self.provider).run(prompt, schema=QuizBatch, config=GenerationConfig(temperature=0.2))
            batch = QuizBatch.model_validate(response.parsed)
            by_id = {item.question_id: item for item in plan.quizzes}
            merged: list[QuizQuestion] = []
            for quiz in batch.quizzes:
                original = by_id.get(quiz.question_id)
                if original is None:
                    continue
                merged.append(
                    quiz.model_copy(
                        update={
                            "source_document_id": original.source_document_id,
                            "source_section_id": original.source_section_id,
                            "requirement_id": original.requirement_id,
                            "grounding_status": original.grounding_status,
                        }
                    )
                )
            if merged:
                quizzes = merged
        except Exception:
            quizzes = plan.quizzes
        validated: list[QuizQuestion] = []
        for quiz in quizzes:
            excerpt = excerpts.get((quiz.source_document_id, quiz.source_section_id))
            if excerpt and excerpt.flagged:
                quiz = quiz.model_copy(update={"grounding_status": GroundingStatus.INJECTION_FLAGGED})
            validated.append(self.distractors.validate(quiz, excerpt))
        return validated
