# Local STEP-0017 backend development

1. Create/activate the project virtual environment and install the package with dev extras:

   ```bash
   .venv/bin/python -m pip install -e '.[dev]'
   ```

2. Start an ordinary local PostgreSQL server (for example, installed PostgreSQL 17). Use an
   isolated development database. Set `DATABASE_URL` in your shell; do not commit it. Local
   connection example: `postgresql://YOUR_USER@127.0.0.1:5432/goatlab_dev`.

3. If `data/product/goatlab-ranking-release-2026-v2-probabilistic/` is absent, rebuild the
   frozen release offline using the STEP-0016 command. Verify the release fingerprint equals
   `2b2b5d91cf519ed091aa8179a800cbe4f018c85510cacc684e0f9ed5fdab4093`.

4. Run the migration and loader commands in [database-loading.md](database-loading.md). A repeat
   load should report `ALREADY_LOADED` and reconcile all rows.

5. Start the API:

   ```bash
   export GOATLAB_BACKEND_MODE=postgres
   export GOATLAB_ALLOWED_CORS_ORIGINS='http://localhost:3000'
   PYTHONPATH=src:. .venv/bin/python -m uvicorn goatlab.product.api:app --host 127.0.0.1 --port 8000
   ```

6. Check `/api/v1/health`, `/api/v1/leaderboard`, `/api/v1/top100`, a canonical player profile,
   and `/api/v1/compare/{a}/{b}`. The OpenAPI description is at `/openapi.json`; Swagger UI at
   `/docs`. For offline artifact mode, omit `DATABASE_URL` and set `GOATLAB_BACKEND_MODE=artifact`.

Integration tests use `GOATLAB_TEST_DATABASE_URL` pointing to a local test database. Each test
creates a uniquely named schema, applies migrations, and removes only that test-owned schema.
The test database user needs schema-creation rights. Tests without that variable still exercise
the artifact/API path and skip PostgreSQL integration tests. No Neon or public deployment is
part of this workflow.
