"""DeepSeek implementation of the provider boundary used by Pipeline 1."""

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

logger = get_logger("deepseek_provider")


class DeepSeekProvider(BaseGenAIProvider):
    """Generate schema-checked JSON through DeepSeek's OpenAI-compatible API."""

    network_backed = True

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.deepseek_api_key
        self.model = model or settings.deepseek_model
        self.base_url = settings.deepseek_base_url
        self.request_timeout_seconds = settings.deepseek_request_timeout_seconds
        self.provider_id = "deepseek"
        self.provider_label = "DeepSeek"
        self.api_key_env = "DEEPSEEK_API_KEY"
        self.extra_headers: dict[str, str] = {}

    def generate(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
        config: GenerationConfig | None = None,
    ) -> GenAIResponse:
        """Call DeepSeek and validate its JSON response against the supplied schema."""
        if not self.api_key:
            raise AppError(
                f"{self.api_key_env} is not configured; refusing to fabricate a plan",
                status_code=503,
            )

        cfg = config or GenerationConfig()
        timeout = cfg.timeout_seconds if cfg.timeout_seconds is not None else self.request_timeout_seconds
        if cfg.deadline_monotonic is not None:
            remaining = cfg.deadline_monotonic - time.monotonic()
            if remaining <= 0:
                raise AppError("Plan-generation time budget was exhausted.", status_code=503)
            timeout = remaining if timeout is None else min(timeout, remaining)

        body: dict[str, Any] = {
            "model": cfg.model or self.model,
            "messages": [
                {"role": "system", "content": "Return only a valid JSON object. Follow the supplied schema exactly."},
                {"role": "user", "content": prompt},
            ],
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_output_tokens,
        }
        if schema is not None or cfg.json_mode:
            body["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    f"{self.base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", **self.extra_headers},
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise AppError(
                f"{self.provider_label} did not finish the complete plan before the request time limit.",
                status_code=503,
                details={"provider": self.provider_id, "error": type(exc).__name__},
            ) from exc
        except httpx.HTTPError as exc:
            raise AppError(
                f"{self.provider_label} API connection failed.",
                status_code=503,
                details={"provider": self.provider_id, "error": type(exc).__name__},
            ) from exc

        if response.is_error:
            self._raise_provider_error(response)

        try:
            payload = response.json()
            raw_text = payload["choices"][0]["message"]["content"]
            if not isinstance(raw_text, str):
                raise TypeError("DeepSeek response content was not text")
            parsed = self._parse_json(raw_text)
            if schema is not None:
                parsed = schema.model_validate(parsed).model_dump(mode="json")
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
            raise AppError(
                f"{self.provider_label} returned JSON that does not match the required plan schema.",
                status_code=502,
                details={"provider": self.provider_id, "error": str(exc)},
            ) from exc

        elapsed_ms = (time.perf_counter() - started) * 1000
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        model_name = payload.get("model") if isinstance(payload.get("model"), str) else body["model"]
        logger.info("%s_generate model=%s elapsed_ms=%.1f", self.provider_id, model_name, elapsed_ms)
        return GenAIResponse(
            parsed=parsed,
            raw_text=raw_text,
            model_name=model_name,
            response_time_ms=elapsed_ms,
            metadata={"api_version": f"{self.provider_id}-chat-completions", "usage": usage},
        )

    def generate_with_retry(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
        max_retries: int = 3,
        config: GenerationConfig | None = None,
    ) -> GenAIResponse:
        """Delegate capped retry behavior to the provider-independent retry manager."""
        from genai_pipeline.retry_manager import RetryManager

        return RetryManager(self, max_attempts=max_retries).run(prompt, schema=schema, config=config)

    @staticmethod
    def _parse_json(raw_text: str) -> dict[str, Any]:
        """Parse a JSON object, tolerating fences or explanatory surrounding text."""
        text = raw_text.strip()
        if text.startswith("```"):
            text = text.removeprefix("```").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
            if text.endswith("```"):
                text = text[:-3].strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # Some OpenAI-compatible models return a valid JSON object after a
            # short prose prefix despite JSON mode. Decode the first object
            # instead of discarding an otherwise usable response.
            object_start = text.find("{")
            if object_start < 0:
                raise
            parsed, _ = json.JSONDecoder().raw_decode(text[object_start:])
        if not isinstance(parsed, dict):
            raise ValueError("DeepSeek JSON root must be an object")
        return parsed

    def _raise_provider_error(self, response: httpx.Response) -> None:
        """Map DeepSeek HTTP failures to safe, actionable application errors."""
        try:
            provider_message = response.json().get("error", {}).get("message")
        except (ValueError, AttributeError):
            provider_message = response.text[:500]
        status = response.status_code
        if status == 401:
            message = f"{self.provider_label} rejected {self.api_key_env}. Check the backend secret and restart the app."
        elif status == 429:
            message = f"{self.provider_label} rate limit or balance limit reached. Wait or add balance, then generate the complete plan again."
        elif status in {502, 503, 504}:
            message = f"{self.provider_label} is temporarily unavailable. Retry the complete plan in a moment."
        else:
            message = f"{self.provider_label} API call failed."
        raise AppError(
            message,
            status_code=status if status in {400, 401, 403, 404, 429, 503} else 502,
            details={"provider": self.provider_id, "status_code": status, "message": provider_message},
        )
