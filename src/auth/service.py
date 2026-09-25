"""Authentication, password hashing, JWT issuance, and RBAC helpers."""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config.logging_config import get_logger
from config.settings import settings
from schemas.common_schema import AppRole
from src.auth.models import User
from src.auth.repository import UserRepository
from src.errors import AppError
from src.reviews.repository import AuditRepository

logger = get_logger("auth")

PBKDF2_ITERATIONS = 200_000


class PasswordHasher:
    """PBKDF2-SHA256 hasher (stdlib) so password hashing does not depend on bcrypt wheels."""

    def hash(self, password: str) -> str:
        """Return salt+digest hex suitable for storage."""
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
        return f"{salt.hex()}${digest.hex()}"

    def verify(self, password: str, stored: str) -> bool:
        """Constant-time compare of a password against a stored hash."""
        try:
            salt_hex, digest_hex = stored.split("$", 1)
        except ValueError:
            return False
        salt = bytes.fromhex(salt_hex)
        expected = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
        return hmac.compare_digest(expected.hex(), digest_hex)


class AuthService:
    """Login, token creation, and user bootstrap."""

    def __init__(self, session: Session) -> None:
        self.users = UserRepository(session)
        self.hasher = PasswordHasher()
        self.audit = AuditRepository(session)

    def create_user(
        self, username: str, password: str, app_role: str, employee_id: int | None = None
    ) -> User:
        """Create a login identity with an RBAC role."""
        if app_role not in {role.value for role in AppRole}:
            raise AppError(f"Invalid app role: {app_role}", status_code=400)
        if self.users.get_by_username(username):
            raise AppError(f"Username already exists: {username}", status_code=409)
        user = User(
            username=username,
            password_hash=self.hasher.hash(password),
            app_role=app_role,
            employee_id=employee_id,
            is_active=True,
        )
        self.users.add(user)
        self.audit.record("system", "user_created", "user", username, {"app_role": app_role})
        logger.info("user_created username=%s role=%s", username, app_role)
        return user

    def authenticate(self, username: str, password: str) -> User:
        """Verify credentials and return the user."""
        user = self.users.get_by_username(username)
        if user is None or not user.is_active or not self.hasher.verify(password, user.password_hash):
            logger.warning("login_failed username=%s", username)
            raise AppError("Invalid username or password", status_code=401)
        self.audit.record(username, "login_success", "user", username, {"app_role": user.app_role})
        logger.info("login_success username=%s role=%s", username, user.app_role)
        return user

    def issue_token(self, user: User) -> str:
        """Create a signed JWT for cookie/bearer use."""
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
        payload = {"sub": user.username, "role": user.app_role, "uid": user.id, "exp": expire}
        return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

    def user_from_token(self, token: str) -> User:
        """Decode a JWT and load the user."""
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        except JWTError as exc:
            raise AppError("Invalid or expired token", status_code=401) from exc
        username = payload.get("sub")
        user = self.users.get_by_username(username) if username else None
        if user is None or not user.is_active:
            raise AppError("Invalid or expired token", status_code=401)
        return user

    def ensure_user(self, username: str, password: str, app_role: str, employee_id: int | None = None) -> User:
        """Idempotent user create for seeding."""
        existing = self.users.get_by_username(username)
        if existing:
            return existing
        return self.create_user(username, password, app_role, employee_id=employee_id)
