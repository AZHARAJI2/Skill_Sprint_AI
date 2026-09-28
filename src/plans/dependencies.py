"""FastAPI dependencies for Pipeline 1 provider injection."""

from config.settings import settings
from genai_pipeline.base_provider import BaseGenAIProvider
from genai_pipeline.commandcode_provider import CommandCodeProvider
from genai_pipeline.deepseek_provider import DeepSeekProvider
from genai_pipeline.gemini_provider import GeminiProvider


def get_genai_provider() -> BaseGenAIProvider:
    """Return the configured production provider, Command Code by default."""
    if settings.genai_provider == "gemini":
        return GeminiProvider()
    if settings.genai_provider == "deepseek":
        return DeepSeekProvider()
    return CommandCodeProvider()
