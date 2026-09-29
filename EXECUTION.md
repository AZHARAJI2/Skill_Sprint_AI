# D12 — Execution Walkthrough

## 1. Start and sign in

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/login` and sign in as `admin` / `admin123`.
Change all demo passwords before a public deployment.

## 2. Demonstrate documents and prompt-injection safety

1. Open **Documents** and upload an approved PDF, DOCX, TXT, Markdown, or CSV.
2. If the uploaded text contains instruction-like content, it is retained as
   untrusted evidence, fenced before any GenAI prompt, and is listed in the
   hallucination/security report as `Prompt Injection Detected`.
3. Open **Reports → Hallucination / Security** to view the persisted finding.

## 3. Create an employee and generate a plan

1. Open **Employees → Add Employee** or import CSV/XLSX/JSON.
2. Select an existing job role, then create the employee account if needed.
3. From the employee row, select **Generate plan**. The application runs
   Pipeline 1 (live GenAI) then Pipeline 2 (pure-Python validation).
4. A fallback/review draft can never be used for employee progress. Regenerate
   it after the provider is available.

## 4. Benchmark real performance

Run this after setting `CMD_API_KEY`; it uses the production generation and
validation services and saves no key:

```powershell
python -m scripts.benchmark_live_plan --employee-code EMP-001
```

The command exits `0` only when a complete non-fallback live plan finishes in
30 seconds or less. A completed but slower plan is written as
`completed_over_srs`, rather than being mislabelled as a failed generation. It
writes the measured evidence to
`reports/d7_live_plan_benchmark.json`. A nonzero exit is evidence of a failed
benchmark, not a successful plan.

## 5. Create and review ten live plans

Create one complete live plan for each of the ten seeded roles, then have an
Admin, Training Manager, or Reviewer inspect and approve/reject/edit it in the
Review Queue. Do not approve source-grounded demo drafts as if they were live
GenAI outputs.

When all ten live plans exist, generate the valid cross-role comparison report:

```powershell
python -m scripts.generate_phase3_reports
```

The command deliberately refuses to overwrite D6 if a role lacks a complete
non-seed live plan. This prevents the previous false 100% comparison claim.

## 6. Final checks

```powershell
python -m pytest -q
```

Follow the acceptance checklist in
[reports/d18_final_submission_checklist.md](reports/d18_final_submission_checklist.md),
then deploy using [DEPLOYMENT.md](DEPLOYMENT.md).
