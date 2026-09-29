# D9 — Security Testing Report

> **System**: SkillSprint AI / NovaCart  
> **Scope**: application-layer security controls exercised by the automated test suite  
> **Date**: 2026-09-29  
> **Result**: 151 automated tests passed; six framework deprecation warnings only.

## Tested controls

| Control | Evidence | Expected result |
|---|---|---|
| Prompt injection | `tests/test_injection.py`, `tests/test_document_processing.py` | Untrusted uploaded text is detected, retained for audit, fenced before prompts, and reported. |
| Unauthorized access / RBAC | `tests/test_security.py`, `tests/test_auth.py` | Employee access is limited to their own profile/plan; privileged routes require an authorized role. |
| Quiz answer protection | `tests/test_security.py`, `tests/test_phase4_dashboards.py` | Answer keys are not included in employee plan/quiz reads; answer evaluation is server-side. |
| Invalid / oversized input | `tests/test_security.py`, `tests/test_document_validation.py` | Invalid documents and large review payloads do not result in an unhandled server error. |
| SQL/XSS-like payload handling | `tests/test_security.py` | Payload text is stored as data and is not executed by the application. |
| Audit integrity | `tests/test_security.py`, `tests/test_review_workflow.py` | Review decisions preserve original results and audit entries are append-only through the public API. |
| Pipeline separation | `tests/test_security.py`, `tests/test_phase3_validation.py` | Validation/reporting security checks do not call a GenAI provider. |
| Policy-update containment | `tests/test_phase4_dashboards.py` | Selective regeneration is scoped to items citing the changed document. |

## Upload-time prompt-injection verification

The upload service scans `parsed.full_text` before persistence. It saves a
document-level finding plus any section findings in `extra_metadata`, which the
report service exposes as `Prompt Injection Detected`. This protects paragraphs
that are not represented by a numbered heading and prevents a hidden payload
from disappearing during parsing.

## Manual deployment checks still required

Automated tests cannot prove production configuration. Before public release:

1. Set a strong, unique `SKILLSPRINT_SECRET_KEY` and HTTPS-only cookies.
2. Keep `CMD_API_KEY` exclusively in the backend secret manager.
3. Verify that Netlify has only `SKILLSPRINT_BACKEND_URL`, never the AI key.
4. Test an unauthorized employee against another employee's plan on the public URL.
5. Upload a harmless injection test document and verify its report finding.
6. Rotate all demo credentials or remove them before exposing the application publicly.

This report does not claim a penetration test or certify production security;
it records the repeatable application tests and required deployment checks.
