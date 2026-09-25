"""User repository for authentication."""

from __future__ import annotations

from sqlalchemy.orm import Session

from database.base import BaseRepository
from src.auth.models import User


class UserRepository(BaseRepository[User]):
    """Data access for login identities."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, User)

    def get_by_username(self, username: str) -> User | None:
        """Fetch a user by unique username."""
        return self.session.query(User).filter(User.username == username).one_or_none()
