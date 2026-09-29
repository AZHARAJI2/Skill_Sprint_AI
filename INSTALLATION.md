# D11 — Installation Instructions

## Prerequisites

- Python 3.12 or newer.
- Git.
- A Command Code API key for live-plan generation. The key is optional for UI,
  document, validation, and demo-draft evaluation.

## Local installation

From the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m database.seed
```

`database.seed` creates the schema, loads the company corpus and role matrix,
provisions evaluator accounts, and creates ten source-grounded **review-only**
demo drafts. It does not add an API key or fabricate a live GenAI response.

## Configure live GenAI

Set these only in the terminal or backend-host secret manager. Never commit
them, put them in browser JavaScript, or configure the key in Netlify.

```powershell
$env:SKILLSPRINT_GENAI_PROVIDER = "commandcode"
$env:CMD_API_KEY = "replace-with-your-key"
$env:COMMAND_CODE_MODEL = "deepseek/deepseek-v4-flash"
$env:SKILLSPRINT_GENAI_PARALLEL_WORKERS = "3"
$env:SKILLSPRINT_COMMAND_CODE_TIMEOUT_SECONDS = "0"
$env:SKILLSPRINT_PLAN_TIMEOUT_SECONDS = "0"
```

For public deployment, follow [DEPLOYMENT.md](DEPLOYMENT.md): FastAPI and
PostgreSQL are hosted separately from Netlify, which acts as the public proxy.

## Verify the installation

```powershell
python -m pytest -q
uvicorn src.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/login`. The default evaluator accounts are in
[hidden_test_ready/evaluator_credentials.md](hidden_test_ready/evaluator_credentials.md).
