"""Abstract GenAI provider: every LLM call in the codebase goes through this interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class GenerationConfig(BaseModel):
    """Optional generation parameters passed to a provider."""

    temperature: float = 0.2
    max_output_tokens: int = 16384
    model: str | None = None


class GenAIResponse(BaseModel):
    """Normalized provider result with parsed JSON and telemetry."""

    parsed: dict[str, Any]
    raw_text: str
    model_name: str
    retry_count: int = 0
    response_time_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseGenAIProvider(ABC):
    """Abstract base for all GenAI API providers."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
        config: GenerationConfig | None = None,
    ) -> GenAIResponse:
        """Generate structured output from the LLM."""

    @abstractmethod
    def generate_with_retry(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
        max_retries: int = 3,
        config: GenerationConfig | None = None,
    ) -> GenAIResponse:
        """Generate with automatic retry on invalid or incomplete output."""
