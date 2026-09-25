# AI Tool Usage Declaration — SkillSprint AI

> **Purpose**: Competition compliance document for judges. This file must be
> updated by the HUMAN team member after reviewing what any AI tool did.
> This is NOT the same as `agent_history.md` (which is internal engineering
> memory for AI agents).

## Usage Log

| Date | Tool | Purpose | File(s) Affected | Modification Performed | Test Performed | Verifying Team Member |
|---|---|---|---|---|---|---|
| 2026-09-24 | Antigravity IDE (Claude) | Architectural planning, Memory Trinity initialization | PROJECT_MAP.md, app_explanation.md, agent_history.md, AI_USAGE.md, requirements.txt | Created project architecture, phase ownership plan, tech stack decisions, folder structure specification | Manual review of all generated documents against competition spec | Azhar Raji AL-Herwi |
| 2026-09-25 | Cursor (Grok) | Phase 1 foundation implementation | `src/`, `database/`, `document_processing/`, `document_validation/`, `role_matrix/load_matrix.py`, `config/`, `templates/`, `static/`, `tests/`, README.md, PROJECT_MAP.md, app_explanation.md, agent_history.md | Built ingest→parse→chunk→version pipeline, SQLAlchemy schema, matrix loader, employee/role CRUD, JWT/RBAC skeleton, FastAPI + Jinja shells | `pytest` — 15 passed (corpus ingest 38 files, 178-row matrix, POL-02 v1/v2, 10-role CRUD, 5-role RBAC, schema tables) | Azhar Raji AL-Herwi |
| | | | | | | |

## Guidelines for Team Members

1. **Every AI interaction must be logged** — whether it's code generation, debugging, documentation, or research.
2. **Fill in the "Verifying Team Member" column** — this confirms a human reviewed and understood the AI output.
3. **"Test Performed" must be specific** — "tested it" is insufficient; describe what was tested and the outcome.
4. **All team members must have entries** — the competition requires meaningful contributions from everyone.
5. **Be honest about AI assistance** — the goal is transparency, not minimization. Using AI well is a strength; hiding it is disqualifying.
