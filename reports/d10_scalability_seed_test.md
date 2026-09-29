# D10 - 1,000+ Employee Reproducible Seed Test

**Date:** 2026-09-29  
**Verifier:** Azhar Raji  
**Scope:** Fresh-database seeding for the SRS employee-profile scalability target.

## What was tested

The committed workforce snapshot was rebuilt from the reviewed local employee
profiles. A separate, empty SQLite database was then seeded with:

```powershell
$env:SKILLSPRINT_DATABASE_URL='sqlite:///D:/Skill_Sprint_AI/.tmp_scalability_seed.db'
.\.venv\Scripts\python.exe -m database.seed_render
```

The command completed successfully. A follow-up database count reported:

| Entity | Result |
|---|---:|
| Employee profiles | 1,013 |
| Employee accounts | 1,013 |
| Staff accounts | 4 |
| Approved job roles referenced by profiles | 11 |
| Role-requirement matrix rows | 178 |
| Company document files ingested | 38 |
| Source-grounded review-only demo plans | 10 |

The generated temporary SQLite file was removed after the check. The committed
snapshot contains no password hashes, API keys, uploaded binaries, plans, quiz
answers, or scores.

## Automated regression guard

`tests/test_current_workforce_snapshot.py` rejects a committed workforce
snapshot containing fewer than 1,000 employees, duplicate employee codes,
duplicate role titles, or an employee that references an absent role.

## Honest boundary

This is a reproducible **employee-profile seeding** test. It demonstrates the
SRS target of supporting at least 1,000 employee profiles without schema or
application redesign. It is not a claim that 1,000 live GenAI plans were
generated, and it does not substitute for a separate PostgreSQL load test or
the independent SRS targets for 100 job roles and 1,000 organizational
documents.
