"""Command Code Provider API adapter for the SkillSprint GenAI boundary."""

from __future__ import annotations

from config.settings import settings
from genai_pipeline.deepseek_provider import DeepSeekProvider


class CommandCodeProvider(DeepSeekProvider):
    """Use Command Code's OpenAI-compatible Chat Completions API.

    Command Code exposes an OpenAI-compatible endpoint, so the JSON validation,
    retry, timeout, and source-grounding protections implemented by the shared
    provider adapter remain unchanged.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        super().__init__(
            api_key=api_key if api_key is not None else settings.command_code_api_key,
            model=model or settings.command_code_model,
        )
        self.base_url = settings.command_code_base_url
        self.request_timeout_seconds = settings.command_code_request_timeout_seconds
        self.provider_id = "commandcode"
        self.provider_label = "Command Code"
        self.api_key_env = "CMD_API_KEY (or COMMAND_CODE_API_KEY)"
        self.extra_headers = {"x-cmd-zdr": "1"} if settings.command_code_zero_data_retention else {}
