"""Sticky Gemini-to-Groq provider failover for one plan-generation request."""

from __future__ import annotations

import time

from pydantic import BaseModel

from config.logging_config import get_logger
from genai_pipeline.base_provider import BaseGenAIProvider, GenerationConfig, GenAIResponse
from src.errors import AppError

logger = get_logger("failover_provider")


class FailoverProvider(BaseGenAIProvider):
    """Use the primary provider until a service outage, then stay on the fallback."""

    network_backed = True

    def __init__(self, primary: BaseGenAIProvider, fallback: BaseGenAIProvider | None = None) -> None:
        self.primary = primary
        self.fallback = fallback
        self.active_provider = primary

    @property
    def model(self) -> str | None:
        """Expose the active model for safe telemetry only."""
        return getattr(self.active_provider, "model", None) or getattr(self.active_provider, "model_name", None)

    def generate(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
        config: GenerationConfig | None = None,
    ) -> GenAIResponse:
        """Generate once, failing over only on an upstream availability failure."""
        try:
            return self.active_provider.generate(prompt, schema=schema, config=config)
        except AppError as exc:
            if self.active_provider is self.primary and self.fallback is not None and exc.status_code in {503, 504}:
                self.active_provider = self.fallback
                logger.warning(
                    "genai_failover primary=%s fallback=%s reason=%s",
                    type(self.primary).__name__,
                    type(self.fallback).__name__,
                    exc,
                )
                fallback_config = config
                if config and config.deadline_monotonic is not None:
                    remaining = config.deadline_monotonic - time.monotonic()
                    if remaining <= 0:
                        raise AppError("Plan-generation time budget was exhausted.", status_code=503) from exc
                    fallback_config = config.model_copy(
                        update={"timeout_seconds": min(config.timeout_seconds or remaining, remaining)}
                    )
                return self.active_provider.generate(prompt, schema=schema, config=fallback_config)
            raise

    def generate_with_retry(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
        max_retries: int = 3,
        config: GenerationConfig | None = None,
    ) -> GenAIResponse:
        """Delegate retry behavior while preserving sticky provider selection."""
        from genai_pipeline.retry_manager import RetryManager

        return RetryManager(self, max_attempts=max_retries).run(prompt, schema=schema, config=config)
