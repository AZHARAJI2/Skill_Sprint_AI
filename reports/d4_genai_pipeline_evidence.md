# D4 — GenAI Pipeline Evidence (Phase 2)

**Owner**: Pipeline 1 / Phase 2  
**Company**: NovaCart  
**Date**: 2026-09-25

This file is the competition GenAI pipeline evidence (D4). Plans are computed live from
the role-requirement matrix and parsed chunks. They are **not** hard-coded per role.

## API / model

| Item | Value |
|---|---|
| SDK | `google-genai==2.23.0` |
| Provider class | `GeminiProvider` implementing `BaseGenAIProvider` |
| Default model | `gemini-2.5-flash` (`GEMINI_MODEL` override) |
| API key | `GEMINI_API_KEY` or `GOOGLE_API_KEY` (never committed) |
| Fail-closed | Missing key → HTTP 503 `AppError`; **no fabricated plan** |
| Retry cap | 3 attempts (`RetryManager.MAX_ATTEMPTS`) |
| Output MIME | `application/json` |

Tests inject `ScriptedProvider` so CI never depends on a live Gemini key. Production
`PlanGenerationService` defaults to `GeminiProvider`.

## Prompt templates (versioned files)

All prompts live under `prompt_templates/`, loaded by `PromptManager` (not string literals
in generators).

| File | Purpose |
|---|---|
| `onboarding_plan_v1.json` | Full structured plan JSON |
| `learning_module_v1.json` | Module wording enrichment |
| `quiz_generation_v1.json` | Quiz stem/options enrichment |
| `assessment_v1.json` | Assessment + rubric enrichment |
| `scenario_task_v1.json` | Scenario-task wording from approved processes |

Every stored plan records `prompt_version` (e.g. `onboarding_plan_v1`), `model_used`,
`generation_timestamp`, and `source_doc_versions` on `OnboardingPlan` plus a
`generation_metadata` row (`retry_count`, `response_time_ms`, log payload).

## Structured output

The only accepted generation artifact is `schemas.plan_schema.GeneratedPlan` (Pydantic).
Free-form prose is never the plan of record. `OutputSchemaValidator` additionally checks:

- role match
- source_document_id + source_section_id in the corpus/matrix
- unique item IDs
- required vs optional checklist status
- all mandatory requirement IDs covered
- at least two onboarding stages (no Day-1 dump)

## Retry and recovery

1. `RetryManager` retries invalid JSON / schema failures up to **3** times and logs each attempt.
2. Auth / missing-key errors (401/403/503) are **not** retried.
3. After the cap, `PlanGenerator` recovers the Python `PlanAssembler` backbone (matrix + chunks)
   so the API still returns a source-grounded structured plan instead of a fake score or empty body.
4. Assembler recovery is recorded in generation metadata (`recovered_from_assembler`).

## Injection defense

`security.injection_guard.InjectionGuard` scans uploaded/parsed text, fences it as
`UNTRUSTED_DOCUMENT_DATA`, and redacts matched instruction sentences. Prompt templates
tell the model to treat fenced text as data only. Demonstrated against the 11 corpus
adversarial cases (VG-2.5 / step 43). Flagged excerpts are not used as policy facts.

## Sample artifacts

Pytest `test_plans_for_all_ten_roles` writes a live Software Engineer plan JSON to:

`reports/d4_sample_software_engineer_plan.json`

That file is produced from matrix rows + chunks at test time.

## Live Gemini run (2026-09-25, operator harness `scripts/live_genai_run.py`)

First real model calls in project history. Environment: `google-genai==2.23.0`,
model `gemini-3.5-flash-lite` via `GEMINI_MODEL` override, seeded SQLite
(178 matrix rows, 38 files, 24 documents). Machine evidence:
`reports/d4_live_genai_run.json` (key never persisted — env only).

| Item | Value |
|---|---|
| Roles generated | 2/2, 0 failures |
| Gemini-backed (model wording merged, `recovered_from_assembler: false`) | 1 — Software Engineer (plan_id 1): 2 modules, 39 checklists, 25 tasks, 8 quizzes, 4 assessments, 6 stages; retry_count 0; provider latency 14.5 s |
| Assembler fallback (`recovered_from_assembler: true`, correctly flagged) | 1 — DevOps/Infrastructure Engineer (plan_id 2): model returned non-JSON 3× (likely truncation of a large plan), retry cap behaved as designed, `OutputSchemaValidator` accepted 103 assembler items |
| Raw unedited Gemini response | Captured (`raw_gemini_sample.captured: true`, 3799 chars, parses as JSON, `prompt_version: onboarding_plan_v1`) |
| Total RetryManager retries | 0 on the Gemini-backed role |

### Findings only a live run could reveal

1. **Default model dead for new keys**: `gemini-2.5-flash` (the `GEMINI_MODEL`
   default) returns `404 NOT_FOUND — no longer available to new users`.
   The API itself pointed at `gemini-3.8-flash`; probing the key's model list
   (61 models) showed `gemini-3.5-flash-lite` as the working flash option.
   The default is intentionally **unchanged** — evaluators may hold older keys
   with `2.5-flash` access — and the override path (`GEMINI_MODEL`) is proven.
2. **Prompt never contained the schema**: `onboarding_plan_v1.json` said
   "output JSON matching the provided schema" but no schema was provided, so
   the model invented `{"employee_onboarding_plan": {...}}` (11→104 validation
   errors across retries). Fixed by passing `response_json_schema` from the
   Pydantic contract in `GeminiProvider.generate` and passing `schema` through
   `RetryManager` (still validated locally as a safety net). First attempt then
   succeeded with zero retries. Suite re-run: 27 passed.
3. **Free-tier quota is the binding constraint**: 5 req/min and 20 req/day per
   model. One role costs 5 model calls (plan + 4 enrichment passes), so the
   harness paces calls (`RateLimitedProvider`, a `GeminiProvider` subclass so
   the enrichment gate still fires) and honors server `retryDelay` on 429.
4. **Open hypothesis (unverified — quota exhausted)**: the DevOps non-JSON
   triple looks like response truncation; raising `max_output_tokens` from
   8192 may fix it, but the constant is deliberately **not** changed without a
   live verification run.

## HTTP surface for later phases

| Method | Path | RBAC |
|---|---|---|
| POST | `/api/plans/generate/{employee_id}` | Admin, Training Manager |
| GET | `/api/plans/{plan_id}` | Authenticated (employees: own only) |
| GET | `/api/plans/employee/{employee_id}` | Authenticated (employees: own only) |

Public Python interfaces: `PlanGenerationService.generate_for_employee`,
`BaseGenAIProvider`, `GeminiProvider`, `ScriptedProvider` (tests), `PromptManager`,
`RequirementExtractor`, `PlanAssembler`, `OutputSchemaValidator`, `InjectionGuard`.
Phase 3 must consume stored `structured_json` and must not call Gemini from validators.
