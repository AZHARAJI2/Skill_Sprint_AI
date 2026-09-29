"""Policy update detection and selective regeneration — Phase 4, Tasks 57-59.

When a source document is updated (new version ingested), this service:
  1. Identifies all plans affected by the changed document.
  2. Identifies which specific modules/tasks/checklists/quizzes reference the old version.
  3. Records a PolicyUpdateEvent and marks affected items for regeneration.
  4. Selective regeneration only re-runs the affected stage-groups (not the whole plan).

No GenAI calls in this module — detection is purely Python.
Regeneration is requested via PlanGenerationService (Pipeline 1) by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from config.logging_config import get_logger
from src.documents.models import Document
from src.plans.models import (
    LearningModuleRecord,
    OnboardingPlan,
    TaskRecord,
    ChecklistItemRecord,
    QuizQuestionRecord,
    AssessmentRecord,
)
from src.reviews.models import AuditEntry
from src.reviews.repository import AuditRepository

logger = get_logger("policy_update")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AffectedItem:
    """One item (module/task/etc.) affected by a policy change."""

    item_id: str
    item_type: str
    plan_id: int
    source_document_id: str
    source_section_id: str
    title: str = ""


@dataclass
class PolicyUpdateImpact:
    """Result of impact analysis for a document version change."""

    document_id: str
    old_version: str | None
    new_version: str | None
    affected_plan_ids: list[int] = field(default_factory=list)
    affected_items: list[AffectedItem] = field(default_factory=list)
    total_affected: int = 0
    analysis_timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# ---------------------------------------------------------------------------
# PolicyUpdateService
# ---------------------------------------------------------------------------


class PolicyUpdateService:
    """Detects and manages the impact of source-document updates on plans.

    Tasks 57-59:
      57 - Policy update detection: finds all affected items when a doc changes
      58 - Impact analysis: reports which modules/tasks/quizzes reference old version
      59 - Selective regeneration: marks only affected items for re-generation
    """

    def __init__(self, session: Session) -> None:
        """Inject the shared database session."""
        self._session = session
        self._audit = AuditRepository(session)

    # ------------------------------------------------------------------
    # Task 57 — Detection
    # ------------------------------------------------------------------

    def detect_affected_plans(self, document_id: str) -> list[int]:
        """Find all plan IDs that reference the given document.

        A plan is affected if its ``source_doc_versions`` JSON column
        contains the document_id key, meaning it was generated using
        content from that document.

        Args:
            document_id: The document whose content changed.

        Returns:
            List of affected plan IDs (may be empty).
        """
        all_plans: list[OnboardingPlan] = self._session.query(OnboardingPlan).all()
        affected: list[int] = []
        for plan in all_plans:
            versions = plan.source_doc_versions or {}
            if document_id in versions:
                affected.append(plan.id)
            elif plan.structured_json:
                # Also check if any generated item cites this document
                sj = plan.structured_json
                all_docs = (
                    [m.get("source_document_id") for m in sj.get("modules", [])]
                    + [t.get("source_document_id") for t in sj.get("tasks", [])]
                    + [q.get("source_document_id") for q in sj.get("quizzes", [])]
                    + [c.get("source_document_id") for c in sj.get("checklists", [])]
                )
                if document_id in all_docs:
                    affected.append(plan.id)
        return list(set(affected))

    # ------------------------------------------------------------------
    # Task 58 — Impact analysis
    # ------------------------------------------------------------------

    def analyse_impact(self, document_id: str) -> PolicyUpdateImpact:
        """Identify all items in all plans that cite the changed document.

        For each affected plan, inspect each child table
        (learning_modules, tasks, checklists, quizzes, assessments) and
        collect items where source_document_id == document_id.

        Args:
            document_id: The document ID of the updated policy/SOP/etc.

        Returns:
            PolicyUpdateImpact with full list of affected items and plans.
        """
        doc: Document | None = (
            self._session.query(Document)
            .filter(Document.document_id == document_id)
            .order_by(Document.version.desc())
            .first()
        )
        old_version = None
        new_version = doc.version if doc else None

        # Find plans referencing this document
        affected_plan_ids = self.detect_affected_plans(document_id)
        affected_items: list[AffectedItem] = []

        for plan_id in affected_plan_ids:
            # Modules
            modules = (
                self._session.query(LearningModuleRecord)
                .filter(
                    LearningModuleRecord.plan_id == plan_id,
                    LearningModuleRecord.source_document_id == document_id,
                )
                .all()
            )
            for m in modules:
                affected_items.append(AffectedItem(
                    item_id=f"M-{m.id}",
                    item_type="module",
                    plan_id=plan_id,
                    source_document_id=document_id,
                    source_section_id=m.source_section_id or "",
                    title=m.title or "",
                ))

            # Tasks
            tasks = (
                self._session.query(TaskRecord)
                .filter(TaskRecord.plan_id == plan_id)
                .all()
            )
            for t in tasks:
                payload = t.payload or {}
                if payload.get("source_document_id") == document_id:
                    affected_items.append(AffectedItem(
                        item_id=f"T-{t.id}",
                        item_type="task",
                        plan_id=plan_id,
                        source_document_id=document_id,
                        source_section_id=payload.get("source_section_id", ""),
                        title=payload.get("description", "")[:80],
                    ))

            # Checklists
            checklists = (
                self._session.query(ChecklistItemRecord)
                .filter(
                    ChecklistItemRecord.plan_id == plan_id,
                    ChecklistItemRecord.source_document_id == document_id,
                )
                .all()
            )
            for c in checklists:
                payload = c.payload or {}
                affected_items.append(AffectedItem(
                    item_id=f"CL-{c.id}",
                    item_type="checklist",
                    plan_id=plan_id,
                    source_document_id=document_id,
                    source_section_id=c.source_section_id or "",
                    title=payload.get("activity", "")[:80],
                ))

            # Quizzes
            quizzes = (
                self._session.query(QuizQuestionRecord)
                .filter(
                    QuizQuestionRecord.plan_id == plan_id,
                    QuizQuestionRecord.source_document_id == document_id,
                )
                .all()
            )
            for q in quizzes:
                payload = q.payload or {}
                affected_items.append(AffectedItem(
                    item_id=f"Q-{q.id}",
                    item_type="quiz_question",
                    plan_id=plan_id,
                    source_document_id=document_id,
                    source_section_id=q.source_section_id or "",
                    title=payload.get("question_text", "")[:80],
                ))

        impact = PolicyUpdateImpact(
            document_id=document_id,
            old_version=old_version,
            new_version=new_version,
            affected_plan_ids=affected_plan_ids,
            affected_items=affected_items,
            total_affected=len(affected_items),
        )

        logger.info(
            "policy_impact_analysis doc=%s plans=%d items=%d",
            document_id, len(affected_plan_ids), len(affected_items),
        )
        return impact

    # ------------------------------------------------------------------
    # Task 59 — Selective regeneration request
    # ------------------------------------------------------------------

    def request_selective_regeneration(
        self,
        document_id: str,
        actor: str = "system",
        provider=None,
    ) -> tuple[PolicyUpdateImpact, list[int]]:
        """Run Pipeline 1 only for the affected source requirements.

        The previous implementation merely marked plans as stale.  This
        implementation invokes ``PlanGenerationService`` with only the matrix
        entries that cite the updated document, replaces only those persisted
        items, and leaves every unrelated item untouched.  It then re-runs the
        independent Python validation before returning the result.
        """
        impact = self.analyse_impact(document_id)
        if not impact.affected_plan_ids:
            return impact, []

        # Imports are local to keep this detection-only module independent
        # until regeneration is explicitly requested.
        from src.plans.service import PlanGenerationService
        from src.plans.validation_service import PlanValidationService

        generation = PlanGenerationService(self._session, provider=provider)
        validation = PlanValidationService(self._session)
        regenerated_plan_ids: list[int] = []
        for plan_id in impact.affected_plan_ids:
            generation.regenerate_affected_items(plan_id, document_id, actor=actor)
            validation.validate(plan_id, actor=actor)
            regenerated_plan_ids.append(plan_id)

        logger.info(
            "selective_regeneration_completed doc=%s actor=%s plans=%d items=%d",
            document_id, actor, len(regenerated_plan_ids), impact.total_affected,
        )
        return impact, regenerated_plan_ids
