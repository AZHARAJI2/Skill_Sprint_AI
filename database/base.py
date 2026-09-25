"""SQLAlchemy engine, session factory, generic repository, and metadata Base."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any, Generic, TypeVar

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config.settings import settings


class Base(DeclarativeBase):
    """Declarative base for all SkillSprint SQLAlchemy models."""


def create_db_engine(url: str | None = None):
    """Create an engine. SQLite needs check_same_thread=False for FastAPI."""
    database_url = url or settings.database_url
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args, future=True)


engine = create_db_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """Generic CRUD helpers. All database access goes through repositories, never raw SQL in routes."""

    def __init__(self, session: Session, model: type[T]) -> None:
        self.session = session
        self.model = model

    def add(self, entity: T) -> T:
        """Persist a new entity and flush so generated keys are available."""
        self.session.add(entity)
        self.session.flush()
        return entity

    def get(self, entity_id: Any) -> T | None:
        """Fetch one entity by primary key."""
        return self.session.get(self.model, entity_id)

    def list_all(self) -> list[T]:
        """Return all rows for this model."""
        return list(self.session.query(self.model).all())

    def delete(self, entity: T) -> None:
        """Delete an entity from the current session."""
        self.session.delete(entity)
        self.session.flush()


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a session and commits or rolls back."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
