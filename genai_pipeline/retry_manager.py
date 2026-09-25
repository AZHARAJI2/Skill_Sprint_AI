"""Capped retry around a BaseGenAIProvider with structured logging."""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from config.logging_config import get_logger
from genai_pipeline.base_provider import BaseGenAIProvider, GenerationConfig, GenAIResponse
from src.errors import AppError

logger = get_logger("retry_manager")

MAX_ATTEMPTS = 3


class RetryManager:
    """Retry invalid or incomplete GenAI output. Hard cap: 3 attempts."""

    def __init__(self, provider: BaseGenAIProvider, max_attempts: int = MAX_ATTEMPTS) -> None:
        self.provider = provider
        self.max_attempts = min(max_attempts, MAX_ATTEMPTS)

    def run(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
        config: GenerationConfig | None = None,
    ) -> GenAIResponse:
        """Attempt generation until schema validation succeeds or the cap is hit."""
        last_error: str | None = None
        working_prompt = prompt
        for attempt in range(1, self.max_attempts + 1):
            try:
                # Pass the schema through so providers with constrained-generation
                # support (e.g. Gemini response_json_schema) emit conformant JSON
                # on the first attempt instead of guessing the shape. The result
                # is still validated below as a safety net.
                response = self.provider.generate(working_prompt, schema=schema, config=config)
                if schema is not None:
                    parsed_model = schema.model_validate(response.parsed)
                    response.parsed = parsed_model.model_dump(mode="json")
                response.retry_count = attempt - 1
                if attempt > 1:
                    logger.warning("genai_retry_recovered attempt=%s", attempt)
                return response
            except (AppError, ValidationError, ValueError, TypeError) as exc:
                if isinstance(exc, AppError) and exc.status_code in {401, 403, 503}:
                    raise
                last_error = str(exc)
                logger.warning("genai_retry_failed attempt=%s/%s error=%s", attempt, self.max_attempts, last_error)
                working_prompt = (
                    f"{prompt}\n\nPREVIOUS_OUTPUT_WAS_INVALID. Fix these errors and return JSON only:\n{last_error}"
                )
        logger.error("genai_retry_exhausted attempts=%s last_error=%s", self.max_attempts, last_error)
        raise AppError(
            "GenAI output remained invalid after retry cap",
            status_code=502,
            details={"attempts": self.max_attempts, "last_error": last_error},
        )
