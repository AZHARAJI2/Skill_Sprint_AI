"""Re-export so genai_pipeline consumers import InjectionGuard from one pipeline package."""

from security.injection_guard import InjectionGuard, InjectionScanResult

__all__ = ["InjectionGuard", "InjectionScanResult"]
