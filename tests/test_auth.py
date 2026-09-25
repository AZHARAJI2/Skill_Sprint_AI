"""Auth and RBAC tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.base import get_session
from database.migrations import create_schema
from src.auth.service import AuthService, PasswordHasher
from src.errors import AppError
from src.main import app


def test_password_hash_roundtrip() -> None:
    """Hasher never stores plaintext and verifies the original password."""
    hasher = PasswordHasher()
    stored = hasher.hash("secret-pass")
    assert stored != "secret-pass"
    assert hasher.verify("secret-pass", stored)
    assert not hasher.verify("wrong", stored)


def test_authenticate_rejects_bad_password(session: Session) -> None:
    """Unknown users and bad passwords raise 401."""
    service = AuthService(session)
    service.create_user("admin", "admin123", "Admin")
    with pytest.raises(AppError) as exc:
        service.authenticate("admin", "nope")
    assert exc.value.status_code == 401


def test_api_login_and_rbac_forbidden() -> None:
    """VG-1.7: five-role skeleton — Employee cannot upload documents."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    create_schema(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    db = factory()
    AuthService(db).create_user("employee", "employee123", "Employee")
    db.commit()

    def override_session():
        local = factory()
        try:
            yield local
            local.commit()
        finally:
            local.close()

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    denied = client.get("/api/employees")
    assert denied.status_code == 401
    token = client.post("/api/login", json={"username": "employee", "password": "employee123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    forbidden = client.post("/api/documents/ingest-sample", headers=headers)
    assert forbidden.status_code == 403
    me = client.get("/api/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["role"] == "Employee"
    app.dependency_overrides.clear()
    db.close()
