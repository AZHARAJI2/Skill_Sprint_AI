# SkillSprint AI — Application Explanation

> *The "travel guide" for any new agent or team member joining mid-project.*

---

## What Is This Application?

**SkillSprint AI** is a web-based employee onboarding intelligence platform built for **NovaCart**, a mid-size e-commerce and logistics company. It uses Generative AI (Google Gemini) combined with rigorous Python validation to automatically create personalized, role-specific onboarding plans — and then independently verify that every piece of those plans is grounded in approved company documents.

This is **not** a chatbot. It is not a wrapper around an LLM. It is an **onboarding intelligence system** that:
1. Ingests real company documents (policies, SOPs, role descriptions, FAQs, compliance procedures)
2. Generates structured onboarding content (plans, modules, checklists, tasks, quizzes, assessments)
3. Validates every generated item against the actual source documents using pure Python logic
4. Surfaces discrepancies, hallucinations, contradictions, and gaps for human review
5. Tracks employee progress and adapts recommendations based on real performance

---

## Who Uses It?

Five user roles, each with a distinct experience:

| Role | What They See | What They Do |
|---|---|---|
| **Employee** | Personal dashboard with assigned modules, tasks, quizzes, progress milestones | Complete onboarding activities, take quizzes, track their own progress |
| **Admin** | Organization-wide dashboard with all employees, compliance coverage, flagged content | Manage employees, roles, documents; monitor system health; resolve flagged items |
| **Training Manager** | Role-based onboarding stats, module effectiveness, coverage gaps | Design/adjust training plans, review generated content, manage prerequisites |
| **Reviewer** | Manual review queue with items needing human judgment | Approve, reject, edit, or request regeneration of flagged content; their decisions are preserved alongside the original in the audit trail |
| **Manager** | Team progress dashboard, employee assessments, weak-area alerts | Monitor direct reports' onboarding progress, act on adaptive recommendations |

---

## The Two-Pipeline Architecture (Critical Design Decision)

The system's core innovation is that **generation and validation are structurally independent**:

### Pipeline 1: GenAI Generation (Python + Gemini API)
- Reads parsed document chunks + role requirement matrix + employee profile
- Uses versioned prompt templates (`onboarding_plan_v2.json`) to request structured JSON from Gemini
- Generates plans incrementally across 3 stage groups (Day 1 + Week 1, Week 2 + First 30 Days, First 60 Days + First 90 Days) to eliminate token truncation and ensure sub-30s latency (NFR-1)
- Validates each stage group against Pydantic schemas before merging in pure Python
- Retries on invalid output (capped at 3 attempts); if retries exhaust on a stage group, items are marked `generation_status: "failed_after_retries"` and prefixed with `[UNGENERATED - PENDING REVIEW]` to prevent unverified content leakage
- Defends against prompt injection embedded in documents
- **Output**: Structured onboarding plan (modules, checklists, tasks, quizzes, assessments) with source citations

### Pipeline 2: Python Validation (Pure Python — ZERO GenAI calls, ever)
- Takes the structured JSON from Pipeline 1
- Runs 9 independent validator classes against the role requirement matrix and parsed document corpus:
  - **CoverageValidator**: Are all mandatory requirements covered?
  - **TraceabilityValidator**: Does every source reference actually exist?
  - **DuplicateValidator**: Any redundant content? (uses sentence embeddings)
  - **ContradictionValidator**: Any conflicting instructions? (applies policy precedence)
  - **RoleRelevanceValidator**: Is everything actually relevant to this role?
  - **HallucinationDetector**: Any unsupported factual claims about company policy?
  - **SequenceValidator**: Are prerequisites correctly ordered?
  - **SchemaValidator**: Is the JSON structurally correct?
  - **GenerationFailureValidator**: Verifies no items have `failed_after_retries` status; forces overall status to "Manual Review Required" if any stage group failed generation after retries.
- **Output**: ValidationReport with scores (coverage, traceability, consistency) and per-item verification status

### The Comparison Engine
- Aligns Pipeline 1 output with Pipeline 2 expectations
- Compares on **structured attributes only** (requirement IDs, booleans, enums) — never on exact natural language
- Produces a requirement-level comparison report showing matches, mismatches, and explanations

---

## How the Parts Communicate

```
Documents (PDF/DOCX files on disk)
        │
        ▼
[Document Processing Layer]
  Upload → Validate → Parse → Chunk → Store
        │
        ▼
[Database] ◄── Role Requirement Matrix (CSV → load_matrix.py → DB)
        │              ◄── Employee Profiles (CRUD via API)
        │
        ├──────────────────────────────────┐
        ▼                                  ▼
[Pipeline 1: GenAI]              [Pipeline 2: Python Validation]
  Prompt Templates                   Validators (9 classes)
  GeminiProvider                     ValidationPipeline
  Schema Validation                  Scores + Statuses
  Retry + Injection Guard            ZERO GenAI calls
        │                                  │
        ▼                                  ▼
[Comparison Engine] ◄─────── aligns structured attributes ──────►
        │
        ▼
[Review Queue] ← items with status ≠ "Verified"
        │
        ▼
[Dashboards + Reports + Export]
  Employee │ Admin │ Role dashboards
  Progress tracking + adaptive recommendations
  Policy update detection + selective regeneration
  CSV / PDF / Excel export
```

---

## Key Domain Concepts

- **Role Requirement Matrix**: A 178-row CSV mapping each of 10 roles to specific requirements drawn from the 24 company documents. Each row has: requirement_id, role, mandatory/optional, priority, due_stage, source_document_id, source_section_id, competency, assessment_requirement. This is the **ground truth** for validation.

- **Verification Status** (9 possible values): Verified, Verified with Warning, Partially Verified, Source Support Missing, Requirement Missing, Unsupported Requirement, Outdated Source, Contradiction Detected, Manual Review Required. A plan is only "Verified" when it achieves 100% mandatory coverage, valid sources throughout, and zero unresolved contradictions/unsupported items.

- **Policy Precedence** (configurable hierarchy): Latest Approved Policy > Department SOP > Compliance Procedures > FAQ > Informal Guidance. This resolves the 10 known contradiction pairs in the document corpus.

- **Multi-Stage Onboarding**: Plans are structured into Day 1, Week 1, Week 2, First 30/60/90 Days. Content is never dumped entirely into Day 1.

- **Source Traceability**: Every generated module, task, quiz question, and checklist item must reference a specific document_id and section_id. The TraceabilityValidator confirms these references actually exist in the parsed corpus.

---

## Technology Choices and Why

| Choice | Why |
|---|---|
| **FastAPI** (not Streamlit) | We need proper REST APIs, RBAC middleware, async capability, and clean separation between API and UI. Streamlit is excellent for prototypes but doesn't support the multi-role auth, review workflows, and structured API endpoints this competition requires. |
| **SQLAlchemy + SQLite** | Repository pattern with ORM gives us clean data access; SQLite needs zero setup for dev/eval; same models work with Postgres for production scaling. |
| **google-genai** (not google-generativeai) | The old SDK is EOL since Nov 2025. The new SDK provides Pydantic-native response parsing, which aligns perfectly with our schema validation requirement. |
| **Pydantic v2** | Every GenAI ↔ application boundary is typed and validated. Pydantic v2's Rust-based core gives us fast validation for the 30-second performance requirement. |
| **sentence-transformers** | Needed for semantic similarity in duplicate detection and contradiction detection — can't do this with exact string matching because GenAI output wording varies across runs. |
| **BaseGenAIProvider ABC** | Competition includes live code-modification challenges. The abstraction means swapping or extending the GenAI provider is a single-class change, not a codebase rewrite. |
| **Validator class per rule** | Same reasoning — "add a new validation rule" = "add one new class implementing BaseValidator" — the answer during a live challenge, not "edit a 400-line function." |

---

## What's Already Done vs. What's Remaining

### Done (Prompt A0 — Data Generation Session)
- ✅ Fictional company: NovaCart (e-commerce + logistics)
- ✅ 10 job roles defined
- ✅ 20 company documents (DOCX + some PDFs) with mandatory/optional clauses, exceptions, cross-references, 10 conflict pairs, 10 version changes, 5 vague areas, 11 adversarial/injection cases
- ✅ 4 addendum role description documents: ROLE-07 (Recruiter), ROLE-08 (Financial Analyst), ROLE-09 (Accounts Payable Clerk), ROLE-10 (Warehouse Operations Coordinator) — all 10 roles now have dedicated ROLE-xx docs (DOCX+PDF)
- ✅ Role Requirement Matrix CSV: 178 rows, 11 columns, 131 mandatory entries, 10 roles, 24 source documents

### Remaining (4 Phases of Engineering)
- Phase 1: ✅ Document processing pipeline, database schema, employee/role CRUD, auth/RBAC skeleton, matrix loader, HTML shells. Run `python -m database.seed` then `uvicorn src.main:app`.
- Phase 2: ✅ Pipeline 1 — `PlanGenerationService.generate_for_employee`, versioned `prompt_templates/*_v1.json`, `GeminiProvider` (503 without API key), Pydantic `GeneratedPlan`, capped retry, source-grounded modules/checklists/tasks/quizzes/assessments, `InjectionGuard`, `/api/plans*`. Evidence: `reports/d4_genai_pipeline_evidence.md`.
- Phase 3: Validation pipeline (9 validators, including GenerationFailureValidator), comparison engine, consistency testing
- Phase 4: Review workflow, 3 dashboards, progress tracking, policy updates, reports, export, final packaging

---

## Competition Context

This application is built for a technical competition with:
- A **hidden evaluation phase** where unseen documents and a new role are introduced — the system must handle them without code changes
- **Live code-modification challenges** where evaluators ask the team to add/change validation rules on the spot
- **Anti-shortcut enforcement**: hard-coded plans, fake scores, prewritten content are all disqualifying
- **5-day timeline** with 4 team members working in parallel phases

The OOP architecture (ABC-based providers, composable validators, repository pattern) exists specifically to survive these live challenges. Every design decision traces back to a competition requirement.
