"""Groq fallback provider using its OpenAI-compatible chat-completions API."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from config.logging_config import get_logger
from config.settings import settings
from genai_pipeline.base_provider import BaseGenAIProvider, GenerationConfig, GenAIResponse
from src.errors import AppError

logger = get_logger("groq_provider")


class GroqProvider(BaseGenAIProvider):
    """Call Groq only as a configured resilience fallback for Gemini outages."""

    network_backed = True
    endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.groq_api_key
        self.model = model or settings.groq_model

    @property
    def configured(self) -> bool:
        """Return whether this fallback has credentials without exposing them."""
        return bool(self.api_key)

    def generate(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
        config: GenerationConfig | None = None,
    ) -> GenAIResponse:
        """Request JSON-only output and validate it against the caller's schema."""
        if not self.api_key:
            raise AppError("GROQ_API_KEY is not configured.", status_code=503)
        cfg = config or GenerationConfig()
        started = time.perf_counter()
        timeout = cfg.timeout_seconds or settings.groq_request_timeout_seconds
        payload: dict[str, Any] = {
            "model": cfg.model or self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        try:
            response = httpx.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            body = response.json()
            raw_text = body["choices"][0]["message"]["content"]
            parsed = json.loads(raw_text)
        except httpx.TransportError as exc:
            raise AppError(
                "Groq API is temporarily unavailable.",
                status_code=503,
                details={"provider": "groq", "message": str(exc)},
            ) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            mapped_status = status if status in {401, 403} else (503 if status in {429, 503, 504} else 502)
            raise AppError(
                "Groq API call failed.",
                status_code=mapped_status,
                details={"provider": "groq", "status_code": status, "message": exc.response.text[:500]},
            ) from exc
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise AppError("Groq returned invalid JSON.", status_code=502, details=str(exc)) from exc
        if not isinstance(parsed, dict):
            raise AppError("Groq JSON root must be an object.", status_code=502)
        if schema is not None:
            try:
                parsed = schema.model_validate(parsed).model_dump(mode="json")
            except ValidationError as exc:
                raise AppError("Groq JSON failed schema validation.", status_code=502, details=exc.errors()) from exc
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info("groq_generate model=%s elapsed_ms=%.1f", payload["model"], elapsed_ms)
        return GenAIResponse(
            parsed=parsed,
            raw_text=raw_text,
            model_name=str(payload["model"]),
            response_time_ms=elapsed_ms,
            metadata={"api_version": "openai-compatible", "provider": "groq"},
        )

    def generate_with_retry(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
        max_retries: int = 3,
        config: GenerationConfig | None = None,
    ) -> GenAIResponse:
        """Delegate capped schema repair behavior to the shared retry manager."""
        from genai_pipeline.retry_manager import RetryManager

        return RetryManager(self, max_attempts=max_retries).run(prompt, schema=schema, config=config)
