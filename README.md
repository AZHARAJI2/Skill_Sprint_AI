# SkillSprint AI

Generative AI onboarding intelligence for **NovaCart** (e-commerce and logistics).
The system ingests approved company documents, generates structured onboarding
plans (Phase 2), and independently validates them in pure Python (Phase 3).

## Phase 1 status

Foundation is implemented: document ingest pipeline, database schema, matrix
loader, employee/role CRUD, auth/RBAC skeleton, and responsive HTML shells.

## Phase 2 status

Pipeline 1 is implemented: requirement extraction, versioned prompt templates,
`CommandCodeProvider` (the default; fails closed without an API key), Pydantic JSON schemas,
capped retry, source-grounded plan/module/checklist/task/quiz/assessment
generation, injection fencing, and `/api/plans*` routes. Evidence: `reports/d4_genai_pipeline_evidence.md`.

## Requirements

- Python 3.12+
- Windows, macOS, or Linux

## Installation

```bash
py -3.12 -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
```

Set `CMD_API_KEY` (or `COMMAND_CODE_API_KEY`) in the environment before live
generation. The default Command Code model is `deepseek/deepseek-v4-flash-fast`.
Override it with `COMMAND_CODE_MODEL` only after confirming that model is
available to your Command Code account. The complete plan is divided into
three independent stage groups and generated concurrently, then merged and
validated by Python. The default waits for a complete provider response rather
than replacing it with an incomplete fallback at an arbitrary local deadline;
the model receives a compact wording-overlay request while Python retains the
complete source-grounded structure. Set
`SKILLSPRINT_PLAN_TIMEOUT_SECONDS=0` only while diagnosing a slow provider.

In PowerShell, set the server-side values in the same terminal before starting
the application (replace the placeholder with your real key):

```powershell
$env:SKILLSPRINT_GENAI_PROVIDER = "commandcode"
$env:CMD_API_KEY = "your-command-code-key"
$env:COMMAND_CODE_MODEL = "deepseek/deepseek-v4-flash-fast"
$env:SKILLSPRINT_GENAI_PARALLEL_WORKERS = "3"
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

The full reproducible D11 instructions are in [INSTALLATION.md](INSTALLATION.md).

Never put `CMD_API_KEY` in a frontend file, Netlify environment variable,
or Git commit. It belongs only in the FastAPI backend environment.

Set `SKILLSPRINT_GENAI_PROVIDER=deepseek` or `gemini` only to use an optional
direct-provider compatibility path.
Without a key the API returns 503 rather than inventing a plan.

## Seed demo data

Loads the committed current demonstration workforce (11 approved job roles and
1,013 employee profiles), an Employee account for each profile, 5 RBAC users, the
178-row matrix, and all files under `sample_documents/`. It also creates one
**source-grounded demo draft** for each of the ten Project Map evidence roles.
Those drafts are computed from the committed document corpus and matrix at seed
time; they are clearly marked for manual review and are never claimed to be a
live GenAI response or an approved plan. This makes a fresh GitHub clone
demonstrable without committing a mutable database file, secrets, or hard-coded
onboarding output.

The reproducible 1,013-employee seed check is documented in
[`reports/d10_scalability_seed_test.md`](reports/d10_scalability_seed_test.md).

```bash
python -m database.seed
```

Demo logins:

| Username | Password | App role |
|---|---|---|
| admin | admin123 | Admin |
| trainer | trainer123 | Training Manager |
| reviewer | reviewer123 | Reviewer |
| manager | manager123 | Manager |
| employee | employee123 | Employee |

## Add a second employee and create their plan

Sign in as `admin` or `trainer`, then choose **Add Employee**. Complete the
profile, select the existing job role, and optionally enable **Create employee
sign-in** to give that person a linked Employee account. After saving, the app
opens the plan-generation dialog for that exact employee. From the Administrator
Dashboard you can later use **Workspace**, **Generate**, or **Regenerate** on
any employee row.

An Employee account is linked to one employee profile and can read only that
profile and its plans; it cannot open another employee's plan by changing a URL.

## Run the web app

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Open http://127.0.0.1:8000/login

## Execution instructions

Use the seeded evaluator credentials shown above to sign in as `admin`.

1. Open **Documents** and upload an approved company document. Check that its
   parsed sections and metadata are available. If a document contains
   instruction-like content, view the persisted `Prompt Injection Detected`
   finding in the Hallucination/Security report.
2. Open **Roles** to create a role from an approved description, import the
   approved Role Requirement Matrix CSV, or submit a requirement for review.
3. Open **Employees** to create one employee or import CSV, XLSX, or JSON.
   JSON may be one object, an array, an `employees` wrapper, JSON Lines, or
   comma-separated employee objects. Each employee must use an existing role.
4. Choose **Generate Plan** for that employee. Pipeline 1 calls the configured
   GenAI provider; Pipeline 2 then validates coverage, traceability, source
   references, hallucinations, contradictions, sequencing, and role relevance.
5. Open the plan and Review Queue. An Admin, Training Manager, or Reviewer can
   approve, reject, edit, comment on, or regenerate items; the original result
   and the decision remain in the audit trail.
6. Open **Reports** to review the GenAI/Python comparison, hallucination and
   prompt-injection findings, contradictions, coverage, traceability, and
   progress results. Generate D6 only after complete live plans exist for all
   ten roles: `python -m scripts.generate_phase3_reports`.
7. Sign in as an employee to take assigned quizzes and view assessments. A
   trainer, manager, reviewer, or admin confirms practical-item completion and
   records final progress; employees cannot confirm their own completion.
8. Upload a newer policy version to run impact analysis. Use selective
   regeneration to regenerate only items citing that document, then review the
   refreshed validation result.
9. Export reports as required and run the complete automated suite with
   `python -m pytest -q`.

For the performance benchmark, deployment steps, and final evidence details,
see [EXECUTION.md](EXECUTION.md) and [DEPLOYMENT.md](DEPLOYMENT.md).

## Deployment

For the required public deployment, use Render PostgreSQL as the persistent
backend and deploy this FastAPI application as a Render Web Service. A fresh
Render database automatically receives the reproducible 11-role/1,013-employee
demo dataset and 10 review-only source-grounded drafts during `bash build.sh`.
The local SQLite database, original import files, credentials, and plans are
never pushed; only the reviewed profile-and-role snapshot is versioned for
reproducible evaluation. See [DEPLOYMENT.md](DEPLOYMENT.md) for the exact
environment variables, free-tier storage limits, and checks.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Public interfaces for later phases

- `DocumentService.ingest_file` / `ingest_bytes` / `ingest_directory`
- `DocumentRepository`, `ChunkRepository`, `DocumentRevisionRepository`
- `MatrixLoader` / `load_matrix` and `RoleMatrixRepository`
- `EmployeeService`, `RoleService`
- `AuthService`, `require_role`, `get_current_user`
- SQLAlchemy tables for plans, quizzes, reviews, and audit
- Phase 2: `PlanGenerationService.generate_for_employee`, `PlanRepository`,
  `BaseGenAIProvider` / `CommandCodeProvider`, `PromptManager`, `InjectionGuard`,
  Pydantic schemas in `schemas/`

Do not call a provider SDK or API from routes or validators. All LLM calls go through
`BaseGenAIProvider`. Do not put GenAI calls in `python_validation/` — that
pipeline must stay GenAI-free.
