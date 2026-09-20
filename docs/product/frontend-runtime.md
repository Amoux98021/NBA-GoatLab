# GOATLab frontend runtime

STEP-0018 adds a Next.js 16 App Router application under `frontend/`; STEP-0019 adds the
probabilistic player-comparison experience. It consumes the read-only
STEP-0017 API; it does not read Gold, product artifacts, PostgreSQL, or paired-draw files.

## Local setup

From the repository root, make sure the immutable STEP-0016 release exists. Its fingerprint
must be `2b2b5d91cf519ed091aa8179a800cbe4f018c85510cacc684e0f9ed5fdab4093`.
For database mode, start local PostgreSQL, set `DATABASE_URL`, then run:

```bash
PYTHONPATH=src:. .venv/bin/python -m pipelines.product.migrate_product_database
PYTHONPATH=src:. .venv/bin/python -m pipelines.product.load_ranking_release
GOATLAB_BACKEND_MODE=postgres PYTHONPATH=src:. .venv/bin/python -m uvicorn goatlab.product.api:app --host 127.0.0.1 --port 8000
```

For offline development with the generated release on disk, the last command can use
`GOATLAB_BACKEND_MODE=artifact` and needs no PostgreSQL. Then in another terminal:

```bash
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

Open `http://localhost:3000`. Set `NEXT_PUBLIC_API_BASE_URL` to the FastAPI origin; it must
be reachable by the Next.js server. Set `GOATLAB_RELEASE_ID` to the exact immutable release ID.
The defaults in `.env.example` target local read-only API service and the 2026 probabilistic
release. No API secret belongs in the browser. Ranking and comparison data are fetched
server-side; the only browser fetch is the narrow same-origin `/api/compare/search` player-search
proxy. A production release must have a secure backend origin and explicit CORS origin.

## Checks

```bash
cd frontend
npm run typecheck
npm run lint
npm test
npm run build
```

With both local servers running, run live contract checks:

```bash
GOATLAB_TEST_LIVE=1 npm test
```

This compares all 100 server-rendered player IDs against `/top100`, diagnostic profiles, five
live pairs against `/compare`, reversed probabilities, canonical search, and unavailable/same/
unknown-player behavior. The optional live tests are skipped when no local API is running.
Browser QA checks 375, 768, 1024, and 1440 px layouts.

## Deployment boundary

`PUBLICATION_RIGHTS_REVIEW_REQUIRED` remains open. Local build and preview are not clearance
for public deployment. Serve only the immutable release; do not point a release ID at changed
content. API failures render an explicit error; no fallback ranking is substituted.
