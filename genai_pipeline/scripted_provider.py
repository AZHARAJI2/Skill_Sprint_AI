"""Test/demo provider that returns assembler JSON parsed from the prompt context — not a hard-coded plan."""

from __future__ import annotations

import json
import time
from collections.abc import Callable

from pydantic import BaseModel

from genai_pipeline.base_provider import BaseGenAIProvider, GenerationConfig, GenAIResponse
from src.errors import AppError


class ScriptedProvider(BaseGenAIProvider):
    """Return caller-supplied payloads in order. Used to test retry and schema failure paths."""

    def __init__(self, payloads: list[dict | Exception], model_name: str = "scripted-test") -> None:
        self.payloads = list(payloads)
        self.model_name = model_name
        self.calls = 0

    def generate(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
        config: GenerationConfig | None = None,
    ) -> GenAIResponse:
        del prompt, config
        if self.calls >= len(self.payloads):
            if len(self.payloads) == 1:
                item = self.payloads[0]
            else:
                raise AppError("ScriptedProvider has no remaining payloads", status_code=502)
        else:
            item = self.payloads[self.calls]
        self.calls += 1

        if isinstance(item, Exception):
            raise item
        if schema is not None:
            parsed = schema.model_validate(item).model_dump(mode="json")
        else:
            parsed = item
        return GenAIResponse(parsed=parsed, raw_text=json.dumps(parsed), model_name=self.model_name)

    def generate_with_retry(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
        max_retries: int = 3,
        config: GenerationConfig | None = None,
    ) -> GenAIResponse:
        from genai_pipeline.retry_manager import RetryManager

        return RetryManager(self, max_attempts=max_retries).run(prompt, schema=schema, config=config)


class CallbackProvider(BaseGenAIProvider):
    """Invoke a callback with the prompt so tests can return context-derived structured JSON."""

    def __init__(self, callback: Callable[[str], dict], model_name: str = "callback-test") -> None:
        self.callback = callback
        self.model_name = model_name

    def generate(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
        config: GenerationConfig | None = None,
    ) -> GenAIResponse:
        del config
        started = time.perf_counter()
        parsed = self.callback(prompt)
        if schema is not None:
            parsed = schema.model_validate(parsed).model_dump(mode="json")
        return GenAIResponse(
            parsed=parsed,
            raw_text=json.dumps(parsed),
            model_name=self.model_name,
            response_time_ms=(time.perf_counter() - started) * 1000,
        )

    def generate_with_retry(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
        max_retries: int = 3,
        config: GenerationConfig | None = None,
    ) -> GenAIResponse:
        from genai_pipeline.retry_manager import RetryManager

        return RetryManager(self, max_attempts=max_retries).run(prompt, schema=schema, config=config)
