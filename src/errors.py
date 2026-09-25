"""Application-level exceptions mapped to HTTP responses by the FastAPI error handler."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Typed application error that the API layer converts into a JSON body."""

    def __init__(self, message: str, status_code: int = 400, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details
