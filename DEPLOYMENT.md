# Deploy SkillSprint AI on Render Free

This project is configured for a **Render Free Web Service** with a separate
**Render Free PostgreSQL** database. The application is stateless: employees,
plans, validation reports, reviews, audit records, parsed document sections,
and the role matrix are stored in PostgreSQL rather than in SQLite or the web
service filesystem.

Read Render's current [Free-instance limits](https://render.com/docs/free)
before deploying. A free deployment is appropriate for an evaluator demo, not
for production employee data.

## What a fresh deployment creates

`bash build.sh` runs `python -m database.seed_render`. On an empty database it
creates the schema and the reproducible evaluation dataset:

- 11 approved demonstration job roles and 1,013 employee profiles
- an Employee login for every seeded profile, plus Admin, Training Manager,
  Reviewer, and Manager accounts
- the committed 178-row role matrix and all committed sample documents
- parsed chunks, injection-scan findings, audit entries, and 10
  source-grounded **manual-review demo drafts** (one for every demo role)

The plans are generated from the committed corpus and matrix during seeding.
They are deliberately labelled as review-only demo drafts, not as live GenAI
plans or approved training evidence. `database.seed_render` does not overwrite
an existing database, so later deploys preserve imported employees, live plans,
and progress.

To create this same demo data locally, run:

```powershell
.\.venv\Scripts\python.exe -m database.seed
```

The local `data/skillsprint.db` is intentionally ignored by Git. It and any
locally imported private employees are not copied to GitHub or a new Render
database. Import those employees into the deployed application only when you
are authorized to place their data there.

## Deploy with the Blueprint

1. Push the repository, including `render.yaml`, to GitHub.
2. In Render, choose **New → Blueprint** and select that repository.
3. Render creates `skillsprint-db` and `skillsprint-ai`; use the same region
   for both.
4. Add `CMD_API_KEY` in the Web Service environment page. Never commit it.
5. Open `https://YOUR-SERVICE.onrender.com/health`, then open `/login`.

`render.yaml` passes Render's database connection string to
`SKILLSPRINT_DATABASE_URL`, generates `SKILLSPRINT_SECRET_KEY`, uses HTTPS-only
cookies, and runs `bash build.sh` so the setup does not depend on an executable
bit in Git. The production build installs the lean `requirements.txt`; test-only
packages remain in `requirements-dev.txt` and are not installed on Render.

## Manual setup instead of a Blueprint

Create one **PostgreSQL** database and one **Web Service** in the same region.
Use these Web Service values:

| Setting | Value |
|---|---|
| Runtime | Python |
| Build command | `bash build.sh` |
| Start command | `uvicorn src.main:app --host 0.0.0.0 --port $PORT` |
| Plan | Free |
| Health check | `/health` |

Set the following environment values:

```text
SKILLSPRINT_DATABASE_URL=<Render PostgreSQL connection string>
SKILLSPRINT_SECRET_KEY=<long random value>
SKILLSPRINT_COOKIE_SECURE=true
SKILLSPRINT_GENAI_PROVIDER=commandcode
CMD_API_KEY=<secret Command Code key>
COMMAND_CODE_MODEL=deepseek/deepseek-chat
SKILLSPRINT_COMMAND_CODE_TIMEOUT_SECONDS=0
SKILLSPRINT_PLAN_TIMEOUT_SECONDS=0
SKILLSPRINT_GENAI_MAX_RETRIES=2
SKILLSPRINT_ENABLE_GENAI_ENRICHMENT=false
SKILLSPRINT_GENAI_PARALLEL_WORKERS=3
SKILLSPRINT_STAGE_OUTPUT_TOKENS=5120
SKILLSPRINT_COMMAND_CODE_ZDR=false
SKILLSPRINT_UPLOAD_DIR=/tmp/skillsprint/uploads
SKILLSPRINT_LOG_DIR=/tmp/skillsprint/logs
```

## Free-tier storage and operational limits

| Concern | What this configuration does |
|---|---|
| Database data | Render Free Postgres provides 1 GB. It retains employees, plans, reviews, parsed chunks, and reports. It expires 30 days after creation and has no managed backup. Export a backup before expiry. |
| Uploaded original files | Free Web Services cannot attach a persistent disk. Uploaded PDFs/DOCX/etc. are parsed immediately and their text/chunks persist in Postgres; the original binary in `/tmp` can disappear on restart, deploy, or idle spin-down. |
| Web-service filesystem | Ephemeral. Never use SQLite, `/tmp`, or logs as the source of truth. |
| Idle behavior | A Free Web Service spins down after 15 idle minutes. Its next request can take about a minute while it starts. |
| Scale | Free allows one web-service instance. The application is configured as one FastAPI instance with PostgreSQL. |

The committed source corpus is about 1.5 MB, so the first seed easily fits.
The database limit is shared by documents and generated plans; monitor **Disk
Usage** in the Render database metrics. Do not upload large private document
collections or treat the free database as long-term production storage.

For persistent original documents in a real deployment, use a paid Render disk
or approved object storage, and keep PostgreSQL for relational data.

## Demo accounts

Change all of these before any non-evaluation deployment:

| Username | Password | Role |
|---|---|---|
| `admin` | `admin123` | Admin |
| `trainer` | `trainer123` | Training Manager |
| `reviewer` | `reviewer123` | Reviewer |
| `manager` | `manager123` | Manager |
| `employee` | `employee123` | Employee |

`employee` / `employee123` is the login linked to `EMP-001`. The remaining
seeded employees use the generated usernames shown in the Employees page and
initial password `SkillSprint!<employee_code>`.
