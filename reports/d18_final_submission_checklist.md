# D18 — Final Submission Checklist

## Complete before submission

- [ ] Public GitHub repository contains the source code, documents, reports,
  installation/execution instructions, and the current `AI_USAGE.md`.
- [x] Fresh clones can seed ten review-only demo drafts with `python -m database.seed`.
- [ ] Ten complete **live GenAI** plans exist, one for every NovaCart role, and
  are reviewed by an authorized staff member.
- [ ] `python -m scripts.benchmark_live_plan --employee-code EMP-001` exits `0`
  and its generated evidence shows a complete non-fallback plan in ≤30 seconds.
- [ ] `python -m scripts.generate_phase3_reports` succeeds after the ten live
  plans exist; D6 then contains genuine same-role comparisons.
- [x] D9 security report and automated test evidence are included.
- [x] D11 installation instructions and D12 execution walkthrough are included.
- [ ] Netlify URL proxies to the HTTPS FastAPI backend with PostgreSQL; run all
  acceptance checks in `DEPLOYMENT.md`.
- [ ] Update credentials, use a strong secret, and confirm AI keys are absent
  from GitHub, Netlify, and frontend source.
- [ ] Record the public URL, evaluator logins, demonstration video, and final
  project report required by the competition.

## Evidence integrity rule

Never replace an unmet item with a generated or manually edited success claim.
The benchmark, D6 generator, and review workflow are intentionally designed to
retain failures and block misleading completion evidence.
