"""Abstract base class for all Pipeline 2 pure-Python validators."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from schemas.plan_schema import GeneratedPlan
from schemas.validation_schema import ItemValidationResult


class BaseValidator(ABC):
    """Abstract base for all Pipeline 2 validation rules.
    
    CRITICAL: Zero GenAI calls allowed in any validator subclass.
    """

    @abstractmethod
    def validate(
        self,
        plan: GeneratedPlan | dict[str, Any],
        matrix: list[Any] | None = None,
        documents: list[Any] | None = None,
        chunks: list[Any] | None = None,
    ) -> list[ItemValidationResult]:
        """Run validation rule and return item-level validation results."""
