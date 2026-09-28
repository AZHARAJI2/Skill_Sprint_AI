"""FastAPI dependencies for Pipeline 1 provider injection."""

from genai_pipeline.base_provider import BaseGenAIProvider
from genai_pipeline.failover_provider import FailoverProvider
from genai_pipeline.gemini_provider import GeminiProvider
from genai_pipeline.groq_provider import GroqProvider


def get_genai_provider() -> BaseGenAIProvider:
    """Prefer the configured low-latency Groq path, retaining Gemini as fallback.

    The project-map Gemini integration remains available when Groq is absent.
    With both keys configured, using Groq first prevents Gemini's mandatory
    10-second request deadline from consuming the plan's 25-second budget.
    """
    groq = GroqProvider()
    if groq.configured:
        return FailoverProvider(groq, fallback=GeminiProvider())
    return GeminiProvider()
