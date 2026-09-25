"""FastAPI dependencies for current user and role gates."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database.base import get_session
from src.auth.models import User
from src.auth.service import AuthService
from src.errors import AppError

_bearer = HTTPBearer(auto_error=False)


def get_token(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    """Read JWT from Authorization Bearer or the skillsprint_token cookie."""
    if credentials and credentials.credentials:
        return credentials.credentials
    cookie = request.cookies.get("skillsprint_token")
    if cookie:
        return cookie
    raise AppError("Not authenticated", status_code=401)


def get_current_user(token: str = Depends(get_token), session: Session = Depends(get_session)) -> User:
    """Resolve the authenticated user from the token."""
    return AuthService(session).user_from_token(token)


def require_role(*allowed: str) -> Callable:
    """Return a dependency that allows listed RBAC roles, plus Admin always."""

    def _checker(user: User = Depends(get_current_user)) -> User:
        if user.app_role == "Admin":
            return user
        if user.app_role not in allowed:
            raise AppError("Forbidden for this role", status_code=403, details={"role": user.app_role})
        return user

    return _checker
