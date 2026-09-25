# SkillSprint AI

Generative AI onboarding intelligence for **NovaCart** (e-commerce and logistics).
The system ingests approved company documents, generates structured onboarding
plans (Phase 2), and independently validates them in pure Python (Phase 3).

## Phase 1 status

Foundation is implemented: document ingest pipeline, database schema, matrix
loader, employee/role CRUD, auth/RBAC skeleton, and responsive HTML shells.

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

## Run the web app

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Open http://127.0.0.1:8000/login

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
- SQLAlchemy tables for plans, quizzes, reviews, and audit (writers come later)

Do not call the Gemini SDK from business logic. Phase 2 owns `BaseGenAIProvider`.
Do not put GenAI calls in `python_validation/` — that pipeline must stay GenAI-free.
