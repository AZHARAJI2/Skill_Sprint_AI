"""Authentication, password hashing, JWT issuance, and RBAC helpers."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config.logging_config import get_logger
from config.settings import settings
from schemas.common_schema import AppRole
from src.auth.models import User
from src.auth.repository import UserRepository
from src.employees.models import Employee
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

    def list_employee_usernames(self) -> dict[int, str]:
        """Map employee profile ids to their linked login usernames."""
        return {
            user.employee_id: user.username
            for user in self.users.list_all()
            if user.employee_id is not None
        }

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

    def change_password(self, user: User, current_password: str, new_password: str) -> None:
        """Change the authenticated user's password after verifying their current password."""
        if not self.hasher.verify(current_password, user.password_hash):
            raise AppError("Your current password is incorrect.", status_code=401)
        if len(new_password) < 8:
            raise AppError("Your new password must contain at least 8 characters.", status_code=422)
        if hmac.compare_digest(current_password, new_password):
            raise AppError("Your new password must be different from your current password.", status_code=422)
        user.password_hash = self.hasher.hash(new_password)
        self.audit.record(user.username, "password_changed", "user", user.username, None)
        logger.info("password_changed username=%s", user.username)

    def provision_employee_account(
        self,
        employee: Employee,
        *,
        preferred_username: str | None = None,
        temporary_password: str | None = None,
        reset_password: bool = False,
        normalize_username: bool = False,
        actor: str = "system",
    ) -> tuple[User, str | None]:
        """Create or activate the Employee login linked to an employee profile.

        New accounts use a preferred username when supplied, otherwise a name
        derived from the employee's first name and department initial. Existing
        usernames are retained unless an administrator explicitly normalizes
        legacy employee accounts.
        A generated password is returned only when a new password was set.
        """
        linked_user = self.users.get_by_employee_id(employee.id)
        password = temporary_password or self._initial_employee_password(employee.employee_code)

        if linked_user is None:
            username = self._resolve_new_employee_username(employee, preferred_username)
            linked_user = self.create_user(username, password, "Employee", employee_id=employee.id)
            self.audit.record(
                actor,
                "employee_account_provisioned",
                "employee",
                employee.employee_code,
                {"username": username},
            )
            return linked_user, password

        changed = False
        if normalize_username:
            normalized_username = self._available_employee_username(employee, linked_user.id)
            if linked_user.username != normalized_username:
                linked_user.username = normalized_username
                changed = True
        if linked_user.app_role != "Employee":
            linked_user.app_role = "Employee"
            changed = True
        if not linked_user.is_active:
            linked_user.is_active = True
            changed = True
        if reset_password:
            linked_user.password_hash = self.hasher.hash(password)
            changed = True
        if changed:
            self.audit.record(
                actor,
                "employee_account_normalized",
                "employee",
                employee.employee_code,
                {"username": linked_user.username, "password_reset": reset_password},
            )
        return linked_user, password if reset_password else None

    def _resolve_new_employee_username(self, employee: Employee, preferred_username: str | None) -> str:
        """Validate an optional username or derive a unique readable one."""
        if preferred_username:
            username = preferred_username.strip().casefold()
            if not re.fullmatch(r"[a-z0-9._-]{3,64}", username):
                raise AppError(
                    "Usernames must be 3–64 characters using letters, numbers, dots, hyphens, or underscores.",
                    status_code=422,
                )
            return username
        return self._available_employee_username(employee, None)

    def _available_employee_username(self, employee: Employee, linked_user_id: int | None) -> str:
        """Build a unique, stable username from employee name and department initial."""
        name_tokens = re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", employee.name).casefold())
        raw_first = name_tokens[0] if name_tokens else "employee"
        first_name = self._safe_username_token(raw_first)
        if first_name == "employee" and raw_first != "employee":
            first_name = f"emp-{self._safe_username_token(employee.employee_code)}"
        department = unicodedata.normalize("NFKC", employee.department).casefold()
        dept_token = self._safe_username_token(department)
        department_initial = dept_token[0] if dept_token else "d"
        base = f"{first_name}-{department_initial}"
        candidates = [base, f"{base}-{self._safe_username_token(employee.employee_code)}"]
        suffix = 2
        while True:
            candidate = candidates.pop(0) if candidates else f"{base}-{self._safe_username_token(employee.employee_code)}-{suffix}"
            existing = self.users.get_by_username(candidate)
            if existing is None or existing.id == linked_user_id:
                return candidate[:64]
            suffix += 1

    @staticmethod
    def _safe_username_token(value: str) -> str:
        """Return a URL- and login-safe identifier token without losing uniqueness."""
        token = re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKC", value).casefold())
        return token or "employee"

    @staticmethod
    def _initial_employee_password(employee_code: str) -> str:
        """Create the initial password shown once to an authorized administrator."""
        return f"SkillSprint!{employee_code}"
