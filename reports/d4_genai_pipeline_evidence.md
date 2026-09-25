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

## HTTP surface for later phases

| Method | Path | RBAC |
|---|---|---|
| POST | `/api/plans/generate/{employee_id}` | Admin, Training Manager |
| GET | `/api/plans/{plan_id}` | Authenticated (employees: own only) |
| GET | `/api/plans/employee/{employee_id}` | Authenticated (employees: own only) |

Public Python interfaces: `PlanGenerationService.generate_for_employee`,
`BaseGenAIProvider`, `PromptManager`, `RequirementExtractor`, `PlanAssembler`,
`OutputSchemaValidator`, `InjectionGuard`. Phase 3 must consume stored
`structured_json` and must not call Gemini from validators.
