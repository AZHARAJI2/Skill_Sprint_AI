"""HTTP API for the human review workflow — Phase 4, Tasks 48 & 49.

Endpoints
---------
GET  /api/reviews/queue                — list items pending human review
GET  /api/reviews/queue/{plan_id}      — list pending items for one plan
POST /api/reviews/{item_id}/approve    — approve an item
POST /api/reviews/{item_id}/reject     — reject an item (comment required)
POST /api/reviews/{item_id}/edit       — supply an edited/corrected version
POST /api/reviews/{item_id}/regenerate — request regeneration of the item
POST /api/reviews/{item_id}/comment    — add a comment without changing status
GET  /api/reviews/{item_id}/decisions  — full decision history for one item
GET  /api/reviews/{item_id}/audit      — full audit trail for one item

RBAC
----
Review queue (read) : Admin, Training Manager, Reviewer, Manager
Review actions (write): Admin, Training Manager, Reviewer
Admin always passes all role checks (see require_role in auth/dependencies.py).
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from database.base import get_session
from src.auth.dependencies import get_current_user, require_role
from src.auth.models import User
from src.reviews.service import ReviewService

router = APIRouter(prefix="/api/reviews", tags=["reviews"])

# Roles that may perform write actions (approve / reject / edit / regenerate)
_REVIEWER_ROLES = ("Admin", "Training Manager", "Reviewer")
# Roles that may read the queue
_QUEUE_READER_ROLES = ("Admin", "Training Manager", "Reviewer", "Manager")


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------


@router.get("/queue", summary="List all items pending human review")
def get_queue(
    session: Session = Depends(get_session),
    user: User = Depends(require_role(*_QUEUE_READER_ROLES)),
) -> list[dict]:
    """Return every item whose verification status requires human review.

    Items that have already been approved or rejected are excluded from the
    active queue.  Items with no decision yet, or with an edit/regenerate
    or comment decision, remain in the queue until approved or rejected.
    """
    service = ReviewService(session)
    return [item.to_dict() for item in service.get_queue()]


@router.get("/queue/{plan_id}", summary="List pending review items for one plan")
def get_queue_for_plan(
    plan_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_role(*_QUEUE_READER_ROLES)),
) -> list[dict]:
    """Return pending review items scoped to a single onboarding plan."""
    service = ReviewService(session)
    return [item.to_dict() for item in service.get_queue(plan_id=plan_id)]


# ---------------------------------------------------------------------------
# Approve
# ---------------------------------------------------------------------------


@router.post("/{item_id}/approve", summary="Approve a validated item")
def approve_item(
    item_id: str,
    body: dict = Body(
        ...,
        example={
            "item_type": "module",
            "original_result": {"item_id": "M-001", "verification_status": "Manual Review Required"},
            "comment": "Content is accurate and source-grounded.",
        },
    ),
    session: Session = Depends(get_session),
    user: User = Depends(require_role(*_REVIEWER_ROLES)),
) -> dict:
    """Approve the item as-is.

    The original Pipeline 2 result is preserved in ReviewDecision.original_result.
    No reviewer_override is set (approve = no content change).
    An AuditEntry is created recording who approved, when, and the full context.

    Request body fields:
        item_type (str): Type of the item (e.g. "module", "task", "quiz_question").
        original_result (dict): The Pipeline 2 ItemValidationResult payload.
        comment (str, optional): Optional approval note.
    """
    service = ReviewService(session)
    decision = service.approve(
        item_id=item_id,
        item_type=body.get("item_type", "unknown"),
        original_result=body.get("original_result", {}),
        reviewer=user,
        comment=body.get("comment"),
        plan_id=_plan_id_from_body(body),
    )
    return _decision_payload(decision)


# ---------------------------------------------------------------------------
# Reject
# ---------------------------------------------------------------------------


@router.post("/{item_id}/reject", summary="Reject a validated item")
def reject_item(
    item_id: str,
    body: dict = Body(
        ...,
        example={
            "item_type": "task",
            "original_result": {"item_id": "T-003", "verification_status": "Contradiction Detected"},
            "comment": "Contradicts POL-02 v2 §3.1. Requires rewrite.",
        },
    ),
    session: Session = Depends(get_session),
    user: User = Depends(require_role(*_REVIEWER_ROLES)),
) -> dict:
    """Reject the item.

    A rejection reason (comment) is mandatory — the service raises HTTP 400
    if the comment is absent or blank.

    The original Pipeline 2 result is preserved in ReviewDecision.original_result.
    reviewer_override is set to ``{"rejected": True, "reason": <comment>}``.
    An AuditEntry is created at WARNING log level.

    Request body fields:
        item_type (str): Type of the item.
        original_result (dict): The Pipeline 2 ItemValidationResult payload.
        comment (str): Required rejection reason.
    """
    service = ReviewService(session)
    decision = service.reject(
        item_id=item_id,
        item_type=body.get("item_type", "unknown"),
        original_result=body.get("original_result", {}),
        reviewer=user,
        comment=body.get("comment"),
        plan_id=_plan_id_from_body(body),
    )
    return _decision_payload(decision)


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


@router.post("/{item_id}/edit", summary="Supply a reviewer-edited version of an item")
def edit_item(
    item_id: str,
    body: dict = Body(
        ...,
        example={
            "item_type": "module",
            "original_result": {"item_id": "M-007", "verification_status": "Source Support Missing"},
            "edited_content": {"title": "Updated Module Title", "objectives": ["Corrected objective 1"]},
            "comment": "Updated to align with SOP-03 §2.",
        },
    ),
    session: Session = Depends(get_session),
    user: User = Depends(require_role(*_REVIEWER_ROLES)),
) -> dict:
    """Reviewer supplies an edited/corrected version of the item.

    original_result is stored UNCHANGED.
    reviewer_override contains ``{"edited": True, "content": <edited_content>}``.
    The item remains in the queue (not approved/rejected) until a separate
    approve/reject action is taken on the edited version.

    Request body fields:
        item_type (str): Type of the item.
        original_result (dict): The Pipeline 2 ItemValidationResult payload.
        edited_content (dict): The reviewer's replacement content.
        comment (str, optional): Note explaining what was changed.
    """
    service = ReviewService(session)
    decision = service.edit(
        item_id=item_id,
        item_type=body.get("item_type", "unknown"),
        original_result=body.get("original_result", {}),
        edited_content=body.get("edited_content", {}),
        reviewer=user,
        comment=body.get("comment"),
        plan_id=_plan_id_from_body(body),
    )
    return _decision_payload(decision)


# ---------------------------------------------------------------------------
# Regenerate
# ---------------------------------------------------------------------------


@router.post("/{item_id}/regenerate", summary="Request regeneration of an item")
def regenerate_item(
    item_id: str,
    body: dict = Body(
        ...,
        example={
            "item_type": "quiz_question",
            "original_result": {"item_id": "Q-012", "verification_status": "Unsupported Requirement"},
            "comment": "Source not found. Please regenerate with updated document corpus.",
        },
    ),
    session: Session = Depends(get_session),
    user: User = Depends(require_role(*_REVIEWER_ROLES)),
) -> dict:
    """Request that the item be regenerated through Pipeline 1.

    This endpoint records a regeneration REQUEST only.  It does NOT invoke the
    GenAI pipeline.  The actual regeneration must be triggered via
    POST /api/plans/generate/{employee_id} after the item's plan is updated.

    original_result is preserved in ReviewDecision.original_result.
    reviewer_override is set to ``{"regeneration_requested": True, "requested_by": <username>}``.
    The item re-enters the review queue under action='regenerate' until a
    new validation run produces a final approve/reject decision.

    Request body fields:
        item_type (str): Type of the item.
        original_result (dict): The Pipeline 2 ItemValidationResult payload.
        comment (str, optional): Note explaining why regeneration is needed.
    """
    service = ReviewService(session)
    decision = service.regenerate(
        item_id=item_id,
        item_type=body.get("item_type", "unknown"),
        original_result=body.get("original_result", {}),
        reviewer=user,
        comment=body.get("comment"),
        plan_id=_plan_id_from_body(body),
    )
    return _decision_payload(decision)


# ---------------------------------------------------------------------------
# Add comment
# ---------------------------------------------------------------------------


@router.post("/{item_id}/comment", summary="Add a comment without changing review status")
def add_comment(
    item_id: str,
    body: dict = Body(
        ...,
        example={
            "item_type": "checklist",
            "original_result": {"item_id": "CL-005", "verification_status": "Partially Verified"},
            "comment": "Discuss with the legal team before final decision.",
        },
    ),
    session: Session = Depends(get_session),
    user: User = Depends(require_role(*_REVIEWER_ROLES)),
) -> dict:
    """Add a comment to an item without changing its approval status.

    original_result is preserved.  reviewer_override is None (no content change).
    The item remains in the queue.

    Request body fields:
        item_type (str): Type of the item.
        original_result (dict): The Pipeline 2 ItemValidationResult payload.
        comment (str): Required comment text.
    """
    service = ReviewService(session)
    decision = service.add_comment(
        item_id=item_id,
        item_type=body.get("item_type", "unknown"),
        original_result=body.get("original_result", {}),
        reviewer=user,
        comment=body.get("comment", ""),
        plan_id=_plan_id_from_body(body),
    )
    return _decision_payload(decision)


# ---------------------------------------------------------------------------
# Decision and audit history
# ---------------------------------------------------------------------------


@router.get("/{item_id}/decisions", summary="Full decision history for an item")
def get_decisions(
    item_id: str,
    plan_id: int | None = Query(default=None, gt=0),
    session: Session = Depends(get_session),
    user: User = Depends(require_role(*_QUEUE_READER_ROLES)),
) -> list[dict]:
    """Return every ReviewDecision row for this item, newest first.

    Each row contains both ``original_result`` (Pipeline 2 evidence, immutable)
    and ``reviewer_override`` (reviewer's change or None), satisfying VG-4.2.
    """
    service = ReviewService(session)
    decisions = service.get_review_decisions(item_id, plan_id=plan_id)
    return [_decision_payload(d) for d in decisions]


@router.get("/{item_id}/audit", summary="Full audit trail for an item")
def get_audit_trail(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_role(*_QUEUE_READER_ROLES)),
) -> list[dict]:
    """Return every AuditEntry for this item, oldest first (immutable log).

    Each entry records actor, action, timestamp, original_result, and
    reviewer_override, enabling full reconstruction of the review history.
    """
    service = ReviewService(session)
    entries = service.get_audit_trail(item_id)
    return [_audit_payload(e) for e in entries]


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _decision_payload(decision) -> dict:
    """Serialize a ReviewDecision ORM row to a plain dict."""
    return {
        "id": decision.id,
        "item_id": decision.item_id,
        "item_type": decision.item_type,
        "plan_id": decision.plan_id,
        "reviewer_id": decision.reviewer_id,
        "action": decision.action,
        "comment": decision.comment,
        "original_result": decision.original_result,
        "reviewer_override": decision.reviewer_override,
        "timestamp": decision.timestamp.isoformat() if decision.timestamp else None,
    }


def _plan_id_from_body(body: dict) -> int | None:
    """Read an optional positive plan scope supplied by the review UI."""
    value = body.get("plan_id")
    if value is None:
        return None
    if isinstance(value, bool):
        from src.errors import AppError

        raise AppError("plan_id must be a positive integer.", status_code=422)
    try:
        plan_id = int(value)
    except (TypeError, ValueError) as exc:
        from src.errors import AppError

        raise AppError("plan_id must be a positive integer.", status_code=422) from exc
    if plan_id <= 0:
        from src.errors import AppError

        raise AppError("plan_id must be a positive integer.", status_code=422)
    return plan_id


def _audit_payload(entry) -> dict:
    """Serialize an AuditEntry ORM row to a plain dict."""
    return {
        "id": entry.id,
        "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
        "actor": entry.actor,
        "action": entry.action,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "details": entry.details,
        "log_level": entry.log_level,
    }
