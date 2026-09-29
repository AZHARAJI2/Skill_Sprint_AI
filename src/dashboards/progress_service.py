"""Employee progress tracking service — SRS Steps 17, 18, 26, 50, 53, 54.

Pure-Python rules (F14):
  - Stage overdue check uses joining_date + stage offset from config.
  - Prerequisite blocking: lower-difficulty/earlier-stage module must be complete
    before higher-difficulty module of same competency area can proceed.
  - Quiz grading: automatic, against stored correct_answer, no answer leak before submission.
  - Completion recording: employee marks done; practical/scenario items -> pending_confirmation.
  - Manager confirmation: written to AuditEntry unconditionally.

No GenAI calls. No hardcoded scores (F12).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from config.settings import settings
from src.plans.models import (
    AssessmentRecord,
    ChecklistItemRecord,
    LearningModuleRecord,
    OnboardingPlan,
    QuizQuestionRecord,
    TaskRecord,
)
from src.reviews.repository import AuditRepository


# Stage order mapping (difficulty ranking)
_DIFFICULTY_RANK: dict[str, int] = {
    "Beginner": 0,
    "Intermediate": 1,
    "Advanced": 2,
}

_STAGE_ORDER: list[str] = [
    "Day 1",
    "Week 1",
    "Week 2",
    "First 30 Days",
    "First 60 Days",
    "First 90 Days",
]


@dataclass
class EmployeeProgressResult:
    """Detailed progress including overdue calculation (SRS Steps 50, 54)."""

    overall_pct: int = 0
    status: str = "Not Started"
    days_elapsed: int = 0
    has_overdue: bool = False
    overdue_count: int = 0
    overdue_stages: list[str] = field(default_factory=list)
    modules_done: int = 0
    modules_total: int = 0
    tasks_done: int = 0
    tasks_total: int = 0
    checklists_done: int = 0
    checklists_total: int = 0
    quizzes_done: int = 0
    quizzes_total: int = 0
    avg_quiz_score: int = 0
    assessments_done: int = 0
    assessments_total: int = 0


class ProgressTrackingService:
    """Surgical progress tracking that honours SRS Steps 17, 18, 26, 50, 53, 54.

    Design:
    - Overdue = today - employee.joining_date (days) > settings.stage_duration_days[stage].
    - Stage lock = disabled. Employee can work on later stages unless a prerequisite blocks.
    - Prerequisite = earlier difficulty module in the same competency area must be completed first.
    - Quiz answers are never revealed before submission; graded server-side.
    - All completion and confirmation events are appended to AuditEntry.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._audit = AuditRepository(session)

    # ------------------------------------------------------------------
    # Public: compute_employee_progress
    # ------------------------------------------------------------------

    def compute_employee_progress(self, employee_id: int) -> EmployeeProgressResult:
        """Compute full progress including overdue check (SRS Steps 50, 53, 54).

        Time unit: the onboarding stage (Day 1, Week 1, …). An item is overdue when
        today - joining_date > settings.stage_duration_days[stage].

        Returns:
            EmployeeProgressResult with status from Step 54 outcomes.
        """
        from src.employees.service import EmployeeService
        from src.plans.repository import PlanRepository

        employee = EmployeeService(self._session).get(employee_id)
        plans = PlanRepository(self._session).list_by_employee(employee_id)
        if not plans:
            return EmployeeProgressResult(status="Not Started")

        plan = sorted(plans, key=lambda p: p.id, reverse=True)[0]

        # ---- Day-count from joining date ----
        joining = employee.joining_date if employee.joining_date else date.today()
        days_elapsed = (date.today() - joining).days

        # ---- Gather child records ----
        modules = (
            self._session.query(LearningModuleRecord)
            .filter(LearningModuleRecord.plan_id == plan.id)
            .all()
        )
        tasks = (
            self._session.query(TaskRecord)
            .filter(TaskRecord.plan_id == plan.id)
            .all()
        )
        checklists = (
            self._session.query(ChecklistItemRecord)
            .filter(ChecklistItemRecord.plan_id == plan.id)
            .all()
        )
        quizzes = (
            self._session.query(QuizQuestionRecord)
            .filter(QuizQuestionRecord.plan_id == plan.id)
            .all()
        )
        assessments = (
            self._session.query(AssessmentRecord)
            .filter(AssessmentRecord.plan_id == plan.id)
            .all()
        )

        # ---- Completion counts ----
        def _is_done(payload: dict | None) -> bool:
            return (payload or {}).get("completion_status") in ("completed", "done")

        modules_done = sum(1 for m in modules if _is_done(m.payload))
        tasks_done = sum(1 for t in tasks if _is_done(t.payload))
        checklists_done = sum(1 for c in checklists if _is_done(c.payload))
        assessments_done = sum(1 for a in assessments if _is_done(a.payload))

        quiz_scores: list[int] = [
            (q.payload or {}).get("score", 0) for q in quizzes
            if (q.payload or {}).get("completion_status") in ("completed", "submitted")
        ]
        quizzes_done = sum(1 for s in quiz_scores if s >= settings.quiz_pass_score)
        avg_quiz_score = int(sum(quiz_scores) / len(quiz_scores)) if quiz_scores else 0

        # ---- Overdue check (SRS Step 50) ----
        overdue_stages: list[str] = []
        for stage, offset_days in settings.stage_duration_days.items():
            if days_elapsed > offset_days:
                # Any incomplete item in this stage is overdue
                stage_mods = [m for m in modules if (m.payload or {}).get("stage") == stage or m.stage == stage]
                stage_tasks = [t for t in tasks if t.due_stage == stage]
                stage_checks = [c for c in checklists if (c.payload or {}).get("due_stage") == stage]
                stage_quizzes = [q for q in quizzes if (q.payload or {}).get("due_stage") == stage]
                stage_assessments = [a for a in assessments if (a.payload or {}).get("stage") == stage]

                incomplete_in_stage = (
                    any(not _is_done(m.payload) for m in stage_mods)
                    or any(not _is_done(t.payload) for t in stage_tasks)
                    or any(not _is_done(c.payload) for c in stage_checks)
                    or any((q.payload or {}).get("completion_status") not in ("completed", "submitted") for q in stage_quizzes)
                    or any(not _is_done(a.payload) for a in stage_assessments)
                )
                if incomplete_in_stage:
                    overdue_stages.append(stage)

        has_overdue = len(overdue_stages) > 0
        overdue_count = len(overdue_stages)

        # ---- Weighted overall_pct (weights: 0.35, 0.25, 0.20, 0.15, 0.05) ----
        weighted_items = [
            (modules_done, len(modules), 0.35),
            (tasks_done, len(tasks), 0.25),
            (checklists_done, len(checklists), 0.20),
            (quizzes_done, len(quizzes), 0.15),
            (assessments_done, len(assessments), 0.05),
        ]
        weighted_sum = 0.0
        weight_used = 0.0
        for done, total, weight in weighted_items:
            if total > 0:
                weighted_sum += (done / total) * weight
                weight_used += weight
        overall_pct = int(weighted_sum / weight_used * 100) if weight_used > 0 else 0

        # ---- Step 54 status ----
        from src.dashboards.service import DashboardService
        status = DashboardService._assess_status(
            overall_pct=overall_pct,
            avg_quiz=avg_quiz_score,
            checklists_done=checklists_done,
            checklists_total=len(checklists),
            has_overdue=has_overdue,
        )

        return EmployeeProgressResult(
            overall_pct=overall_pct,
            status=status,
            days_elapsed=days_elapsed,
            has_overdue=has_overdue,
            overdue_count=overdue_count,
            overdue_stages=overdue_stages,
            modules_done=modules_done,
            modules_total=len(modules),
            tasks_done=tasks_done,
            tasks_total=len(tasks),
            checklists_done=checklists_done,
            checklists_total=len(checklists),
            quizzes_done=quizzes_done,
            quizzes_total=len(quizzes),
            avg_quiz_score=avg_quiz_score,
            assessments_done=assessments_done,
            assessments_total=len(assessments),
        )

    # ------------------------------------------------------------------
    # Public: check_prerequisites (SRS Step 26)
    # ------------------------------------------------------------------

    def check_prerequisites(
        self, item_type: str, item_id: str, plan_id: int
    ) -> tuple[bool, str]:
        """Check if a prerequisite is incomplete, blocking this item.

        Rules (pure Python — SRS Step 26):
        - For a learning module: if another module of LOWER difficulty in the SAME
          competency area (extracted from module title) is not yet completed, block.
        - Stages are NOT locked — the competency difficulty order is the only gate.
        - For tasks and checklists: no prerequisite blocking (they are independent).

        Returns:
            (is_blocked, reason_string)
        """
        if item_type != "module":
            return False, ""

        plan = self._session.query(OnboardingPlan).get(plan_id)
        if not plan or not plan.structured_json:
            return False, ""

        all_modules_json = plan.structured_json.get("modules", [])
        # Find target module
        target_mod = next((m for m in all_modules_json if m.get("module_id") == item_id), None)
        if not target_mod:
            return False, ""

        target_diff = _DIFFICULTY_RANK.get(target_mod.get("difficulty", "Beginner"), 0)
        target_comp = _extract_competency(target_mod.get("title", ""))

        # Check all db module records for same competency, lower difficulty, not complete
        all_records: list[LearningModuleRecord] = (
            self._session.query(LearningModuleRecord)
            .filter(LearningModuleRecord.plan_id == plan_id)
            .all()
        )
        for rec in all_records:
            payload = rec.payload or {}
            rec_mod_json = next(
                (m for m in all_modules_json if m.get("module_id") == payload.get("module_id", "")),
                None,
            )
            if rec_mod_json is None:
                # Fallback: match by title
                rec_mod_json = next(
                    (m for m in all_modules_json if m.get("title", "") == rec.title),
                    None,
                )
            if rec_mod_json is None:
                continue

            rec_diff = _DIFFICULTY_RANK.get(rec_mod_json.get("difficulty", "Beginner"), 0)
            rec_comp = _extract_competency(rec_mod_json.get("title", ""))

            if rec_comp != target_comp:
                continue

            if rec_diff < target_diff:
                # This is a prerequisite module — must be completed first
                if payload.get("completion_status") not in ("completed", "done"):
                    return True, (
                        f"prerequisite module '{rec.title}' (Beginner/{rec_comp}) "
                        f"must be completed before '{target_mod.get('title')}' ({target_mod.get('difficulty')})."
                    )

        return False, ""

    # ------------------------------------------------------------------
    # Public: record_item_completion (SRS Steps 17, 18)
    # ------------------------------------------------------------------

    def record_item_completion(
        self,
        plan_id: int,
        item_type: str,
        item_id: str,
        actor: str,
    ) -> dict[str, str]:
        """Employee marks a module, task, checklist, or assessment complete.

        Business rules (SRS Steps 17, 18):
        - Non-practical items -> status = 'completed' immediately.
        - Practical tasks (is_scenario=True) or practical/scenario assessments
          -> status = 'pending_confirmation', awaiting manager confirmation.
        - Every event (completion or confirmation request) appended to AuditEntry.

        Returns:
            {"status": "completed" | "pending_confirmation", "message": "..."}
        """
        plan = self._session.query(OnboardingPlan).get(plan_id)
        if plan is None:
            return {"status": "error", "message": "Plan not found."}

        if item_type == "module":
            return self._complete_module(plan, item_id, actor)
        elif item_type == "task":
            return self._complete_task(plan, item_id, actor)
        elif item_type == "checklist":
            return self._complete_checklist(plan, item_id, actor)
        elif item_type == "assessment":
            return self._complete_assessment(plan, item_id, actor)
        return {"status": "error", "message": f"Unknown item_type '{item_type}'."}

    def _complete_module(self, plan: OnboardingPlan, module_id: str, actor: str) -> dict:
        rec = (
            self._session.query(LearningModuleRecord)
            .filter(LearningModuleRecord.plan_id == plan.id)
            .all()
        )
        # Match by payload module_id or fallback to title lookup
        all_mods_json = (plan.structured_json or {}).get("modules", [])
        target_rec = None
        for r in rec:
            pay = r.payload or {}
            if pay.get("module_id") == module_id:
                target_rec = r
                break
            # fallback: find json module by id and match by title
            j = next((m for m in all_mods_json if m.get("module_id") == module_id), None)
            if j and j.get("title") == r.title:
                target_rec = r
                break

        if target_rec is None:
            return {"status": "error", "message": f"Module '{module_id}' not found in plan."}

        payload = dict(target_rec.payload or {})
        payload["completion_status"] = "completed"
        payload["module_id"] = module_id
        target_rec.payload = payload
        self._session.flush()

        self._audit.record(
            actor=actor,
            action="item_completed",
            entity_type="module",
            entity_id=module_id,
            details={"plan_id": plan.id, "item_type": "module"},
        )
        self._session.commit()
        return {"status": "completed", "message": "Module marked as completed."}

    def _complete_task(self, plan: OnboardingPlan, task_id: str, actor: str) -> dict:
        tasks: list[TaskRecord] = (
            self._session.query(TaskRecord)
            .filter(TaskRecord.plan_id == plan.id)
            .all()
        )
        target_rec = next(
            (t for t in tasks if (t.payload or {}).get("task_id") == task_id),
            None,
        )
        if target_rec is None:
            return {"status": "error", "message": f"Task '{task_id}' not found."}

        payload = dict(target_rec.payload or {})
        is_practical = payload.get("is_scenario", False)

        if is_practical:
            payload["completion_status"] = "pending_confirmation"
            target_rec.payload = payload
            self._session.flush()

            self._audit.record(
                actor=actor,
                action="completion_requested",
                entity_type="task",
                entity_id=task_id,
                details={"plan_id": plan.id, "requires": "manager_confirmation"},
            )
            self._session.commit()
            criteria = payload.get("completion_criteria", "manager confirmation")
            return {
                "status": "pending_confirmation",
                "message": f"Manager confirmation required: {criteria}",
            }

        payload["completion_status"] = "completed"
        target_rec.payload = payload
        self._session.flush()
        self._audit.record(
            actor=actor,
            action="item_completed",
            entity_type="task",
            entity_id=task_id,
            details={"plan_id": plan.id},
        )
        self._session.commit()
        return {"status": "completed", "message": "Task marked as completed."}

    def _complete_checklist(self, plan: OnboardingPlan, item_id: str, actor: str) -> dict:
        checklists: list[ChecklistItemRecord] = (
            self._session.query(ChecklistItemRecord)
            .filter(ChecklistItemRecord.plan_id == plan.id)
            .all()
        )
        target_rec = next(
            (c for c in checklists if (c.payload or {}).get("item_id") == item_id),
            None,
        )
        if target_rec is None:
            return {"status": "error", "message": f"Checklist item '{item_id}' not found."}

        payload = dict(target_rec.payload or {})
        payload["completion_status"] = "completed"
        target_rec.payload = payload
        self._session.flush()

        self._audit.record(
            actor=actor,
            action="item_completed",
            entity_type="checklist",
            entity_id=item_id,
            details={"plan_id": plan.id},
        )
        self._session.commit()
        return {"status": "completed", "message": "Checklist item marked as completed."}

    def _complete_assessment(self, plan: OnboardingPlan, assessment_id: str, actor: str) -> dict:
        assessments: list[AssessmentRecord] = (
            self._session.query(AssessmentRecord)
            .filter(AssessmentRecord.plan_id == plan.id)
            .all()
        )
        target_rec = next(
            (a for a in assessments if (a.payload or {}).get("assessment_id") == assessment_id),
            None,
        )
        if target_rec is None:
            return {"status": "error", "message": f"Assessment '{assessment_id}' not found."}

        payload = dict(target_rec.payload or {})
        # Practical and scenario assessments require confirmation
        is_practical = target_rec.assessment_type in ("practical", "scenario")

        if is_practical:
            payload["completion_status"] = "pending_confirmation"
            target_rec.payload = payload
            self._session.flush()

            self._audit.record(
                actor=actor,
                action="completion_requested",
                entity_type="assessment",
                entity_id=assessment_id,
                details={"plan_id": plan.id, "requires": "manager_confirmation"},
            )
            self._session.commit()
            return {
                "status": "pending_confirmation",
                "message": "Manager/Reviewer confirmation required for practical assessment.",
            }

        payload["completion_status"] = "completed"
        target_rec.payload = payload
        self._session.flush()
        self._audit.record(
            actor=actor,
            action="item_completed",
            entity_type="assessment",
            entity_id=assessment_id,
            details={"plan_id": plan.id},
        )
        self._session.commit()
        return {"status": "completed", "message": "Assessment marked as completed."}

    # ------------------------------------------------------------------
    # Public: confirm_item_completion (SRS Step 18)
    # ------------------------------------------------------------------

    def confirm_item_completion(
        self,
        plan_id: int,
        item_type: str,
        item_id: str,
        reviewer_name: str,
        confirmed: bool,
        comment: str = "",
    ) -> dict[str, str]:
        """Manager/Reviewer confirms (or rejects) practical task/assessment completion.

        Rules (SRS Step 18):
        - Confirmed: status -> 'completed'. Rejected: status -> 'not_started'.
        - Always writes an AuditEntry regardless of outcome.

        Returns:
            {"status": "completed" | "rejected", "message": "..."}
        """
        if item_type == "task":
            records: list[Any] = (
                self._session.query(TaskRecord)
                .filter(TaskRecord.plan_id == plan_id)
                .all()
            )
            target_rec = next(
                (r for r in records if (r.payload or {}).get("task_id") == item_id),
                None,
            )
        elif item_type == "assessment":
            records = (
                self._session.query(AssessmentRecord)
                .filter(AssessmentRecord.plan_id == plan_id)
                .all()
            )
            target_rec = next(
                (r for r in records if (r.payload or {}).get("assessment_id") == item_id),
                None,
            )
        else:
            return {"status": "error", "message": f"Confirmation not supported for '{item_type}'."}

        if target_rec is None:
            return {"status": "error", "message": f"{item_type.title()} '{item_id}' not found."}

        payload = dict(target_rec.payload or {})
        new_status = "completed" if confirmed else "not_started"
        payload["completion_status"] = new_status
        payload["reviewer_comment"] = comment
        payload["reviewer_name"] = reviewer_name
        target_rec.payload = payload
        self._session.flush()

        action = "completion_confirmed" if confirmed else "completion_rejected"
        self._audit.record(
            actor=reviewer_name,
            action=action,
            entity_type=item_type,
            entity_id=item_id,
            details={
                "plan_id": plan_id,
                "confirmed": confirmed,
                "comment": comment,
            },
        )
        self._session.commit()

        msg = f"{item_type.title()} completion {'confirmed' if confirmed else 'rejected'} by {reviewer_name}."
        return {"status": new_status, "message": msg}

    # ------------------------------------------------------------------
    # Public: grade_quiz (SRS Step 53)
    # ------------------------------------------------------------------

    def grade_quiz(
        self,
        plan_id: int,
        answers: dict[str, str],
        actor: str,
    ) -> dict[str, Any]:
        """Grade quiz answers automatically against stored correct_answer.

        Rules (SRS Step 53 / F12):
        - Never reveals correct answers before submission.
        - After submission, reveals correct answer and explanation per question.
        - Writes AuditEntry for every quiz submission.

        Args:
            plan_id: Plan to grade quiz for.
            answers: {question_id: selected_answer} mapping.
            actor: Username of the submitter.

        Returns:
            {
              "score": int (0-100),
              "passed": bool,
              "details": {
                question_id: {
                  "correct": bool,
                  "selected": str,
                  "correct_answer": str,   # revealed AFTER submission
                  "explanation": str,      # revealed AFTER submission
                }
              }
            }
        """
        quizzes: list[QuizQuestionRecord] = (
            self._session.query(QuizQuestionRecord)
            .filter(QuizQuestionRecord.plan_id == plan_id)
            .all()
        )

        expected_question_ids = {
            (q.payload or {}).get("question_id", str(q.id)) for q in quizzes
        }
        submitted_question_ids = set(answers)
        if expected_question_ids != submitted_question_ids:
            raise ValueError(
                "Submit exactly one answer for every quiz question before grading."
            )

        details: dict[str, dict] = {}
        correct_count = 0
        total_graded = 0

        for q in quizzes:
            payload = q.payload or {}
            q_id = payload.get("question_id", str(q.id))
            if q_id not in answers:
                continue

            selected = answers[q_id]
            stored_answer = payload.get("correct_answer", "")
            explanation = payload.get("explanation", "")

            if isinstance(stored_answer, list):
                # Multiple-response questions pass only when the complete set
                # of selected options matches the stored answer.  Awarding a
                # point for one of several correct choices is misleading.
                selected_values = selected if isinstance(selected, list) else [selected]
                is_correct = {
                    self._normalize(value) for value in selected_values
                } == {self._normalize(value) for value in stored_answer}
            else:
                is_correct = self._normalize(selected) == self._normalize(stored_answer)

            if is_correct:
                correct_count += 1
            total_graded += 1

            details[q_id] = {
                "correct": is_correct,
                "selected": selected,
                "correct_answer": stored_answer,   # only revealed POST-submission
                "explanation": explanation,        # only revealed POST-submission
            }

            # Update quiz record with per-question result (interim flush)
            payload["completion_status"] = "submitted"
            payload["submitted_answer"] = selected
            payload["is_correct"] = is_correct
            q.payload = payload

        self._session.flush()

        total_in_plan = len(quizzes)
        score = int(correct_count / total_graded * 100) if total_graded > 0 else 0
        passed = score >= settings.quiz_pass_score

        # Write overall plan-level score back to every graded quiz record so that
        # compute_employee_progress can sum them correctly (F12: no hardcoded scores).
        for q in quizzes:
            payload = q.payload or {}
            if payload.get("completion_status") == "submitted":
                payload["score"] = score  # overall quiz session score
                q.payload = payload

        self._session.flush()

        self._audit.record(
            actor=actor,
            action="quiz_submitted",
            entity_type="quiz",
            entity_id=f"plan_{plan_id}",
            details={
                "plan_id": plan_id,
                "score": score,
                "passed": passed,
                "correct_count": correct_count,
                "total_graded": total_graded,
            },
        )
        self._session.commit()

        return {
            "score": score,
            "passed": passed,
            "total_in_plan": total_in_plan,
            "total_answered": total_graded,
            "correct_count": correct_count,
            "details": details,
        }

    # ------------------------------------------------------------------
    # Public: check_single_answer - per-question immediate feedback
    # ------------------------------------------------------------------

    def check_single_answer(self, plan_id: int, question_id: str, selected) -> dict:
        """Validate one quiz answer and return correctness + explanation.

        The correct answer is fetched from the DB only after the employee
        commits an answer, so it is never preloaded into the page (F12 safe).
        """
        quizzes = (
            self._session.query(QuizQuestionRecord)
            .filter(QuizQuestionRecord.plan_id == plan_id)
            .all()
        )
        for q in quizzes:
            payload = q.payload or {}
            q_id = payload.get("question_id", str(q.id))
            if q_id != question_id:
                continue

            stored_answer = payload.get("correct_answer", "")
            explanation = payload.get("explanation", "")

            if isinstance(stored_answer, list):
                selected_values = selected if isinstance(selected, list) else [selected]
                is_correct = (
                    {self._normalize(v) for v in selected_values}
                    == {self._normalize(v) for v in stored_answer}
                )
            else:
                is_correct = self._normalize(selected) == self._normalize(stored_answer)

            return {
                "question_id": question_id,
                "correct": is_correct,
                "correct_answer": stored_answer,
                "explanation": explanation,
                "selected": selected,
            }

        raise ValueError(f"Question {question_id!r} not found in plan {plan_id}")

    # ------------------------------------------------------------------
    # Public: get_sanitized_quiz_items (no answer leak before submission)
    # ------------------------------------------------------------------

    def get_sanitized_quiz_items(self, plan_id: int) -> list[dict]:
        """Return quiz items with correct_answer and explanation stripped out.

        Only shows question_text, options, question_type, difficulty, source
        — never reveals correct_answer or explanation until after submission (F12).
        """
        quizzes: list[QuizQuestionRecord] = (
            self._session.query(QuizQuestionRecord)
            .filter(QuizQuestionRecord.plan_id == plan_id)
            .all()
        )
        safe_items: list[dict] = []
        for q in quizzes:
            payload = q.payload or {}
            safe_items.append(
                {
                    "question_id": payload.get("question_id", str(q.id)),
                    "question_text": payload.get("question_text", ""),
                    "options": payload.get("options", []),
                    "question_type": payload.get("question_type", ""),
                    "difficulty": payload.get("difficulty", ""),
                    "source_document_id": payload.get("source_document_id", "") or q.source_document_id,
                    "source_section_id": payload.get("source_section_id", "") or q.source_section_id,
                    "due_stage": payload.get("due_stage", ""),
                    # Explicitly excluded: correct_answer, explanation
                    "correct_answer": None,
                    "explanation": None,
                }
            )
        return safe_items

    def get_assessment_items(self, plan_id: int) -> list[dict]:
        """Return employee-visible assessment instructions from persisted records.

        Assessments are sourced from their own records instead of the plan JSON
        so they remain visible if a legacy plan cannot be parsed by the current
        Pydantic schema. Rubrics contain evaluation criteria, not answer keys.
        """
        assessments: list[AssessmentRecord] = (
            self._session.query(AssessmentRecord)
            .filter(AssessmentRecord.plan_id == plan_id)
            .all()
        )
        return [
            {
                "assessment_id": payload.get("assessment_id", str(record.id)),
                "title": payload.get("title", "Assessment"),
                "assessment_type": payload.get("assessment_type", record.assessment_type or ""),
                "difficulty": payload.get("difficulty", ""),
                "stage": payload.get("stage", ""),
                "pass_threshold": payload.get("pass_threshold", 0.8),
                "rubric": payload.get("rubric", []),
                "source_document_id": payload.get("source_document_id", record.payload.get("source_document_id", "")),
                "source_section_id": payload.get("source_section_id", record.payload.get("source_section_id", "")),
                "completion_status": payload.get("completion_status", "not_started"),
            }
            for record in assessments
            for payload in [record.payload or {}]
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(s: Any) -> str:
        if s is None:
            return ""
        return str(s).strip().lower()


def _extract_competency(title: str) -> str:
    """Extract competency name from a module title for prerequisite matching.

    Titles follow pattern: "Competency Area — Stage" or plain text.
    Extracts the first part before ' — ' as competency; falls back to the full title.
    """
    if " — " in title:
        return title.split(" — ")[0].strip()
    if " - " in title:
        return title.split(" - ")[0].strip()
    return title.strip()
