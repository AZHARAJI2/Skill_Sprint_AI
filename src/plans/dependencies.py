"""FastAPI dependencies for Pipeline 1 provider injection."""

from genai_pipeline.base_provider import BaseGenAIProvider
from genai_pipeline.gemini_provider import GeminiProvider


def get_genai_provider() -> BaseGenAIProvider:
    """Production default: Gemini. Tests override this dependency with a scripted provider."""
    return GeminiProvider()
