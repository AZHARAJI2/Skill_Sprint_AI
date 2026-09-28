"""Capped retry around a BaseGenAIProvider with structured logging."""

from __future__ import annotations

import time

from pydantic import BaseModel, ValidationError

from config.logging_config import get_logger
from config.settings import settings
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
        deadline_monotonic: float | None = None,
    ) -> GenAIResponse:
        """Attempt generation until schema validation succeeds or the cap is hit."""
        last_error: str | None = None
        last_status_code: int | None = None
        working_prompt = prompt
        for attempt in range(1, self.max_attempts + 1):
            try:
                call_config = config
                if deadline_monotonic is not None:
                    remaining = deadline_monotonic - time.monotonic()
                    if remaining <= 0:
                        raise AppError("Plan-generation time budget was exhausted.", status_code=503)
                    call_config = (config or GenerationConfig()).model_copy(
                        update={"timeout_seconds": min((config or GenerationConfig()).timeout_seconds or remaining, remaining), "deadline_monotonic": deadline_monotonic}
                    )
                # Pass the schema through so providers with constrained-generation
                # support (e.g. Gemini response_json_schema) emit conformant JSON
                # on the first attempt instead of guessing the shape. The result
                # is still validated below as a safety net.
                response = self.provider.generate(working_prompt, schema=schema, config=call_config)
                if schema is not None:
                    parsed_model = schema.model_validate(response.parsed)
                    response.parsed = parsed_model.model_dump(mode="json")
                response.retry_count = attempt - 1
                if attempt > 1:
                    logger.warning("genai_retry_recovered attempt=%s", attempt)
                return response
            except (AppError, ValidationError, ValueError, TypeError) as exc:
                last_status_code = exc.status_code if isinstance(exc, AppError) else None
                # Configuration and quota errors cannot be corrected by
                # resending the prompt. A 503 is a temporary provider overload,
                # so retry it within the hard three-attempt Project Map cap.
                if isinstance(exc, AppError) and exc.status_code in {400, 401, 403, 429}:
                    raise
                detail = exc.details if isinstance(exc, AppError) else None
                detail_error = detail.get("error") if isinstance(detail, dict) else None
                # Give the next retry the actual schema/parser reason, without
                # putting an unbounded provider response into a new prompt.
                last_error = str(detail_error or exc)[:1200]
                logger.warning("genai_retry_failed attempt=%s/%s error=%s", attempt, self.max_attempts, last_error)
                if attempt < self.max_attempts and getattr(self.provider, "network_backed", False):
                    delay = settings.genai_retry_backoff_seconds * attempt
                    if deadline_monotonic is not None:
                        delay = min(delay, max(0, deadline_monotonic - time.monotonic()))
                    logger.info("genai_retry_backoff seconds=%.1f", delay)
                    time.sleep(delay)
                working_prompt = (
                    f"{prompt}\n\nPREVIOUS_OUTPUT_WAS_INVALID. Fix these errors and return JSON only:\n{last_error}"
                )
        logger.error("genai_retry_exhausted attempts=%s last_error=%s", self.max_attempts, last_error)
        if last_status_code == 503:
            if last_error and "time budget" in last_error.casefold():
                raise AppError(
                    "The complete plan exceeded the configured generation time limit. Set SKILLSPRINT_PLAN_TIMEOUT_SECONDS=0 to wait without a cap, then generate again.",
                    status_code=503,
                    details={"attempts": self.max_attempts, "last_error": last_error},
                )
            raise AppError(
                "The configured AI provider is temporarily unavailable after three attempts. Wait a moment and generate the complete plan again.",
                status_code=503,
                details={"attempts": self.max_attempts, "last_error": last_error},
            )
        raise AppError(
            "GenAI output remained invalid after retry cap",
            status_code=502,
            details={"attempts": self.max_attempts, "last_error": last_error},
        )
