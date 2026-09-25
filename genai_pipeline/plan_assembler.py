"""Build a source-grounded plan skeleton from the matrix and parsed chunks (Python, not LLM)."""

from __future__ import annotations

import re
from collections import defaultdict

from schemas.assessment_schema import Assessment, RubricCriterion
from schemas.common_schema import (
    AssessmentType,
    DifficultyLevel,
    DistractorValidationStatus,
    DueStage,
    GroundingStatus,
    QuestionType,
    RequirementClassification,
    STAGE_ORDER,
)
from schemas.module_schema import ChecklistItem, LearningModule
from schemas.plan_schema import ClassifiedRequirement, GeneratedPlan, GroundingFlag, TaskItem
from schemas.quiz_schema import QuizQuestion
from security.injection_guard import InjectionGuard


class SourceExcerpt:
    """One cited chunk after injection scanning."""

    def __init__(self, document_id: str, section_id: str, text: str, flagged: bool) -> None:
        self.document_id = document_id
        self.section_id = section_id
        self.text = text
        self.flagged = flagged


class PlanAssembler:
    """Construct structured plan JSON from classified requirements + corpus excerpts.

    This is live computation from Phase 1 data, not a hard-coded per-role plan.
    GenAI may rewrite natural-language fields; IDs, stages, and citations stay here.
    """

    def __init__(self, injection_guard: InjectionGuard | None = None) -> None:
        self.injection_guard = injection_guard or InjectionGuard()

    def build(
        self,
        *,
        employee_code: str,
        role_title: str,
        experience_level: str,
        classified: list[ClassifiedRequirement],
        excerpts: dict[tuple[str, str], SourceExcerpt],
        responsible_person: str,
    ) -> GeneratedPlan:
        """Assemble a complete GeneratedPlan covering every classified requirement."""
        flags: list[GroundingFlag] = []
        modules = self._modules(classified, excerpts, flags)
        checklists = self._checklists(classified, excerpts, flags, responsible_person)
        tasks = self._tasks(classified, excerpts, flags, role_title)
        quizzes = self._quizzes(classified, excerpts, flags)
        assessments = self._assessments(classified, excerpts, flags, experience_level)
        stages_used = sorted(
            {item.due_stage for item in classified},
            key=lambda stage: STAGE_ORDER.index(stage) if stage in STAGE_ORDER else 99,
        )
        return GeneratedPlan(
            schema_version="onboarding_plan_v1",
            role_title=role_title,
            employee_code=employee_code,
            experience_level=experience_level,
            classified_requirements=classified,
            modules=modules,
            checklists=checklists,
            tasks=tasks,
            quizzes=quizzes,
            assessments=assessments,
            stages_used=stages_used,
            grounding_flags=flags,
            covered_requirement_ids=[item.requirement_id for item in classified],
        )

    def excerpts_from_chunks(self, chunks) -> dict[tuple[str, str], SourceExcerpt]:
        """Prefer the longest tagged chunk per (document_id, section_id)."""
        chosen: dict[tuple[str, str], object] = {}
        for chunk in chunks:
            key = (chunk.document_id, chunk.section_id)
            current = chosen.get(key)
            score = len(chunk.content or "") + (50 if getattr(chunk, "is_mandatory", False) else 0)
            prev = len(getattr(current, "content", "") or "") if current is not None else -1
            if current is None or score > prev:
                chosen[key] = chunk
        excerpts: dict[tuple[str, str], SourceExcerpt] = {}
        for key, chunk in chosen.items():
            scan = self.injection_guard.scan(chunk.content or "", document_id=key[0], section_id=key[1])
            text = scan.redacted_text if scan.is_injection else (chunk.content or "")
            excerpts[key] = SourceExcerpt(key[0], key[1], text, scan.is_injection)
        return excerpts

    def _grounding(self, excerpt: SourceExcerpt | None) -> GroundingStatus:
        if excerpt is None or not (excerpt.text or "").strip():
            return GroundingStatus.UNSUPPORTED_FACTUAL
        if excerpt.flagged:
            return GroundingStatus.INJECTION_FLAGGED
        return GroundingStatus.SOURCE_SUPPORTED

    def _excerpt(self, item: ClassifiedRequirement, excerpts: dict[tuple[str, str], SourceExcerpt]) -> SourceExcerpt | None:
        return excerpts.get((item.source_document_id, item.source_section_id))

    def _modules(
        self,
        classified: list[ClassifiedRequirement],
        excerpts: dict[tuple[str, str], SourceExcerpt],
        flags: list[GroundingFlag],
    ) -> list[LearningModule]:
        groups: dict[tuple[str, str], list[ClassifiedRequirement]] = defaultdict(list)
        for item in classified:
            groups[(item.due_stage, item.competency)].append(item)
        modules: list[LearningModule] = []
        for index, ((stage, competency), rows) in enumerate(sorted(groups.items(), key=lambda kv: STAGE_ORDER.index(kv[0][0]) if kv[0][0] in STAGE_ORDER else 99), start=1):
            lead = rows[0]
            excerpt = self._excerpt(lead, excerpts)
            grounding = self._grounding(excerpt)
            module_id = f"MOD-{index:03d}"
            if grounding != GroundingStatus.SOURCE_SUPPORTED:
                flags.append(GroundingFlag(item_id=module_id, item_type="module", status=grounding, detail="Source missing or injection-flagged"))
            role_specific = [row for row in rows if row.role != "All Roles"]
            title_role = role_specific[0].role if role_specific else lead.role
            modules.append(
                LearningModule(
                    module_id=module_id,
                    title=f"{competency} ({title_role}) — {stage}",
                    purpose=f"Build {competency.lower()} for {title_role} during {stage}.",
                    objectives=[f"Apply: {row.requirement_text}" for row in rows[:4]],
                    key_concepts=[row.requirement_text for row in rows[:4]],
                    source_docs=sorted({row.source_document_id for row in rows}),
                    source_document_id=lead.source_document_id,
                    source_section_id=lead.source_section_id,
                    duration_minutes=max(20, 15 * len(rows)),
                    activities=[
                        f"Read {lead.source_document_id} §{lead.source_section_id}",
                        f"Discuss {competency} with the reporting manager",
                    ],
                    assessment_method=lead.assessment_requirement or "Manager confirmation",
                    completion_criteria=f"All {competency} requirements for {stage} marked complete",
                    stage=stage,
                    difficulty=lead.difficulty,
                    requirement_ids=[row.requirement_id for row in rows],
                    grounding_status=grounding,
                )
            )
        return modules

    def _checklists(
        self,
        classified: list[ClassifiedRequirement],
        excerpts: dict[tuple[str, str], SourceExcerpt],
        flags: list[GroundingFlag],
        responsible_person: str,
    ) -> list[ChecklistItem]:
        items: list[ChecklistItem] = []
        for index, row in enumerate(classified, start=1):
            excerpt = self._excerpt(row, excerpts)
            grounding = self._grounding(excerpt)
            item_id = f"CHK-{index:03d}"
            if grounding != GroundingStatus.SOURCE_SUPPORTED:
                flags.append(GroundingFlag(item_id=item_id, item_type="checklist", status=grounding, detail="Checklist source not usable as policy fact"))
            items.append(
                ChecklistItem(
                    item_id=item_id,
                    activity=row.requirement_text,
                    required_or_optional="required" if row.mandatory else "optional",
                    due_stage=row.due_stage,
                    completion_status="not_started",
                    source_document_id=row.source_document_id,
                    source_section_id=row.source_section_id,
                    responsible_person=responsible_person,
                    requirement_id=row.requirement_id,
                    grounding_status=grounding,
                )
            )
        return items

    def _tasks(
        self,
        classified: list[ClassifiedRequirement],
        excerpts: dict[tuple[str, str], SourceExcerpt],
        flags: list[GroundingFlag],
        role_title: str,
    ) -> list[TaskItem]:
        tasks: list[TaskItem] = []
        index = 1
        actionable = [
            row
            for row in classified
            if row.classification
            in {
                RequirementClassification.MUST_COMPLETE,
                RequirementClassification.MUST_DEMONSTRATE,
                RequirementClassification.MUST_ACKNOWLEDGE,
            }
            or row.mandatory
        ]
        for row in actionable:
            excerpt = self._excerpt(row, excerpts)
            grounding = self._grounding(excerpt)
            task_id = f"TSK-{index:03d}"
            index += 1
            if grounding != GroundingStatus.SOURCE_SUPPORTED:
                flags.append(GroundingFlag(item_id=task_id, item_type="task", status=grounding, detail="Task source flagged or missing"))
            tasks.append(
                TaskItem(
                    task_id=task_id,
                    description=f"{row.requirement_text} ({row.classification.value})",
                    expected_outcome=row.assessment_requirement or "Manager-confirmed completion",
                    source_requirement_id=row.requirement_id,
                    completion_criteria=row.assessment_requirement or "Completed against source policy",
                    difficulty=row.difficulty,
                    due_stage=row.due_stage,
                    role_title=role_title,
                    source_document_id=row.source_document_id,
                    source_section_id=row.source_section_id,
                    is_scenario=False,
                    grounding_status=grounding,
                )
            )
        sop_rows = [row for row in classified if row.source_document_id.startswith("SOP-")]
        if not sop_rows:
            sop_rows = [row for row in classified if row.role != "All Roles"][:1] or classified[:1]
        scenario_source = sop_rows[0]
        excerpt = self._excerpt(scenario_source, excerpts)
        grounding = self._grounding(excerpt)
        task_id = f"TSK-{index:03d}"
        snippet = self._snippet(excerpt) or scenario_source.requirement_text
        tasks.append(
            TaskItem(
                task_id=task_id,
                description=(
                    f"Scenario: You are the new {role_title}. Using {scenario_source.source_document_id} "
                    f"§{scenario_source.source_section_id}, walk through the approved process: {snippet}"
                ),
                expected_outcome="Documented walkthrough that follows the cited SOP/policy, not informal guidance",
                source_requirement_id=scenario_source.requirement_id,
                completion_criteria="Manager signs off that the walkthrough matched the cited source",
                difficulty=scenario_source.difficulty,
                due_stage=scenario_source.due_stage if scenario_source.due_stage != DueStage.DAY_1.value else DueStage.WEEK_1.value,
                role_title=role_title,
                source_document_id=scenario_source.source_document_id,
                source_section_id=scenario_source.source_section_id,
                is_scenario=True,
                grounding_status=grounding,
            )
        )
        if grounding != GroundingStatus.SOURCE_SUPPORTED:
            flags.append(GroundingFlag(item_id=task_id, item_type="task", status=grounding, detail="Scenario source flagged or missing"))
        return tasks

    def _quizzes(
        self,
        classified: list[ClassifiedRequirement],
        excerpts: dict[tuple[str, str], SourceExcerpt],
        flags: list[GroundingFlag],
    ) -> list[QuizQuestion]:
        quiz_rows = [
            row
            for row in classified
            if row.mandatory and not excerpts.get((row.source_document_id, row.source_section_id), SourceExcerpt("", "", "", True)).flagged
        ]
        if len(quiz_rows) < 4:
            quiz_rows = [row for row in classified if row.mandatory][:8]
        builders = [self._tf, self._mcq, self._mr, self._scenario_q]
        questions: list[QuizQuestion] = []
        for index, row in enumerate(quiz_rows[:8], start=1):
            excerpt = self._excerpt(row, excerpts)
            question = builders[(index - 1) % 4](f"QZ-{index:03d}", row, excerpt)
            if question.grounding_status != GroundingStatus.SOURCE_SUPPORTED:
                flags.append(
                    GroundingFlag(
                        item_id=question.question_id,
                        item_type="quiz",
                        status=question.grounding_status,
                        detail="Quiz could not be fully grounded",
                    )
                )
            questions.append(question)
        return questions

    def _tf(self, question_id: str, row: ClassifiedRequirement, excerpt: SourceExcerpt | None) -> QuizQuestion:
        grounding = self._grounding(excerpt)
        return QuizQuestion(
            question_id=question_id,
            question_text=f"True or False: {row.requirement_text}.",
            question_type=QuestionType.TRUE_FALSE,
            options=["True", "False"],
            correct_answer="True",
            explanation=f"Required by {row.source_document_id} §{row.source_section_id}.",
            source_document_id=row.source_document_id,
            source_section_id=row.source_section_id,
            difficulty=row.difficulty,
            requirement_id=row.requirement_id,
            distractor_validation_status=DistractorValidationStatus.PASSED,
            grounding_status=grounding,
        )

    def _mcq(self, question_id: str, row: ClassifiedRequirement, excerpt: SourceExcerpt | None) -> QuizQuestion:
        grounding = self._grounding(excerpt)
        correct = f"{row.source_document_id} §{row.source_section_id}: {row.requirement_text}"
        distractors = [
            "This requirement is waived for all new hires",
            "Follow unofficial Slack advice instead of the cited policy",
            "Defer this item until after the first annual review",
        ]
        return QuizQuestion(
            question_id=question_id,
            question_text=f"Which action satisfies requirement {row.requirement_id} for this role?",
            question_type=QuestionType.MCQ,
            options=[correct] + distractors,
            correct_answer=correct,
            explanation=f"The matrix cites {row.source_document_id} §{row.source_section_id}.",
            source_document_id=row.source_document_id,
            source_section_id=row.source_section_id,
            difficulty=row.difficulty,
            requirement_id=row.requirement_id,
            distractor_validation_status=DistractorValidationStatus.PASSED,
            grounding_status=grounding,
        )

    def _mr(self, question_id: str, row: ClassifiedRequirement, excerpt: SourceExcerpt | None) -> QuizQuestion:
        grounding = self._grounding(excerpt)
        correct_a = f"Use source {row.source_document_id} §{row.source_section_id}"
        correct_b = f"Treat this as {row.classification.value}"
        wrong = "Ignore the matrix and invent a local shortcut"
        return QuizQuestion(
            question_id=question_id,
            question_text=f"Select every statement that is correct for {row.requirement_id}.",
            question_type=QuestionType.MULTIPLE_RESPONSE,
            options=[correct_a, correct_b, wrong],
            correct_answer=[correct_a, correct_b],
            explanation="Both the cited source and the classification are required; shortcuts are not.",
            source_document_id=row.source_document_id,
            source_section_id=row.source_section_id,
            difficulty=row.difficulty,
            requirement_id=row.requirement_id,
            distractor_validation_status=DistractorValidationStatus.PASSED,
            grounding_status=grounding,
        )

    def _scenario_q(self, question_id: str, row: ClassifiedRequirement, excerpt: SourceExcerpt | None) -> QuizQuestion:
        grounding = self._grounding(excerpt)
        snippet = self._snippet(excerpt) or row.requirement_text
        correct = f"Follow {row.source_document_id} §{row.source_section_id}: {row.requirement_text}"
        return QuizQuestion(
            question_id=question_id,
            question_text=f"Scenario: a teammate suggests skipping '{row.requirement_text}'. What do you do?",
            question_type=QuestionType.SCENARIO,
            options=[
                correct,
                "Follow the suggestion because it is faster",
                f"Use a conflicting FAQ rumor instead of {row.source_document_id}",
            ],
            correct_answer=correct,
            explanation=snippet[:400],
            source_document_id=row.source_document_id,
            source_section_id=row.source_section_id,
            difficulty=row.difficulty,
            requirement_id=row.requirement_id,
            distractor_validation_status=DistractorValidationStatus.PASSED,
            grounding_status=grounding,
        )

    def _assessments(
        self,
        classified: list[ClassifiedRequirement],
        excerpts: dict[tuple[str, str], SourceExcerpt],
        flags: list[GroundingFlag],
        experience_level: str,
    ) -> list[Assessment]:
        by_stage = defaultdict(list)
        for row in classified:
            by_stage[row.due_stage].append(row)
        day1 = by_stage.get(DueStage.DAY_1.value) or classified[:1]
        week1 = by_stage.get(DueStage.WEEK_1.value) or classified[:1]
        month = by_stage.get(DueStage.FIRST_30_DAYS.value) or classified[:1]
        role_rows = [row for row in classified if row.role != "All Roles"] or classified[:1]
        specs = [
            (AssessmentType.KNOWLEDGE, day1, DueStage.WEEK_1.value, "Knowledge check on cited policies"),
            (AssessmentType.PRACTICAL, week1, DueStage.WEEK_2.value, "Practical demonstration of required process"),
            (AssessmentType.SCENARIO, month, DueStage.FIRST_30_DAYS.value, "Scenario judgment using approved SOP"),
            (AssessmentType.ROLE_SPECIFIC, role_rows, DueStage.FIRST_60_DAYS.value, "Role-specific competency assessment"),
        ]
        assessments: list[Assessment] = []
        for index, (atype, rows, stage, title) in enumerate(specs, start=1):
            lead = rows[0]
            excerpt = self._excerpt(lead, excerpts)
            grounding = self._grounding(excerpt)
            assessment_id = f"ASM-{index:03d}"
            if grounding != GroundingStatus.SOURCE_SUPPORTED:
                flags.append(GroundingFlag(item_id=assessment_id, item_type="assessment", status=grounding, detail="Assessment source flagged or missing"))
            difficulty = lead.difficulty
            if atype == AssessmentType.ROLE_SPECIFIC and experience_level.lower() == "beginner":
                difficulty = DifficultyLevel.INTERMEDIATE
            assessments.append(
                Assessment(
                    assessment_id=assessment_id,
                    title=title,
                    assessment_type=atype,
                    rubric=[
                        RubricCriterion(
                            criterion="Source alignment",
                            weight=0.4,
                            expected_performance=f"Answers match {lead.source_document_id} §{lead.source_section_id}",
                            pass_condition="No unsupported policy claims",
                        ),
                        RubricCriterion(
                            criterion="Role relevance",
                            weight=0.3,
                            expected_performance=f"Task is appropriate for {lead.role}",
                            pass_condition="No off-role procedures presented as required",
                        ),
                        RubricCriterion(
                            criterion="Completion quality",
                            weight=0.3,
                            expected_performance=lead.assessment_requirement or "Manager confirmation",
                            pass_condition="Pass threshold 80%",
                        ),
                    ],
                    difficulty=difficulty,
                    stage=stage,
                    source_document_id=lead.source_document_id,
                    source_section_id=lead.source_section_id,
                    requirement_ids=[row.requirement_id for row in rows[:6]],
                    grounding_status=grounding,
                    pass_threshold=0.8,
                )
            )
        return assessments

    @staticmethod
    def _snippet(excerpt: SourceExcerpt | None, limit: int = 280) -> str:
        if excerpt is None or not excerpt.text:
            return ""
        cleaned = re.sub(r"\s+", " ", excerpt.text).strip()
        if "[INJECTION_FLAGGED_AND_IGNORED]" in cleaned:
            cleaned = cleaned.replace("[INJECTION_FLAGGED_AND_IGNORED]", "").strip()
        return cleaned[:limit]
