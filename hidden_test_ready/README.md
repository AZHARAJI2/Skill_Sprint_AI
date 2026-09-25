# Hidden-test ready pack

Evaluators: the live application must ingest unseen documents and a new role
without source changes.

1. Install from the repository root (`pip install -r requirements.txt`).
2. Run `python -m database.seed` then `uvicorn src.main:app --host 0.0.0.0 --port 8000`.
3. Log in as `admin` / `admin123`.
4. Upload hidden documents via `/documents/upload` or `POST /api/documents/upload`.
5. Create a hidden role via `POST /api/roles` and an employee via `POST /api/employees`.
6. Reload an updated matrix CSV with `POST /api/matrix/load` after replacing
   `role_matrix/role_requirement_matrix_seed.csv` (or posting a future upload endpoint in Phase 4).

Demo credentials are listed in the root README. This folder will gain packaged
demo snapshots in Phase 4.
