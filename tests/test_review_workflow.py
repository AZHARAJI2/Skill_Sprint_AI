"""Tests for Phase 4 — Human Review Workflow (Tasks 48 & 49).

Coverage:
  1. Review queue retrieval (empty + populated)
  2. Approve action
  3. Reject action (with and without comment)
  4. Edit action
  5. Regenerate request
  6. Add comment
  7. Unauthorized access (Employee role blocked)
  8. AuditEntry created for every action
  9. original_result is preserved (never mutated)
 10. reviewer_override stored correctly alongside original_result
 11. Both original_result AND reviewer_override exist in the audit trail details
 12. Full decision history endpoint
 13. Full audit trail endpoint

The test suite uses the shared ``session`` fixture from conftest.py (in-memory
SQLite with the full project schema) and a FastAPI TestClient with injected
session, matching the pattern from test_auth.py.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database.base import get_session
from database.migrations import create_schema
from src.auth.models import User
from src.auth.service import AuthService
from src.main import app
from src.reviews.models import AuditEntry, ReviewDecision, ValidationReportRecord
from src.reviews.service import ReviewService, ReviewRepository, ValidationReportRepository
from src.reviews.repository import AuditRepository


# ---------------------------------------------------------------------------
# Test database + client infrastructure
# ---------------------------------------------------------------------------

def _make_engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


@pytest.fixture()
def db_session():
    """Isolated in-memory database with the full schema for service-level tests."""
    engine = _make_engine()
    create_schema(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    db = factory()
    try:
        yield db
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def client_with_db():
    """TestClient + isolated in-memory DB + pre-seeded Reviewer and Employee users.

    Returns (client, reviewer_token, employee_token, db_session).
    """
    engine = _make_engine()
    create_schema(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    db = factory()

    auth = AuthService(db)
    auth.create_user("reviewer", "rev123", "Reviewer")
    auth.create_user("employee_user", "emp123", "Employee")
    db.commit()

    def override_session():
        local = factory()
        try:
            yield local
            local.commit()
        finally:
            local.close()

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app, raise_server_exceptions=True)

    reviewer_token = client.post(
        "/api/login", json={"username": "reviewer", "password": "rev123"}
    ).json()["access_token"]
    employee_token = client.post(
        "/api/login", json={"username": "employee_user", "password": "emp123"}
    ).json()["access_token"]

    yield client, reviewer_token, employee_token, db

    app.dependency_overrides.clear()
    db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reviewer_user(session: Session) -> User:
    """Create a minimal reviewer User for service-layer tests."""
    auth = AuthService(session)
    user = auth.create_user("svc_reviewer", "pass123", "Reviewer")
    session.flush()
    return user


def _sample_original_result(item_id: str = "M-001", item_type: str = "module") -> dict:
    return {
        "item_id": item_id,
        "item_type": item_type,
        "verification_status": "Manual Review Required",
        "details": "Source document reference not found in corpus.",
        "source_references": ["POL-02", "SOP-01"],
    }


# ---------------------------------------------------------------------------
# 1. Review queue — empty
# ---------------------------------------------------------------------------

class TestReviewQueueEmpty:
    """Queue is empty when no validation reports exist."""

    def test_get_queue_returns_empty_list(self, db_session: Session) -> None:
        """No reports → empty queue."""
        service = ReviewService(db_session)
        assert service.get_queue() == []

    def test_get_queue_api_empty(self, client_with_db) -> None:
        client, reviewer_token, _, _ = client_with_db
        resp = client.get(
            "/api/reviews/queue",
            headers={"Authorization": f"Bearer {reviewer_token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# 2. Review queue — populated from a persisted ValidationReportRecord
# ---------------------------------------------------------------------------

class TestReviewQueuePopulated:
    """Items with review-required statuses appear in the queue."""

    def _seed_report(self, session: Session, plan_id: int = 1) -> ValidationReportRecord:
        report = ValidationReportRecord(
            plan_id=plan_id,
            coverage_score=100.0,
            traceability_score=95.0,
            consistency_score=None,
            overall_status="Manual Review Required",
            payload={
                "per_item_results": [
                    {
                        "item_id": "M-001",
                        "item_type": "module",
                        "verification_status": "Manual Review Required",
                        "details": "Hallucination detected.",
                        "source_references": ["POL-02"],
                    },
                    {
                        "item_id": "M-002",
                        "item_type": "module",
                        "verification_status": "Verified",  # should NOT appear in queue
                        "details": "OK",
                        "source_references": [],
                    },
                ]
            },
        )
        session.add(report)
        session.flush()
        return report

    def test_queue_contains_review_required_item(self, db_session: Session) -> None:
        self._seed_report(db_session)
        service = ReviewService(db_session)
        queue = service.get_queue()
        assert len(queue) == 1
        assert queue[0].item_id == "M-001"

    def test_queue_excludes_verified_item(self, db_session: Session) -> None:
        self._seed_report(db_session)
        service = ReviewService(db_session)
        queue = service.get_queue()
        ids = [q.item_id for q in queue]
        assert "M-002" not in ids

    def test_queue_item_carries_original_result(self, db_session: Session) -> None:
        self._seed_report(db_session)
        service = ReviewService(db_session)
        queue = service.get_queue()
        assert queue[0].original_result is not None
        assert queue[0].original_result["verification_status"] == "Manual Review Required"


# ---------------------------------------------------------------------------
# 3. Approve
# ---------------------------------------------------------------------------

class TestApprove:
    """Approve action preserves original, sets no reviewer_override, logs audit entry."""

    def test_approve_creates_review_decision(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        original = _sample_original_result()
        decision = service.approve(
            item_id="M-001",
            item_type="module",
            original_result=original,
            reviewer=reviewer,
            comment="Looks good.",
        )
        assert decision.id is not None
        assert decision.action == "approve"

    def test_approve_preserves_original_result(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        original = _sample_original_result()
        decision = service.approve(
            item_id="M-001",
            item_type="module",
            original_result=original,
            reviewer=reviewer,
        )
        # original_result must be unchanged
        assert decision.original_result == original

    def test_approve_has_no_reviewer_override(self, db_session: Session) -> None:
        """Approve = agreement with original; no content change."""
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        decision = service.approve(
            item_id="M-001",
            item_type="module",
            original_result=_sample_original_result(),
            reviewer=reviewer,
        )
        assert decision.reviewer_override is None

    def test_approve_creates_audit_entry(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        service.approve(
            item_id="M-001",
            item_type="module",
            original_result=_sample_original_result(),
            reviewer=reviewer,
            comment="Approved.",
        )
        entries = (
            db_session.query(AuditEntry)
            .filter(AuditEntry.entity_id == "M-001")
            .all()
        )
        assert len(entries) == 1
        assert entries[0].action == "review_approved"

    def test_approve_api(self, client_with_db) -> None:
        client, reviewer_token, _, _ = client_with_db
        resp = client.post(
            "/api/reviews/M-001/approve",
            headers={"Authorization": f"Bearer {reviewer_token}"},
            json={
                "item_type": "module",
                "original_result": _sample_original_result(),
                "comment": "Approved via API.",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "approve"
        assert data["original_result"] is not None
        assert data["reviewer_override"] is None


# ---------------------------------------------------------------------------
# 4. Reject
# ---------------------------------------------------------------------------

class TestReject:
    """Reject action requires comment; preserves original; sets reviewer_override."""

    def test_reject_with_comment_succeeds(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        decision = service.reject(
            item_id="M-002",
            item_type="module",
            original_result=_sample_original_result("M-002"),
            reviewer=reviewer,
            comment="Contradicts POL-02.",
        )
        assert decision.action == "reject"
        assert decision.comment == "Contradicts POL-02."

    def test_reject_without_comment_raises_400(self, db_session: Session) -> None:
        from src.errors import AppError
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        with pytest.raises(AppError) as exc:
            service.reject(
                item_id="M-002",
                item_type="module",
                original_result=_sample_original_result("M-002"),
                reviewer=reviewer,
                comment=None,
            )
        assert exc.value.status_code == 400

    def test_reject_preserves_original_result(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        original = _sample_original_result("M-002")
        decision = service.reject(
            item_id="M-002",
            item_type="module",
            original_result=original,
            reviewer=reviewer,
            comment="Bad.",
        )
        assert decision.original_result == original

    def test_reject_sets_reviewer_override(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        decision = service.reject(
            item_id="M-002",
            item_type="module",
            original_result=_sample_original_result("M-002"),
            reviewer=reviewer,
            comment="Needs fix.",
        )
        assert decision.reviewer_override is not None
        assert decision.reviewer_override.get("rejected") is True

    def test_reject_audit_entry_is_warning(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        service.reject(
            item_id="M-002",
            item_type="module",
            original_result=_sample_original_result("M-002"),
            reviewer=reviewer,
            comment="Source not found.",
        )
        entries = (
            db_session.query(AuditEntry)
            .filter(AuditEntry.entity_id == "M-002")
            .all()
        )
        assert entries[0].log_level == "WARNING"

    def test_reject_api_missing_comment_returns_400(self, client_with_db) -> None:
        client, reviewer_token, _, _ = client_with_db
        resp = client.post(
            "/api/reviews/M-002/reject",
            headers={"Authorization": f"Bearer {reviewer_token}"},
            json={
                "item_type": "module",
                "original_result": _sample_original_result("M-002"),
            },
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 5. Edit
# ---------------------------------------------------------------------------

class TestEdit:
    """Edit stores original unchanged AND reviewer content in reviewer_override."""

    def test_edit_preserves_original_result(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        original = _sample_original_result("T-001", "task")
        decision = service.edit(
            item_id="T-001",
            item_type="task",
            original_result=original,
            edited_content={"description": "Revised task description."},
            reviewer=reviewer,
            comment="Updated to match SOP-03.",
        )
        assert decision.original_result == original

    def test_edit_stores_reviewer_content_in_override(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        edited = {"description": "Revised task description."}
        decision = service.edit(
            item_id="T-001",
            item_type="task",
            original_result=_sample_original_result("T-001", "task"),
            edited_content=edited,
            reviewer=reviewer,
        )
        assert decision.reviewer_override is not None
        assert decision.reviewer_override["edited"] is True
        assert decision.reviewer_override["content"] == edited

    def test_edit_empty_content_raises_400(self, db_session: Session) -> None:
        from src.errors import AppError
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        with pytest.raises(AppError) as exc:
            service.edit(
                item_id="T-001",
                item_type="task",
                original_result=_sample_original_result("T-001", "task"),
                edited_content={},
                reviewer=reviewer,
            )
        assert exc.value.status_code == 400

    def test_edit_creates_audit_entry(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        service.edit(
            item_id="T-001",
            item_type="task",
            original_result=_sample_original_result("T-001", "task"),
            edited_content={"description": "fixed"},
            reviewer=reviewer,
        )
        entries = (
            db_session.query(AuditEntry)
            .filter(AuditEntry.entity_id == "T-001")
            .all()
        )
        assert len(entries) == 1
        assert entries[0].action == "review_edited"

    def test_edit_api(self, client_with_db) -> None:
        client, reviewer_token, _, _ = client_with_db
        resp = client.post(
            "/api/reviews/T-001/edit",
            headers={"Authorization": f"Bearer {reviewer_token}"},
            json={
                "item_type": "task",
                "original_result": _sample_original_result("T-001", "task"),
                "edited_content": {"description": "Corrected."},
                "comment": "Aligned with SOP-02.",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "edit"
        # original_result preserved
        assert data["original_result"]["item_id"] == "T-001"
        # reviewer_override carries the edit
        assert data["reviewer_override"]["edited"] is True


# ---------------------------------------------------------------------------
# 6. Regenerate
# ---------------------------------------------------------------------------

class TestRegenerate:
    """Regenerate records a request; does NOT call GenAI; preserves original."""

    def test_regenerate_action_is_recorded(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        decision = service.regenerate(
            item_id="Q-001",
            item_type="quiz_question",
            original_result=_sample_original_result("Q-001", "quiz_question"),
            reviewer=reviewer,
            comment="Source missing.",
        )
        assert decision.action == "regenerate"

    def test_regenerate_preserves_original_result(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        original = _sample_original_result("Q-001", "quiz_question")
        decision = service.regenerate(
            item_id="Q-001",
            item_type="quiz_question",
            original_result=original,
            reviewer=reviewer,
        )
        assert decision.original_result == original

    def test_regenerate_override_contains_flag(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        decision = service.regenerate(
            item_id="Q-001",
            item_type="quiz_question",
            original_result=_sample_original_result("Q-001", "quiz_question"),
            reviewer=reviewer,
        )
        assert decision.reviewer_override is not None
        assert decision.reviewer_override.get("regeneration_requested") is True

    def test_regenerate_creates_audit_entry(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        service.regenerate(
            item_id="Q-001",
            item_type="quiz_question",
            original_result=_sample_original_result("Q-001", "quiz_question"),
            reviewer=reviewer,
        )
        entries = (
            db_session.query(AuditEntry)
            .filter(AuditEntry.entity_id == "Q-001")
            .all()
        )
        assert len(entries) == 1
        assert entries[0].action == "review_regenerate_requested"

    def test_regenerate_api(self, client_with_db) -> None:
        client, reviewer_token, _, _ = client_with_db
        resp = client.post(
            "/api/reviews/Q-001/regenerate",
            headers={"Authorization": f"Bearer {reviewer_token}"},
            json={
                "item_type": "quiz_question",
                "original_result": _sample_original_result("Q-001", "quiz_question"),
                "comment": "Please regenerate.",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "regenerate"
        assert data["reviewer_override"]["regeneration_requested"] is True


# ---------------------------------------------------------------------------
# 7. Unauthorized access
# ---------------------------------------------------------------------------

class TestUnauthorized:
    """Employee role must not perform review write actions."""

    def test_employee_cannot_approve(self, client_with_db) -> None:
        client, _, employee_token, _ = client_with_db
        resp = client.post(
            "/api/reviews/M-001/approve",
            headers={"Authorization": f"Bearer {employee_token}"},
            json={
                "item_type": "module",
                "original_result": _sample_original_result(),
            },
        )
        assert resp.status_code == 403

    def test_employee_cannot_reject(self, client_with_db) -> None:
        client, _, employee_token, _ = client_with_db
        resp = client.post(
            "/api/reviews/M-001/reject",
            headers={"Authorization": f"Bearer {employee_token}"},
            json={
                "item_type": "module",
                "original_result": _sample_original_result(),
                "comment": "Rejected.",
            },
        )
        assert resp.status_code == 403

    def test_employee_cannot_edit(self, client_with_db) -> None:
        client, _, employee_token, _ = client_with_db
        resp = client.post(
            "/api/reviews/M-001/edit",
            headers={"Authorization": f"Bearer {employee_token}"},
            json={
                "item_type": "module",
                "original_result": _sample_original_result(),
                "edited_content": {"title": "x"},
            },
        )
        assert resp.status_code == 403

    def test_unauthenticated_cannot_access_queue(self, client_with_db) -> None:
        client, _, _, _ = client_with_db
        resp = client.get("/api/reviews/queue")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 8. Audit entry creation (one per action)
# ---------------------------------------------------------------------------

class TestAuditEntryCreation:
    """Every review action generates exactly one AuditEntry."""

    def test_one_audit_entry_per_approve(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        service.approve("X-001", "module", _sample_original_result("X-001"), reviewer)
        count = db_session.query(AuditEntry).filter(AuditEntry.entity_id == "X-001").count()
        assert count == 1

    def test_multiple_actions_produce_multiple_entries(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        original = _sample_original_result("X-002")
        service.add_comment("X-002", "module", original, reviewer, "first note")
        service.edit("X-002", "module", original, {"title": "edited"}, reviewer, "fixed")
        service.approve("X-002", "module", original, reviewer)
        count = db_session.query(AuditEntry).filter(AuditEntry.entity_id == "X-002").count()
        assert count == 3


# ---------------------------------------------------------------------------
# 9 & 10. original_result and reviewer_override coexistence — VG-4.2
# ---------------------------------------------------------------------------

class TestOriginalResultPreservation:
    """VG-4.2: both original_result and reviewer_override must exist on the same row."""

    def test_edit_has_both_original_and_override(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        original = {"item_id": "M-010", "verification_status": "Contradiction Detected"}
        edited = {"title": "Corrected module title"}
        decision = service.edit("M-010", "module", original, edited, reviewer, "fixed")

        assert decision.original_result == original, "original_result must not be mutated"
        assert decision.reviewer_override is not None, "reviewer_override must be present"
        assert decision.reviewer_override["content"] == edited

    def test_reject_has_both_original_and_override(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        original = {"item_id": "M-011", "verification_status": "Source Support Missing"}
        decision = service.reject("M-011", "module", original, reviewer, "Bad source.")

        assert decision.original_result == original
        assert decision.reviewer_override is not None
        assert decision.reviewer_override["rejected"] is True

    def test_approve_has_original_and_no_override(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        original = {"item_id": "M-012", "verification_status": "Manual Review Required"}
        decision = service.approve("M-012", "module", original, reviewer)

        assert decision.original_result == original
        assert decision.reviewer_override is None  # Approve = no change


# ---------------------------------------------------------------------------
# 11. Audit trail details contain both original_result and reviewer_override
# ---------------------------------------------------------------------------

class TestAuditTrailCompleteness:
    """Audit entries must capture the full review context in their details JSON."""

    def test_audit_details_contain_original_result(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        original = _sample_original_result("Z-001")
        service.approve("Z-001", "module", original, reviewer, "Good.")
        entry = (
            db_session.query(AuditEntry)
            .filter(AuditEntry.entity_id == "Z-001")
            .first()
        )
        assert entry is not None
        assert "original_result" in entry.details
        assert entry.details["original_result"] == original

    def test_audit_details_contain_reviewer_override(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        original = _sample_original_result("Z-002")
        edited = {"title": "Fixed"}
        service.edit("Z-002", "module", original, edited, reviewer)
        entry = (
            db_session.query(AuditEntry)
            .filter(AuditEntry.entity_id == "Z-002")
            .first()
        )
        assert entry is not None
        assert "reviewer_override" in entry.details
        assert entry.details["reviewer_override"]["content"] == edited

    def test_reject_audit_contains_both(self, db_session: Session) -> None:
        reviewer = _reviewer_user(db_session)
        service = ReviewService(db_session)
        original = _sample_original_result("Z-003")
        service.reject("Z-003", "module", original, reviewer, "Not supported.")
        entry = (
            db_session.query(AuditEntry)
            .filter(AuditEntry.entity_id == "Z-003")
            .first()
        )
        assert entry.details["original_result"] == original
        assert entry.details["reviewer_override"]["rejected"] is True

    def test_audit_trail_api_endpoint(self, client_with_db) -> None:
        client, reviewer_token, _, db = client_with_db
        # Perform an action first
        client.post(
            "/api/reviews/Z-API/approve",
            headers={"Authorization": f"Bearer {reviewer_token}"},
            json={
                "item_type": "module",
                "original_result": _sample_original_result("Z-API"),
                "comment": "OK",
            },
        )
        # Fetch the audit trail
        resp = client.get(
            "/api/reviews/Z-API/audit",
            headers={"Authorization": f"Bearer {reviewer_token}"},
        )
        assert resp.status_code == 200
        trail = resp.json()
        assert len(trail) == 1
        assert trail[0]["action"] == "review_approved"
        assert trail[0]["details"]["original_result"] is not None


# ---------------------------------------------------------------------------
# 12. Decision history endpoint
# ---------------------------------------------------------------------------

class TestDecisionHistory:
    """GET /api/reviews/{item_id}/decisions returns complete history."""

    def test_decisions_endpoint_returns_all_history(self, client_with_db) -> None:
        client, reviewer_token, _, _ = client_with_db
        original = _sample_original_result("H-001")
        # Add comment then approve
        client.post(
            "/api/reviews/H-001/comment",
            headers={"Authorization": f"Bearer {reviewer_token}"},
            json={"item_type": "module", "original_result": original, "comment": "Note 1."},
        )
        client.post(
            "/api/reviews/H-001/approve",
            headers={"Authorization": f"Bearer {reviewer_token}"},
            json={"item_type": "module", "original_result": original, "comment": "Approved."},
        )
        resp = client.get(
            "/api/reviews/H-001/decisions",
            headers={"Authorization": f"Bearer {reviewer_token}"},
        )
        assert resp.status_code == 200
        decisions = resp.json()
        assert len(decisions) == 2
        actions = [d["action"] for d in decisions]
        assert "approve" in actions
        assert "comment" in actions

    def test_each_decision_has_original_result(self, client_with_db) -> None:
        client, reviewer_token, _, _ = client_with_db
        original = _sample_original_result("H-002")
        client.post(
            "/api/reviews/H-002/reject",
            headers={"Authorization": f"Bearer {reviewer_token}"},
            json={"item_type": "module", "original_result": original, "comment": "Bad."},
        )
        resp = client.get(
            "/api/reviews/H-002/decisions",
            headers={"Authorization": f"Bearer {reviewer_token}"},
        )
        decisions = resp.json()
        for d in decisions:
            assert d["original_result"] is not None
