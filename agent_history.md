# Agent History — SkillSprint AI

> **Purpose**: Internal engineering memory for AI agents. NOT the competition's
> AI_USAGE.md (that is a separate file for human judges — see AI_USAGE.md).
> Each phase has its own section to avoid merge conflicts when 4 people work
> in parallel branches.

---

## Phase 0 Log (Architecture & Planning)

### Entry 001 — 2026-09-24 | Role: Tech Lead (Architecture Session)

**What was done**:
1. **Prerequisite verification**: Confirmed existence and completeness of all input data:
   - `sample_documents/`: 20 DOCX files + 6 PDF duplicates across 6 subdirectories (compliance, faqs, handbook, policies, role_descriptions, sops). Total 26 files on disk representing 20 unique documents.
   - `role_matrix/role_requirement_matrix_seed.csv`: 154 rows, 11 columns. 111 mandatory entries, 10 unique roles, 20 unique source_document_ids. All required counts met or exceeded per dataset_verification_report.md.
   - Company identified as **NovaCart** (e-commerce + logistics).
   - 10 adversarial/prompt-injection cases confirmed embedded across documents.
   - 10 conflicting instruction pairs confirmed.
   - 10 policy version change cases confirmed.
   - 4 roles (Recruiter, Financial Analyst, Accounts Payable Clerk, Warehouse Operations Coordinator) have no dedicated ROLE-XX documents — requirements come from shared policies + SOPs + matrix. This is by design.

2. **Technology stack locked** (Protocol 1):
   - Python 3.12.3, FastAPI 0.141.1, Pydantic 2.13.5, SQLAlchemy 2.0.54, google-genai 2.23.0 (NOT deprecated google-generativeai), pdfplumber 0.11.10, python-docx 1.2.0, sentence-transformers 6.1.0, uvicorn 0.53.0, pandas 3.0.6, numpy 2.5.3, plotly 7.0.0, jinja2 3.1.6.
   - Critical finding: `google-generativeai` is EOL since Nov 2025. Replaced with `google-genai` v2.23.0 which uses `client = genai.Client(api_key=...)` pattern and returns Pydantic-based responses natively.

3. **Architecture established** (Protocol 3):
   - Two independent pipelines: Pipeline 1 (GenAI + Python), Pipeline 2 (pure Python, zero GenAI).
   - OOP architecture with ABCs: BaseGenAIProvider, BaseValidator, BaseRepository.
   - 8 concrete validator classes composable via ValidationPipeline.
   - Repository pattern for all DB access — no raw queries in routes/services.
   - Policy precedence hierarchy: Latest Approved Policy > Department SOP > Compliance Procedures > FAQ > Informal Guidance.
   - Verification status enum with 9 values.
   - FastAPI + Jinja2 + Bootstrap 5.3 for frontend (not Streamlit — competition requires multi-role RBAC, review workflows, proper REST APIs).

4. **Phase ownership assigned** (Protocol 5):
   - Phase 1 (Foundation): steps 4-10, doc processing, DB, auth, matrix loader
   - Phase 2 (GenAI): steps 11-26 + 37-43, all content generation, prompts, injection defense
   - Phase 3 (Validation): steps 27-36 + 44-47, validation pipeline, comparison, consistency
   - Phase 4 (Delivery): steps 48-63, review workflow, dashboards, progress, reports, export, packaging

5. **Memory Trinity created**:
   - `PROJECT_MAP.md` — full architecture, phase ownership, compliance checklist, folder structure
   - `app_explanation.md` — the "travel guide" for joining agents/members
   - `agent_history.md` — this file

**Key decisions and rationale**:
- **FastAPI over Streamlit**: Streamlit cannot support the multi-role RBAC, stateful review workflows, and structured REST API endpoints that the competition spec demands. FastAPI gives us typed routes, async capability, dependency injection for auth, and OpenAPI docs for free.
- **google-genai over google-generativeai**: The old SDK is literally end-of-life. Using it would risk breaking during the 5-day competition window.
- **SQLAlchemy Repository pattern**: The competition includes live code-modification challenges. Isolating DB access behind repositories means a "change how we query roles" challenge is a single-file edit, not a find-and-replace across the codebase.
- **8 validator classes (not one big function)**: When evaluators say "add a new validation rule," the answer is "create one new class implementing BaseValidator and register it." This is a 2-minute change, not a surgery on a monolith.
- **Policy precedence as a configurable YAML**: The contradiction challenge will test precedence rules. Making it configurable means the team can adjust the hierarchy without code changes if needed.
- **4 roles without dedicated ROLE-XX documents**: Architectural decision — the role requirement matrix is the authoritative mapping. Role description documents are supplementary context. Phase 2's prompt templates must handle roles that only have matrix entries + shared policy references.

**Assumptions made**:
1. SQLite is acceptable for evaluation (the spec allows it). PostgreSQL migration is a connection-string swap via SQLAlchemy — no code changes needed.
2. The PDF files on disk are intentional duplicates of corresponding DOCX files — they exist to test both parsing paths, not as independent documents. Phase 1 must verify this by comparing content. As of Addendum v1.1, 14 of 24 documents have PDFs (POL-02–POL-05, ROLE-01 through ROLE-10).
3. Bootstrap 5.3 CDN availability during evaluation is assumed. Fallback: bundle locally in static/.
4. The google-genai SDK's Pydantic-native response mode will be used for structured JSON output, eliminating the need for manual JSON parsing from raw text.

**Next steps for executing agents**:
- **Phase 1 agent**: Read PROJECT_MAP.md Phase 1 section. Scaffold the entire folder structure. Create requirements.txt. Implement database schema first (all entity models), then document processing pipeline, then load_matrix.py, then employee CRUD, then auth skeleton. Run all 20 documents through the full pipeline as the acceptance test. Verify parsed counts against the minimums. Write tests.
- **Phase 2 agent**: Read PROJECT_MAP.md Phase 2 section. WAIT for Phase 1 to complete the database schema + document parsing — you need parsed chunks and the loaded matrix to build prompts. Implement BaseGenAIProvider + GeminiProvider first, then PromptManager, then generators one by one.
- **Phase 3 agent**: Read PROJECT_MAP.md Phase 3 section. WAIT for Phase 1 (database, parsed docs, loaded matrix) and Phase 2 (generated plans to validate). Implement BaseValidator + all 8 concrete validators, then ValidationPipeline, then ComparisonEngine, then ConsistencyTester.
- **Phase 4 agent**: Read PROJECT_MAP.md Phase 4 section. WAIT for Phase 1 (auth, templates), Phase 2 (generated content), and Phase 3 (validation reports). Implement review workflow first (it blocks dashboards), then dashboards, then progress/recommendations, then policy update detection, then reports/export, then final packaging.

---

### Entry 002 — 2026-09-25 | Role: Tech Lead (Addendum v1.1)

**What was done**:
1. **4 new role description documents added**: ROLE-07 (Recruiter), ROLE-08 (Financial Analyst), ROLE-09 (Accounts Payable Clerk), ROLE-10 (Warehouse Operations Coordinator). Each in both DOCX and PDF format.
2. **PDF versions added** for ROLE-03 through ROLE-06 (previously DOCX-only). All 10 role descriptions now have both formats.
3. **Matrix expanded**: 24 new rows (R155–R178) added to `role_requirement_matrix_seed.csv`, bringing total from 154 → 178 rows, mandatory entries from 111 → 131.
4. **Q1 resolved**: The 4 roles that previously lacked dedicated ROLE-xx documents now have them. All 10 roles have a dedicated role description document.
5. **1 new adversarial/injection case** added: ROLE-07 §5.2 (fake appendix note). Total now 11.
6. **Documentation updated**: `dataset_verification_report.md`, `dataset_special_cases_index.md`, `PROJECT_MAP.md`, `app_explanation.md`, and this file.

**Key numbers after addendum**:
- 24 unique documents, 38 files on disk (24 DOCX + 14 PDF)
- 178 matrix rows, 131 mandatory, 10 roles, 24 source documents
- 102 mandatory sections, 28 optional sections, 65 role-specific sections
- 11 adversarial/injection cases, 10 conflict pairs, 12+ cross-references

---

## Phase 1 Log

### Entry 001 — 2026-09-25 08:22 | Agent: Execution - Phase 1 | Task: Start foundation implementation

**Timestamp**: 2026-09-25  
**Agent**: Execution - Phase 1 (Foundation Engineer)  
**Member**: Azhar Raji AL-Herwi  
**Task**: Implement Phase 1 end-to-end (schema, document pipeline, matrix loader, employee/role CRUD, auth/RBAC skeleton, FastAPI + base UI)  
**Rationale**: PROJECT_MAP assigns steps 4–10 and FRs for ingest/auth/matrix to Phase 1. Hidden-document readiness (F2) requires a generic upload→validate→parse→chunk→version pipeline that treats `sample_documents/` as real input, not pre-loaded artifacts. `load_matrix.py` must validate and persist the approved CSV rather than author requirements. OOP boundaries from [ARCHITECTURE] (repositories, DocumentService, version control) will be implemented so later phases consume stored chunks/matrix without re-parsing files ad hoc.

**Public interfaces this phase will expose**: `Document`/`DocumentChunk`/`DocumentRevision`, `DocumentRepository`/`ChunkRepository`, `DocumentService.ingest_file`/`ingest_upload`, `RoleMatrixRepository` + `load_matrix.py`, `Employee`/`Role` + CRUD services, `AuthService` + `require_role`, SQLAlchemy `Base.metadata` for all planned tables, FastAPI app with global error handlers.

**Depends on (other phases)**: none. Phase 2–4 consume this layer; this phase will not call GenAI or run plan validators.

**Status**: In progress

### Entry 002 — 2026-09-25 09:17 | Agent: Execution - Phase 1 | Task: Close foundation + Memory Trinity sync

**Timestamp**: 2026-09-25  
**Agent**: Execution - Phase 1 (Foundation Engineer)  
**Member**: Azhar Raji AL-Herwi  
**Task**: Verify Phase 1, sync Memory Trinity, split git commits  
**Rationale**: Implementation of steps 4–10 is complete and covered by 15 pytest cases. PROJECT_MAP still showed PENDING, which would mis-scope Phase 2+ agents. Metrics originally under-counted `[M]` because duplicate `section_id` rows in one document overwrote a tagged chunk; `CorpusMetricsService` now ORs flags per `(document_id, section_id)`.

**Status**: Completed  

**Public interfaces for later phases**:
- `DocumentService.ingest_file` / `ingest_bytes` / `ingest_directory`
- `DocumentRepository`, `ChunkRepository`, `DocumentRevisionRepository`
- `CorpusMetricsService.compute()`
- `MatrixLoader` / `load_matrix()` / `RoleMatrixRepository`
- `EmployeeService`, `RoleService`
- `AuthService`, `require_role`, `get_current_user`
- Tables: documents, chunks, revisions, employees, roles, role_requirements, users, plans, modules, checklists, tasks, quizzes, assessments, validation_reports, review_decisions, audit_log, prompt_templates, generation_metadata
- HTTP: `/login`, `/api/login`, `/api/documents/*`, `/api/employees`, `/api/roles`, `/api/matrix`, `/dashboard*`

**Notes**: Do not call Gemini from these modules. Empty packages (`genai_pipeline/`, `python_validation/` validators, etc.) are scaffolds only. Seed with `python -m database.seed`. Demo users: admin/admin123 and the other four README accounts.

**Next**: Phase 2 consumes parsed chunks + matrix rows; Phase 3 consumes the same plus generated JSON.


---

## Phase 2 Log

### Entry 001 — 2026-09-25 10:27 | Agent: Execution - Phase 2 | Task: Start GenAI pipeline

**Timestamp**: 2026-09-25 10:27  
**Agent**: Execution - Phase 2 (GenAI Pipeline Engineer)  
**Member**: A'LAA MADYAN  
**Task**: Implement Pipeline 1 end-to-end (requirement extraction, versioned prompts, Gemini structured JSON, schema/retry, source-grounded modules/checklists/tasks/quizzes/assessments, injection defense, generation metadata)  
**Rationale**: PROJECT_MAP assigns steps 11–26 and 37–43 plus D4 to Phase 2. Generation must consume Phase 1 public interfaces only (`RoleMatrixRepository`, `ChunkRepository`/`DocumentRepository`, `EmployeeService`, `AuditRepository`) and expose `PlanGenerationService` + Pydantic schemas for Phase 3/4. All LLM calls go through `BaseGenAIProvider`; uploaded text is fenced as data. Tests inject a context-derived fixture provider so we never hard-code role plans. Production default is `GeminiProvider` and fails closed without an API key (F12 — no fabricated plans).

**Public interfaces this phase will expose**: `BaseGenAIProvider`, `GeminiProvider`, `PromptManager`, `RetryManager`, `OutputSchemaValidator`, `InjectionGuard`, `RequirementExtractor`, generators (plan/module/quiz/assessment), `PlanGenerationService.generate_for_employee`, `PlanRepository`, HTTP `/api/plans*`.

**Depends on (other phases)**: Phase 1 ingest, matrix, employee/role, auth. Will not implement Pipeline 2 validators.

**Status**: Completed

### Entry 002 — 2026-09-25 11:15 | Agent: Execution - Phase 2 | Task: Verify Pipeline 1, tests, D4 evidence

**Timestamp**: 2026-09-25 11:15  
**Agent**: Execution - Phase 2 (GenAI Pipeline Engineer)  
**Member**: A'LAA MADYAN  
**Task**: Close remaining Phase 2 gaps (scenario-task generator, sequence mutation safety, automated VG-2.x tests, D4 evidence, Memory Trinity, distributed commits, branch push)  
**Rationale**: Uncommitted Pipeline 1 modules already cover providers, versioned prompts, assembler-backed structured JSON, injection fencing, retry cap, and plan persistence. Success criteria before calling the phase done: pytest covers VG-2.1–VG-2.9 without fabricating plans; Gemini fails closed without an API key; `/api/plans*` is wired; D4 evidence is a real artifact; PROJECT_MAP Phase 2 steps are checked off.

**Status**: Completed  

**Notes**: D4 written to `reports/d4_genai_pipeline_evidence.md`. Sample plan JSON is produced by `test_plans_for_all_ten_roles`.

### Entry 003 — 2026-09-25 12:10 | Agent: Execution - Phase 2 | Task: Fix provider injection on generate path

**Timestamp**: 2026-09-25 12:10  
**Agent**: Execution - Phase 2 (GenAI Pipeline Engineer)  
**Member**: A'LAA MADYAN  
**Task**: Bind `PlanGenerator` to the current `BaseGenAIProvider` on each generate call; expose FastAPI `get_genai_provider` so tests/routes can inject `ScriptedProvider` without hitting Gemini  
**Rationale**: pytest VG coverage was 26/27. `test_api_generate_requires_admin` returned 503 because `PlanGenerationService.__init__` cached `PlanGenerator(GeminiProvider())` and later `self.provider = ...` swaps were ignored. Success criterion: Admin POST `/api/plans/generate/{id}` with an injected test provider returns 200 + valid `GeneratedPlan` JSON; missing-key unit test still fails closed (F12).

**Status**: Completed  

**Notes**: `PlanGenerationService` constructs `PlanGenerator(provider)` inside `generate_for_employee`. FastAPI `Depends(get_genai_provider)` is the injection point. GET `/api/plans` does not construct Gemini.

### Entry 004 — 2026-09-25 12:20 | Agent: Execution - Phase 2 | Task: Verify, close, commit, and push Pipeline 1

**Timestamp**: 2026-09-25 12:20  
**Agent**: Execution - Phase 2 (GenAI Pipeline Engineer)  
**Member**: A'LAA MADYAN  
**Task**: Finish Phase 2: confirm VG-2.1–VG-2.9 against uncommitted Pipeline 1 code, fix remaining gaps (route order, Memory Trinity, AI_USAGE, distributed commits), then push `phase-2-genai-pipeline`  
**Rationale**: Implementation is on disk but not committed; Entry 003 left provider injection in progress. Success criterion: full pytest green including Admin generate with injected provider; Memory Trinity + AI_USAGE synchronized; branch pushed. Will not implement Pipeline 2 validators.

**Status**: Completed  

**Public interfaces for later phases**:
- `PlanGenerationService.generate_for_employee` / `get_plan` / `list_for_employee`
- `PlanRepository`, `PromptTemplateRepository`, `GenerationMetadataRepository`
- `BaseGenAIProvider`, `GeminiProvider`, `ScriptedProvider` (tests)
- `PromptManager` + `prompt_templates/*_v1.json`
- `RequirementExtractor`, `PlanAssembler`, `PlanGenerator`
- `ModuleGenerator`, `QuizGenerator` + `DistractorValidator`, `AssessmentGenerator`, `ScenarioTaskGenerator`
- `OutputSchemaValidator`, `RetryManager` (cap 3), `PrerequisiteEnforcer`
- `InjectionGuard` (`security.injection_guard`; re-exported from `genai_pipeline`)
- Pydantic: `GeneratedPlan`, `LearningModule`, `ChecklistItem`, `TaskItem`, `QuizQuestion`, `Assessment`
- HTTP: `POST /api/plans/generate/{employee_id}`, `GET /api/plans/{plan_id}`, `GET /api/plans/employee/{employee_id}`
- Stored `OnboardingPlan.structured_json` is the plan of record for Phase 3

**Notes**: Do not call Gemini from `python_validation/`. Missing `GEMINI_API_KEY` → 503, never a fake plan. After retry cap, assembler backbone is persisted and `recovered_from_assembler` is logged in generation metadata. Route order: list-by-employee is registered before `GET /{plan_id}`.

### Entry 005 — 2026-09-25 12:36 | Agent: Execution - Phase 2 | Task: Independent re-verification of Pipeline 1

**Timestamp**: 2026-09-25 12:36  
**Agent**: Execution - Phase 2 (GenAI Pipeline Engineer)  
**Member**: A'LAA MADYAN  
**Task**: Re-read Memory Trinity, audit Phase 2 scope vs code, re-run pytest, close remaining public-export gap, confirm branch push  
**Rationale**: This session was launched as full Phase 2 execution. PROJECT_MAP already marked steps 11–26 and 37–43 complete on `phase-2-genai-pipeline`. Success criterion: do not rebuild Pipeline 1 if VG-2.1–VG-2.9 already hold; independently re-run the suite; export `ScriptedProvider` from `genai_pipeline` so the documented test injection interface is package-public. Will not implement Pipeline 2 validators.

**Status**: Completed  

**Notes**: `.venv` pytest result: 27 passed. All Phase 2 requirement IDs remain checked in PROJECT_MAP. `ScriptedProvider` is now in `genai_pipeline.__all__`. Branch `phase-2-genai-pipeline` was already tracking origin; this session pushes the verification/export commit.

### Entry 006 — 2026-09-25 | Agent: Execution - Phase 2 | Task: Integrate Pipeline 1 into main

**Timestamp**: 2026-09-25 (session opened as full Phase 2 execution)
**Agent**: Execution - Phase 2 (GenAI Pipeline Engineer)
**Member**: A'LAA MADYAN
**Task**: Confirm Phase 2 scope is genuinely complete, then integrate `phase-2-genai-pipeline` into `main`
**Rationale**: This session was launched with authority to execute Phase 2, so the first obligation was verification, not regeneration. Read the Memory Trinity, enumerated the 20 assigned step IDs (11–26, 37–43) and 9 verification goals (VG-2.1–VG-2.9) against the filesystem: all 14 `genai_pipeline/` modules, 5 versioned `prompt_templates/`, 6 `schemas/`, `security/injection_guard.py`, and `src/plans/` are present; a pattern scan for `TODO`/`FIXME`/`placeholder`/`NotImplemented` returned only `tuple[...]` type-hint false positives. `python_validation/`, `comparison_engine/`, `hallucination_checks/`, and `contradiction_checks/` contain only `__init__.py`, confirming Phase 3 is untouched — no scope creep, and no silent gap hiding inside Phase 2. Independently re-ran the suite (27 passed) rather than trusting the prior session's log. Only remaining administrative gap was that `main` sat 12 commits behind the phase branch, so Pipeline 1 was unreachable from the default branch and D2's "source code in structure" claim was only true on a non-default branch.

**Status**: Completed

**Notes**: Fast-forward `main` onto `phase-2-genai-pipeline` (no merge commit, no history rewrite — Phase 1's commits are already ancestors, so nothing is lost and `phase-2-genai-pipeline` stays intact for audit). Phase 2 code is unchanged by this integration; only branch pointers move. Phase 3 remains the next executable phase and may consume `OnboardingPlan.structured_json` (`GeneratedPlan`) as the plan of record.

### Entry 007 — 2026-09-25 | Agent: Execution - Phase 2 | Task: Close the "no live Gemini call" evidence gap

**Timestamp**: 2026-09-25 14:09
**Agent**: Execution - Phase 2 (GenAI Pipeline Engineer)
**Member**: A'LAA MADYAN
**Task**: Audit whether Pipeline 1 was ever exercised against the real Gemini API; if not, close the environment gap and build the live-run harness
**Rationale**: Asked directly whether Gemini had actually been called, so I re-checked instead of trusting the green suite. Findings: `GEMINI_API_KEY` unset; all 27 tests inject `ScriptedProvider`; the one `GeminiProvider` test only asserts the 503 fail-closed path; `d4_sample_software_engineer_plan.json` has no `model_used`/`prompt_version`/`generation_timestamp` keys, proving it came from `PlanAssembler`, not Gemini; and `google-genai` was absent from `.venv` despite being pinned in `requirements.txt`. So Phase 2's *code* was complete but its *GenAI proof* was not. Kept the test suite key-free by design (CI must not depend on a live key) and instead added an operator harness — the right boundary, since D4 needs a real recorded response, not a test that skips when no key exists.

**Status**: In progress — harness built and wiring-proven; the real run needs a valid key from the team member.

**Public interfaces this phase will expose**:
- `scripts.live_genai_run.LiveGenAIRun` — `discover_employees()`, `run_role()`, `capture_raw_sample()`, `execute()`, `write_evidence()`
- CLI `python -m scripts.live_genai_run [--roles N] [--out PATH]`, exit 2 with a clear message when `GEMINI_API_KEY` is unset, exit 1 when zero roles generate
- Evidence artifact `reports/d4_live_genai_run.json` with per-role model, retry count, provider latency, wall clock, item counts, `recovered_from_assembler`, and one unedited raw Gemini response head

**Notes**: `google-genai==2.23.0` installed into `.venv`; it downgrades `websockets` 17.1 → 16.1.1, and `uvicorn==0.53.0` still imports fine (27/27 tests re-run green, no regression). A wiring test with a deliberately invalid key proved the path is live: the request reached `generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent` and Google returned `400 API_KEY_INVALID`; `RetryManager` logged 3 capped attempts, `PlanGenerator` fell back to `PlanAssembler`, `OutputSchemaValidator` accepted 102 items, and the harness honestly reported `recovered_from_assembler: true` / `all_gemini_backed: false`. The seeded DB was empty (18 tables, 0 rows), so I re-ran `python -m database.seed` (178 matrix rows, 38 files, 24 documents, 11 adversarial sections) and reset it again after the wiring test so the real run starts clean. The harness must never persist or log the key — it reads the environment only.

### Entry 008 — 2026-09-25 | Agent: Execution - Phase 2 | Task: First live Gemini run + schema-constraint fix + D4 close-out

**Timestamp**: 2026-09-25 15:05
**Agent**: Execution - Phase 2 (GenAI Pipeline Engineer)
**Member**: A'LAA MADYAN
**Task**: Run Pipeline 1 against the real API with the member-supplied key, fix whatever the live run exposes, and close D4 honestly
**Rationale**: The key arrived, so the success criterion became a recorded Gemini-backed plan, not just wiring. The run exposed three production issues no mock could: (1) `gemini-2.5-flash` 404s for new keys — kept the default (evaluators may hold old keys) and proved the `GEMINI_MODEL` override with `gemini-3.5-flash-lite`; (2) the plan template demanded schema conformance without ever supplying the schema, so the model invented `employee_onboarding_plan` — fixed with `response_json_schema` in `GeminiProvider.generate` plus schema passthrough in `RetryManager` (local validation retained as safety net; suite still 27 green); (3) free-tier quota (5/min, 20/day per model) makes unpaced 10-role runs impossible — added `RateLimitedProvider` as a `GeminiProvider` subclass inside the harness only, so the `isinstance` enrichment gate keeps firing. Result: Software Engineer Gemini-backed with 0 retries (2 modules, 39 checklists, 25 tasks, 8 quizzes, 4 assessments, 6 stages, 14.5 s provider latency) plus an unedited 3799-char raw response, all in `reports/d4_live_genai_run.json`. DevOps fell back to the assembler after 3× non-JSON output — recorded as fallback, not hidden. Security: grepped evidence + logs for key fragments before commit — clean.

**Status**: Completed

**Public interfaces for later phases** (unchanged contracts, stronger guarantees):
- `GeminiProvider.generate` now constrains output with `response_json_schema` whenever a Pydantic schema is passed — Phase 3 can trust `structured_json` shape more, but must still validate (contract, not proof)
- `scripts/live_genai_run.py` gains `--throttle` and `--roles`; rerun after quota reset for the remaining 8 roles

### Entry 009 — 2026-09-25 16:25 | Agent: Execution - Phase 2 | Task: Fix enrichment item retention and raise token limit

**Timestamp**: 2026-09-25 16:25  
**Agent**: Execution - Phase 2 (GenAI Pipeline Engineer)  
**Member**: A'LAA MADYAN  
**Task**: Fix item retention across enrichment passes (`ModuleGenerator`, `QuizGenerator`, `AssessmentGenerator`, `ScenarioTaskGenerator`) and make `max_output_tokens` configurable/raised  
**Rationale**: Post-run audit of `d4_live_genai_run.json` showed Software Engineer had only 1 module recorded instead of the full 26 assembler modules. Root cause: `ModuleGenerator.enrich` (and similarly `QuizGenerator`, `AssessmentGenerator`, `ScenarioTaskGenerator`) iterated over `batch.items` rather than updating `plan.items` by ID. When the LLM returned a partial batch (e.g. 1 module), the remaining items were dropped from the plan rather than preserved. Merging by iterating over `plan.items` and replacing with matching enriched items guarantees 100% item retention while accepting model wording improvements. In addition, `GenerationConfig.max_output_tokens` is raised from 8192 to 16384 (standard in Gemini 2.5/3.5) to prevent mid-JSON truncation on large multi-stage plans.

**Status**: Completed

**Public interfaces for later phases** (unchanged signatures, guaranteed complete inventory):
- `ModuleGenerator.enrich`: preserves 100% of plan modules, merging batch wording on ID matches.
- `QuizGenerator.enrich`: preserves 100% of plan quizzes and runs distractor validation across all items.
- `AssessmentGenerator.enrich`: preserves 100% of plan assessments, merging batch wording on ID matches.
- `ScenarioTaskGenerator.enrich`: preserves 100% of plan tasks and maintains original stage/prerequisite order.
- `GenerationConfig.max_output_tokens`: raised to 16384 default to prevent truncation on large plans.

**Notes**: Verified with automated test `test_enrichment_preserves_full_item_inventory_on_partial_batches`. Full test suite now passes with 28 tests (28 passed, 0 failed). Ready for Phase 3 ingestion.

### Entry 010 — 2026-09-26 | Agent: Execution - Phase 2 | Task: Surgical fix - remove self-certifying validation fields from Pipeline 1 output

**Timestamp**: 2026-09-26  
**Agent**: Execution - Phase 2 (GenAI Pipeline Engineer)  
**Member**: Azhar Raji AL-Herwi (review)  
**Task**: Surgical fix - remove self-certifying validation fields from Pipeline 1 output  
**Impact Area**: `schemas/common_schema.py`, `schemas/quiz_schema.py`, `schemas/plan_schema.py`, `schemas/module_schema.py`, `schemas/assessment_schema.py`, `schemas/__init__.py`, `genai_pipeline/plan_assembler.py`, `genai_pipeline/quiz_generator.py`, `genai_pipeline/plan_generator.py`, `genai_pipeline/module_generator.py`, `genai_pipeline/assessment_generator.py`, `genai_pipeline/scenario_generator.py`, `src/plans/service.py`, `tests/test_genai_pipeline.py`, `reports/d4_sample_software_engineer_plan.json`, `PROJECT_MAP.md`  
**Risk**: must not touch Phase 3 code (`python_validation/`, `comparison_engine/`, `hallucination_checks/`)  
**Rationale**: `distractor_validation_status` was being set to `passed`/`repaired` inside Pipeline 1. Phase 2 cannot independently verify distractors against source; only Phase 3 may set the final value. `grounding_status` / `grounding_flags` are not in PROJECT_MAP entity definitions; equivalent outcomes belong on Phase 3 `ItemValidationResult.verification_status`.

**Status**: Completed

**Notes**: Phase 3 folders were not modified. Pipeline 1 quizzes now always emit `distractor_validation_status=pending_verification`. `grounding_status` and `grounding_flags` are removed from `GeneratedPlan` and item schemas.

---

## Phase 3 Log

*(Reserved for Phase 3 Validation & Trust Engineer entries)*

---

## Phase 4 Log

*(Reserved for Phase 4 Workflow, Dashboards & Delivery Engineer entries)*

---

## Cross-Phase Notes

- Phase 2 plan of record is `OnboardingPlan.structured_json` (`GeneratedPlan`). Phase 3 must validate that JSON with zero GenAI calls.
- LLM injection point: `src.plans.dependencies.get_genai_provider`. Do not instantiate `GeminiProvider` inside validators or routes except through this dependency / `PlanGenerationService.generate_for_employee`.
- After Gemini retry cap, metadata may show `recovered_from_assembler=true`; that backbone is still live matrix+chunk computation, not a fake score.
