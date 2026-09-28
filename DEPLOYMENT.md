# Production deployment: Netlify + FastAPI

`PROJECT_MAP.md` requires a host that supports FastAPI and a production-ready
PostgreSQL database. Netlify is therefore the public entry point, while the
stateful Python application runs on Render, Railway, PythonAnywhere, or another
FastAPI host. Do not deploy the application with SQLite to a serverless host:
employee records, audit history, uploaded documents, and generated plans must
survive a restart.

The included `netlify.toml` creates a same-origin Netlify proxy to the backend.
Users visit the Netlify URL while the FastAPI app continues to render the UI and
serve the API. Netlify's 200 rewrites preserve the browser URL while proxying to
the backend: https://docs.netlify.com/manage/routing/redirects/rewrites-proxies/

## 1. Deploy the FastAPI backend

Create a web service from this repository on a Python host and use:

```text
Build command: pip install -r requirements.txt
Start command: uvicorn src.main:app --host 0.0.0.0 --port $PORT
Health check: /health
```

Create a managed PostgreSQL database on the same provider or another trusted
provider. The application normalizes provider URLs automatically; set these
secrets in the backend host's dashboard, never in Git or Netlify:

```text
SKILLSPRINT_DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/skillsprint
SKILLSPRINT_SECRET_KEY=<long random value>
SKILLSPRINT_COOKIE_SECURE=true
SKILLSPRINT_GENAI_PROVIDER=commandcode
CMD_API_KEY=<your Command Code key>
COMMAND_CODE_MODEL=deepseek/deepseek-v4-flash
# Optional: leave unset (or set 0) to wait for Command Code without an application deadline.
# Set positive values only if you intentionally want a timeout.
SKILLSPRINT_COMMAND_CODE_TIMEOUT_SECONDS=0
SKILLSPRINT_PLAN_TIMEOUT_SECONDS=0
SKILLSPRINT_GENAI_MAX_RETRIES=3
SKILLSPRINT_GENAI_RETRY_BACKOFF_SECONDS=2
SKILLSPRINT_ENABLE_GENAI_ENRICHMENT=false
SKILLSPRINT_GENAI_PARALLEL_WORKERS=3
# Set true only after confirming the selected Command Code model supports ZDR.
SKILLSPRINT_COMMAND_CODE_ZDR=false
```

After the first successful deploy, open the provider shell once and run:

```text
python -m database.seed
```

Then open `https://YOUR-BACKEND/health`; it must return `status: ok` before
continuing. The PostgreSQL driver is included as `psycopg[binary]`.

## 2. Publish the Netlify entry point

In Netlify, import this same Git repository. Do not expose `CMD_API_KEY` in
Netlify. Under **Project configuration → Environment variables**, create only:

```text
SKILLSPRINT_BACKEND_URL=https://YOUR-BACKEND-HOST
```

Then deploy. `netlify.toml` runs `scripts/build_netlify_proxy.py`, which creates
a `200` rewrite for every path to the HTTPS backend. The proxy preserves the
Netlify URL for the login page, dashboards, document APIs, and plan APIs.

Netlify supports secrets in the project environment-variable UI rather than in
the repository, and a new deploy applies changed values:
https://docs.netlify.com/build/environment-variables/get-started/

## 3. Acceptance checks

1. Open `https://YOUR-SITE.netlify.app/health` and confirm the FastAPI health JSON.
2. Sign in with the evaluator account, then create an employee and generate one
   complete plan using Command Code.
3. Upload one allowed document and confirm it remains listed after a backend
   restart.
4. Complete one checklist item, submit a quiz, and confirm progress changes only
   after server-side persistence.
5. Confirm the browser source does not contain `CMD_API_KEY` or a quiz answer key.

## Operational notes

- Set a real `SKILLSPRINT_SECRET_KEY` before public deployment; the development
  default is not acceptable in production.
- Command Code balance/rate limits return a clear `429` response. It does not create
  a short plan; add balance or wait, then regenerate the complete plan.
  Temporary `503` overloads are retried up to three times with increasing delays.
- Uploaded files are confidential organization data. Keep the backend and
  PostgreSQL region/access controls appropriate for your evaluator and company.
