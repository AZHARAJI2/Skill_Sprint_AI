"""Gemini implementation of BaseGenAIProvider using the google-genai SDK."""

from __future__ import annotations

import json
import re
import time
from typing import Any

from pydantic import BaseModel, ValidationError

from config.logging_config import get_logger
from config.settings import settings
from genai_pipeline.base_provider import BaseGenAIProvider, GenerationConfig, GenAIResponse
from src.errors import AppError

logger = get_logger("gemini_provider")


class GeminiProvider(BaseGenAIProvider):
    """Concrete provider wrapping google.genai.Client.

    Fails closed when GEMINI_API_KEY / GOOGLE_API_KEY is missing so the system never
    invents a plan in place of a model response.
    """

    network_backed = True

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model = model or getattr(settings, "gemini_model", None) or "gemini-2.5-flash"
        self._client = None
        self._client_timeout_seconds: float | None = None

    def _client_or_raise(self, timeout_seconds: float | None = None):
        """Return a Gemini client configured for this request's time budget."""
        if not self.api_key:
            raise AppError(
                "GEMINI_API_KEY is not configured; refusing to fabricate a plan",
                status_code=503,
            )
        effective_timeout = timeout_seconds if timeout_seconds is not None else settings.gemini_request_timeout_seconds
        # The SDK rejects manually configured deadlines below 10 seconds.  A
        # None timeout is intentional: it lets the underlying transport wait
        # for a complete structured plan.
        if effective_timeout is not None:
            effective_timeout = max(10.0, effective_timeout)
        if self._client is None or self._client_timeout_seconds != effective_timeout:
            from google import genai
            from google.genai import types

            self._client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(
                    timeout=effective_timeout * 1000 if effective_timeout is not None else None
                ),
            )
            self._client_timeout_seconds = effective_timeout
        return self._client

    def generate(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
        config: GenerationConfig | None = None,
    ) -> GenAIResponse:
        """Call Gemini and parse JSON, optionally validating a Pydantic schema."""
        cfg = config or GenerationConfig()
        model_name = cfg.model or self.model
        requested_timeout = (
            cfg.timeout_seconds
            if cfg.timeout_seconds is not None
            else settings.gemini_request_timeout_seconds
        )
        if cfg.deadline_monotonic is not None:
            remaining = cfg.deadline_monotonic - time.monotonic()
            requested_timeout = remaining if requested_timeout is None else min(requested_timeout, remaining)
        # Settings caps each SDK request; GenerationConfig narrows it further
        # to the plan's remaining end-to-end budget.
        configured_cap = settings.gemini_request_timeout_seconds
        effective_timeout = (
            min(configured_cap, requested_timeout)
            if configured_cap is not None and requested_timeout is not None
            else configured_cap or requested_timeout
        )
        client = self._client_or_raise(effective_timeout)
        started = time.perf_counter()
        try:
            from google.genai import types

            gen_config_kwargs: dict[str, Any] = {
                "max_output_tokens": cfg.max_output_tokens,
                "response_mime_type": "application/json",
            }
            # Gemini 3.8 removed sampling parameters such as temperature.
            # Keep them for legacy model IDs only, so the provider can still
            # be overridden explicitly for an older permitted model.
            if not model_name.startswith("gemini-3.8-"):
                gen_config_kwargs["temperature"] = cfg.temperature
            budget = cfg.thinking_budget if cfg.thinking_budget is not None else getattr(settings, "gemini_thinking_budget", None)
            if budget is not None and budget > 0 and hasattr(types, "ThinkingConfig"):
                try:
                    gen_config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=budget)
                except Exception as ex:
                    logger.warning("could_not_set_thinking_config error=%s", ex)
            if schema is not None:
                # Constrain the model to the Pydantic contract at the API level.
                # Without this, "output JSON matching the schema" is only a
                # suggestion and the model invents its own top-level shape.
                gen_config_kwargs["response_json_schema"] = schema.model_json_schema()
            gen_config = types.GenerateContentConfig(**gen_config_kwargs)
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=gen_config,
            )
        except AppError:
            raise
        except Exception as exc:
            logger.error("gemini_call_failed error=%s", exc)
            status_code = self._provider_status_code(exc)
            if status_code == 429:
                raise AppError(
                    "Gemini quota or rate limit reached. Wait for the provider reset, then generate the complete plan again.",
                    status_code=429,
                    details={"provider": "gemini", "status_code": status_code, "message": str(exc)},
                ) from exc
            if status_code == 404:
                raise AppError(
                    "Configured Gemini model is unavailable. Set GEMINI_MODEL=gemini-3.8-flash and restart the app.",
                    status_code=400,
                    details={"provider": "gemini", "status_code": status_code, "message": str(exc)},
                ) from exc
            timed_out = "timeout" in str(exc).lower() or "timed out" in str(exc).lower()
            unavailable = status_code in {503, 504} or timed_out or any(
                word in str(exc).lower() for word in ("timeout", "timed out", "unavailable", "connection")
            )
            raise AppError(
                (
                    "Gemini did not finish the complete plan before the request time limit. "
                    "Retry the plan, or use a faster supported Gemini model."
                    if timed_out
                    else "Gemini API call failed"
                ),
                status_code=503 if unavailable else 502,
                details={"provider": "gemini", "status_code": status_code, "message": str(exc)},
            ) from exc
        raw_text = getattr(response, "text", None) or ""
        parsed = self._parse_json(raw_text)
        if schema is not None:
            try:
                parsed = schema.model_validate(parsed).model_dump(mode="json")
            except ValidationError as exc:
                raise AppError("Gemini JSON failed schema validation", status_code=502, details=exc.errors()) from exc
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info("gemini_generate model=%s elapsed_ms=%.1f", model_name, elapsed_ms)
        return GenAIResponse(
            parsed=parsed,
            raw_text=raw_text,
            model_name=model_name,
            response_time_ms=elapsed_ms,
            metadata={"api_version": "google-genai"},
        )

    def generate_with_retry(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
        max_retries: int = 3,
        config: GenerationConfig | None = None,
    ) -> GenAIResponse:
        """Retry invalid JSON up to max_retries additional attempts (cap 3)."""
        from genai_pipeline.retry_manager import RetryManager

        return RetryManager(self, max_attempts=max_retries).run(prompt, schema=schema, config=config)

    @staticmethod
    def _provider_status_code(exc: Exception) -> int | None:
        """Extract an HTTP status without depending on one SDK exception class."""
        response = getattr(exc, "response", None)
        value = getattr(response, "status_code", None) or getattr(exc, "code", None)
        if isinstance(value, int):
            return value
        match = re.search(r"\b(4\d{2}|5\d{2})\b", str(exc))
        return int(match.group(1)) if match else None

    @staticmethod
    def _parse_json(raw_text: str) -> dict[str, Any]:
        text = (raw_text or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AppError("Gemini returned non-JSON output", status_code=502, details=str(exc)) from exc
        if not isinstance(payload, dict):
            raise AppError("Gemini JSON root must be an object", status_code=502)
        return payload
