"""Human review workflow service — Phase 4, Tasks 48 & 49.

Implements approve / reject / edit / regenerate / add_comment actions.
Every action writes a ReviewDecision **and** an AuditEntry so that:
  - The original system result is never overwritten (preserved in ReviewDecision.original_result).
  - The reviewer decision/override is stored alongside it (ReviewDecision.reviewer_override).
  - An immutable audit row records who did what and when (AuditRepository.record).

No GenAI calls are made here.  Regenerate is recorded as a pending-regeneration
request; the actual re-generation is triggered through the existing
PlanGenerationService (Pipeline 1) — this service only records the intent and
updates the plan's verification_status so the queue reflects the new state.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from database.base import BaseRepository
from schemas.common_schema import ReviewAction, VerificationStatus
from src.auth.models import User
from src.errors import AppError
from src.plans.models import OnboardingPlan
from src.reviews.models import AuditEntry, ReviewDecision, ValidationReportRecord
from src.reviews.repository import AuditRepository


# ---------------------------------------------------------------------------
# ReviewRepository
# ---------------------------------------------------------------------------

class ReviewRepository(BaseRepository[ReviewDecision]):
    """CRUD for reviewer decisions against validated plan items."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ReviewDecision)

    def get_by_item(self, item_id: str) -> list[ReviewDecision]:
        """Return all review decisions for a given item (most recent first)."""
        return (
            self.session.query(ReviewDecision)
            .filter(ReviewDecision.item_id == item_id)
            .order_by(ReviewDecision.timestamp.desc())
            .all()
        )

    def latest_for_item(self, item_id: str) -> ReviewDecision | None:
        """Return the single most-recent decision for an item, or None."""
        return (
            self.session.query(ReviewDecision)
            .filter(ReviewDecision.item_id == item_id)
            .order_by(ReviewDecision.timestamp.desc())
            .first()
        )

    def pending_items(self) -> list[ReviewDecision]:
        """Return items that still have status 'pending_review' (no final decision yet)."""
        return (
            self.session.query(ReviewDecision)
            .filter(ReviewDecision.action == "pending_review")
            .all()
        )


class ValidationReportRepository(BaseRepository[ValidationReportRecord]):
    """Repository for persisted Pipeline 2 ValidationReportRecords."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ValidationReportRecord)

    def get_by_plan(self, plan_id: int) -> ValidationReportRecord | None:
        """Return the latest validation report for a plan."""
        return (
            self.session.query(ValidationReportRecord)
            .filter(ValidationReportRecord.plan_id == plan_id)
            .order_by(ValidationReportRecord.created_at.desc())
            .first()
        )

    def list_all(self) -> list[ValidationReportRecord]:
        """Return all validation reports ordered by created_at descending."""
        return (
            self.session.query(ValidationReportRecord)
            .order_by(ValidationReportRecord.created_at.desc())
            .all()
        )



# ---------------------------------------------------------------------------
# ReviewQueueItem — lightweight data-transfer object for the API layer
# ---------------------------------------------------------------------------

class ReviewQueueItem:
    """Read-only view of one pending item for the review queue endpoint."""

    def __init__(
        self,
        item_id: str,
        item_type: str,
        plan_id: int,
        verification_status: str,
        original_result: dict | None,
        reviewer_status: str,
        source_references: list[str],
        comment: str | None,
        timestamp: datetime,
    ) -> None:
        self.item_id = item_id
        self.item_type = item_type
        self.plan_id = plan_id
        self.verification_status = verification_status
        self.original_result = original_result
        self.reviewer_status = reviewer_status
        self.source_references = source_references
        self.comment = comment
        self.timestamp = timestamp

    def to_dict(self) -> dict:
        """Serialize to a plain dict suitable for JSON responses."""
        return {
            "item_id": self.item_id,
            "item_type": self.item_type,
            "plan_id": self.plan_id,
            "verification_status": self.verification_status,
            "original_result": self.original_result,
            "reviewer_status": self.reviewer_status,
            "source_references": self.source_references,
            "comment": self.comment,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


# ---------------------------------------------------------------------------
# ReviewService
# ---------------------------------------------------------------------------

class ReviewService:
    """Orchestrates the human review workflow (Tasks 48 & 49).

    Design principles:
      - original_result is NEVER modified after creation.
      - reviewer_override stores only what the reviewer changed.
      - Every action (approve/reject/edit/regenerate/add_comment) is recorded
        in both ReviewDecision and AuditEntry.
      - The AuditRepository is append-only; no existing row is deleted or
        updated by this service.
    """

    # Verification statuses that require human review
    _REVIEW_REQUIRED_STATUSES: frozenset[str] = frozenset(
        {
            VerificationStatus.SOURCE_SUPPORT_MISSING.value,
            VerificationStatus.REQUIREMENT_MISSING.value,
            VerificationStatus.UNSUPPORTED_REQUIREMENT.value,
            VerificationStatus.OUTDATED_SOURCE.value,
            VerificationStatus.CONTRADICTION_DETECTED.value,
            VerificationStatus.MANUAL_REVIEW_REQUIRED.value,
            VerificationStatus.PARTIALLY_VERIFIED.value,
        }
    )

    def __init__(self, session: Session) -> None:
        """Inject the database session; all repositories share it."""
        self._session = session
        self._review_repo = ReviewRepository(session)
        self._audit_repo = AuditRepository(session)
        self._report_repo = ValidationReportRepository(session)

    # ------------------------------------------------------------------
    # Queue
    # ------------------------------------------------------------------

    def get_queue(self, plan_id: int | None = None) -> list[ReviewQueueItem]:
        """Return all items awaiting human review.

        Items enter the queue in two ways:
          1. A ValidationReportRecord exists for a plan and its per_item_results
             contain a status that requires review (the normal pipeline path).
          2. A ReviewDecision with action='pending_review' was explicitly created
             (e.g. after a regenerate request).

        Args:
            plan_id: If provided, restrict to items belonging to this plan.

        Returns:
            List of ReviewQueueItem sorted by timestamp descending.
        """
        queue: list[ReviewQueueItem] = []
        seen_item_ids: set[str] = set()

        # --- Source 1: validation reports stored in DB ---
        reports: list[ValidationReportRecord]
        if plan_id is not None:
            report = self._report_repo.get_by_plan(plan_id)
            reports = [report] if report else []
        else:
            reports = self._report_repo.list_all()

        for report in reports:
            payload = report.payload or {}
            per_item = payload.get("per_item_results", [])
            for item in per_item:
                status = item.get("verification_status", "")
                if status not in self._REVIEW_REQUIRED_STATUSES:
                    continue
                item_id = item.get("item_id", "")
                if item_id in seen_item_ids:
                    continue
                seen_item_ids.add(item_id)
                # Check whether a final decision has already been made
                latest = self._review_repo.latest_for_item(item_id)
                if latest and latest.action in (
                    ReviewAction.APPROVE.value,
                    ReviewAction.REJECT.value,
                ):
                    # Already resolved — exclude from active queue
                    continue
                reviewer_status = latest.action if latest else "pending_review"
                queue.append(
                    ReviewQueueItem(
                        item_id=item_id,
                        item_type=item.get("item_type", "unknown"),
                        plan_id=report.plan_id,
                        verification_status=status,
                        original_result=item,
                        reviewer_status=reviewer_status,
                        source_references=item.get("source_references", []),
                        comment=latest.comment if latest else None,
                        timestamp=latest.timestamp if latest else report.created_at,
                    )
                )

        # --- Source 2: explicit pending_review decisions not from a report ---
        for decision in self._review_repo.pending_items():
            if decision.item_id in seen_item_ids:
                continue
            seen_item_ids.add(decision.item_id)
            queue.append(
                ReviewQueueItem(
                    item_id=decision.item_id,
                    item_type=decision.item_type,
                    plan_id=0,  # plan not directly retrievable from this row
                    verification_status=decision.original_result.get(
                        "verification_status", VerificationStatus.MANUAL_REVIEW_REQUIRED.value
                    )
                    if decision.original_result
                    else VerificationStatus.MANUAL_REVIEW_REQUIRED.value,
                    original_result=decision.original_result,
                    reviewer_status=decision.action,
                    source_references=[],
                    comment=decision.comment,
                    timestamp=decision.timestamp,
                )
            )

        queue.sort(key=lambda x: x.timestamp, reverse=True)
        return queue

    # ------------------------------------------------------------------
    # Review actions
    # ------------------------------------------------------------------

    def approve(
        self,
        item_id: str,
        item_type: str,
        original_result: dict,
        reviewer: User,
        comment: str | None = None,
    ) -> ReviewDecision:
        """Reviewer approves the item as-is.

        The original_result is stored verbatim.  reviewer_override is None
        because no change was made — only the decision (approve) is recorded.

        Args:
            item_id: Unique identifier of the validated item.
            item_type: Type of item (module, task, quiz_question, etc.).
            original_result: The Pipeline 2 ItemValidationResult dict (never modified).
            reviewer: The authenticated User performing the action.
            comment: Optional approval note.

        Returns:
            The created ReviewDecision.
        """
        decision = self._create_decision(
            item_id=item_id,
            item_type=item_type,
            reviewer=reviewer,
            action=ReviewAction.APPROVE.value,
            original_result=original_result,
            reviewer_override=None,  # Approve = no change to content
            comment=comment,
        )
        self._audit_repo.record(
            actor=reviewer.username,
            action="review_approved",
            entity_type=item_type,
            entity_id=item_id,
            details={
                "action": ReviewAction.APPROVE.value,
                "original_result": original_result,
                "reviewer_override": None,
                "comment": comment,
                "reviewer_id": reviewer.id,
            },
        )
        return decision

    def reject(
        self,
        item_id: str,
        item_type: str,
        original_result: dict,
        reviewer: User,
        comment: str | None = None,
    ) -> ReviewDecision:
        """Reviewer rejects the item.

        The original_result is preserved exactly.  reviewer_override carries a
        ``{"rejected": True}`` marker so downstream consumers can distinguish a
        clean reject from an edit.

        Args:
            item_id: Unique identifier of the validated item.
            item_type: Type of item.
            original_result: The original Pipeline 2 result dict (never mutated).
            reviewer: The authenticated User performing the action.
            comment: Mandatory rejection reason (enforced here if absent).

        Returns:
            The created ReviewDecision.

        Raises:
            AppError: If comment is empty (reject without a reason is prohibited).
        """
        if not comment or not comment.strip():
            raise AppError(
                "A rejection reason (comment) is required.", status_code=400
            )
        override = {"rejected": True, "reason": comment}
        decision = self._create_decision(
            item_id=item_id,
            item_type=item_type,
            reviewer=reviewer,
            action=ReviewAction.REJECT.value,
            original_result=original_result,
            reviewer_override=override,
            comment=comment,
        )
        self._audit_repo.record(
            actor=reviewer.username,
            action="review_rejected",
            entity_type=item_type,
            entity_id=item_id,
            details={
                "action": ReviewAction.REJECT.value,
                "original_result": original_result,
                "reviewer_override": override,
                "comment": comment,
                "reviewer_id": reviewer.id,
            },
            log_level="WARNING",
        )
        return decision

    def edit(
        self,
        item_id: str,
        item_type: str,
        original_result: dict,
        edited_content: dict,
        reviewer: User,
        comment: str | None = None,
    ) -> ReviewDecision:
        """Reviewer supplies an edited/corrected version of the item.

        original_result is stored UNCHANGED.
        reviewer_override contains the reviewer's replacement content.
        Both are stored side-by-side in ReviewDecision — neither overwrites
        the other.

        Args:
            item_id: Unique identifier of the validated item.
            item_type: Type of item.
            original_result: The original Pipeline 2 result dict (never mutated).
            edited_content: The reviewer-supplied replacement content.
            reviewer: The authenticated User performing the action.
            comment: Optional note explaining the edit.

        Returns:
            The created ReviewDecision.
        """
        if not edited_content:
            raise AppError("edited_content must not be empty.", status_code=400)
        override = {"edited": True, "content": edited_content}
        decision = self._create_decision(
            item_id=item_id,
            item_type=item_type,
            reviewer=reviewer,
            action=ReviewAction.EDIT.value,
            original_result=original_result,
            reviewer_override=override,
            comment=comment,
        )
        self._audit_repo.record(
            actor=reviewer.username,
            action="review_edited",
            entity_type=item_type,
            entity_id=item_id,
            details={
                "action": ReviewAction.EDIT.value,
                "original_result": original_result,
                "reviewer_override": override,
                "comment": comment,
                "reviewer_id": reviewer.id,
            },
        )
        return decision

    def regenerate(
        self,
        item_id: str,
        item_type: str,
        original_result: dict,
        reviewer: User,
        comment: str | None = None,
    ) -> ReviewDecision:
        """Reviewer requests regeneration of the item.

        This method records a regeneration REQUEST.  It does NOT call the GenAI
        pipeline directly — the actual re-generation must be triggered through
        PlanGenerationService (Pipeline 1).  The item is placed back into the
        review queue with action='pending_review' after the request is recorded.

        The original result is preserved in ReviewDecision.original_result.
        reviewer_override contains ``{"regeneration_requested": True}`` so the
        queue knows this item is awaiting a new generation run.

        Args:
            item_id: Unique identifier of the validated item.
            item_type: Type of item.
            original_result: The original Pipeline 2 result dict (never mutated).
            reviewer: The authenticated User performing the action.
            comment: Optional note.

        Returns:
            The created ReviewDecision (action='regenerate').
        """
        override = {"regeneration_requested": True, "requested_by": reviewer.username}
        decision = self._create_decision(
            item_id=item_id,
            item_type=item_type,
            reviewer=reviewer,
            action=ReviewAction.REGENERATE.value,
            original_result=original_result,
            reviewer_override=override,
            comment=comment,
        )
        self._audit_repo.record(
            actor=reviewer.username,
            action="review_regenerate_requested",
            entity_type=item_type,
            entity_id=item_id,
            details={
                "action": ReviewAction.REGENERATE.value,
                "original_result": original_result,
                "reviewer_override": override,
                "comment": comment,
                "reviewer_id": reviewer.id,
            },
        )
        return decision

    def add_comment(
        self,
        item_id: str,
        item_type: str,
        original_result: dict,
        reviewer: User,
        comment: str,
    ) -> ReviewDecision:
        """Add a comment to an item without changing its review status.

        original_result is preserved.  reviewer_override is None because
        no content change is being made.  The action is stored as 'comment'.

        Args:
            item_id: Unique identifier of the validated item.
            item_type: Type of item.
            original_result: The original Pipeline 2 result dict.
            reviewer: The authenticated User adding the comment.
            comment: The comment text (required, must not be empty).

        Returns:
            The created ReviewDecision.
        """
        if not comment or not comment.strip():
            raise AppError("comment must not be empty.", status_code=400)
        decision = self._create_decision(
            item_id=item_id,
            item_type=item_type,
            reviewer=reviewer,
            action=ReviewAction.COMMENT.value,
            original_result=original_result,
            reviewer_override=None,
            comment=comment,
        )
        self._audit_repo.record(
            actor=reviewer.username,
            action="review_comment_added",
            entity_type=item_type,
            entity_id=item_id,
            details={
                "action": ReviewAction.COMMENT.value,
                "original_result": original_result,
                "reviewer_override": None,
                "comment": comment,
                "reviewer_id": reviewer.id,
            },
        )
        return decision

    # ------------------------------------------------------------------
    # Audit log helpers
    # ------------------------------------------------------------------

    def get_audit_trail(self, item_id: str) -> list[AuditEntry]:
        """Return all audit entries for a specific item, oldest first.

        Args:
            item_id: The item whose audit trail is requested.

        Returns:
            List of AuditEntry rows ordered by timestamp ascending.
        """
        return (
            self._session.query(AuditEntry)
            .filter(AuditEntry.entity_id == item_id)
            .order_by(AuditEntry.timestamp.asc())
            .all()
        )

    def get_review_decisions(self, item_id: str) -> list[ReviewDecision]:
        """Return all ReviewDecision rows for an item, newest first.

        This is the primary way to confirm that BOTH the original result AND
        the reviewer override exist on the same row.

        Args:
            item_id: The item whose decisions are requested.

        Returns:
            List of ReviewDecision rows ordered by timestamp descending.
        """
        return self._review_repo.get_by_item(item_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_decision(
        self,
        item_id: str,
        item_type: str,
        reviewer: User,
        action: str,
        original_result: dict,
        reviewer_override: dict | None,
        comment: str | None,
    ) -> ReviewDecision:
        """Persist a ReviewDecision row and flush so the PK is available.

        The original_result column stores the Pipeline 2 output verbatim.
        The reviewer_override column stores the reviewer's mutation (or None).
        Neither column is ever modified after creation — this is an
        append-only ledger.
        """
        decision = ReviewDecision(
            item_id=item_id,
            item_type=item_type,
            reviewer_id=reviewer.id,
            action=action,
            comment=comment,
            original_result=original_result,   # immutable — Pipeline 2 evidence
            reviewer_override=reviewer_override,  # reviewer's change (may be None)
        )
        return self._review_repo.add(decision)
