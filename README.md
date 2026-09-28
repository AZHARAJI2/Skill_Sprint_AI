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
generation. The default Command Code model is `deepseek/deepseek-v4-flash`.
Override it with `COMMAND_CODE_MODEL` only after confirming that model is
available to your Command Code account. The complete plan is divided into
three independent stage groups and generated concurrently, then merged and
validated by Python. By default it waits for Command Code to finish; set
`SKILLSPRINT_PLAN_TIMEOUT_SECONDS` to a positive number only when an intentional
end-to-end deadline is required.

In PowerShell, set the server-side values in the same terminal before starting
the application (replace the placeholder with your real key):

```powershell
$env:SKILLSPRINT_GENAI_PROVIDER = "commandcode"
$env:CMD_API_KEY = "your-command-code-key"
$env:COMMAND_CODE_MODEL = "deepseek/deepseek-v4-flash"
$env:SKILLSPRINT_GENAI_PARALLEL_WORKERS = "3"
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Never put `CMD_API_KEY` in a frontend file, Netlify environment variable,
or Git commit. It belongs only in the FastAPI backend environment.

Set `SKILLSPRINT_GENAI_PROVIDER=deepseek` or `gemini` only to use an optional
direct-provider compatibility path.
Without a key the API returns 503 rather than inventing a plan.

## Seed demo data

Loads 10 job roles, 10 demo employees, 5 RBAC users, the 178-row matrix, and
ingests all files under `sample_documents/`.

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

## Deployment

For the required public deployment, use Netlify as the public entry point and
a FastAPI host with PostgreSQL as the persistent backend. See
[DEPLOYMENT.md](DEPLOYMENT.md) for the exact environment variables and checks.

## Tests

```bash
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
