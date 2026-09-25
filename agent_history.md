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

*(Reserved for Phase 1 Foundation Engineer entries)*

---

## Phase 2 Log

*(Reserved for Phase 2 GenAI Pipeline Engineer entries)*

---

## Phase 3 Log

*(Reserved for Phase 3 Validation & Trust Engineer entries)*

---

## Phase 4 Log

*(Reserved for Phase 4 Workflow, Dashboards & Delivery Engineer entries)*

---

## Cross-Phase Notes

*(For issues, blockers, or decisions that span multiple phases)*
