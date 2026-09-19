# STEP-0017 — Postgres Loader & FastAPI Serving Layer

Date: 2026-09-19

Step status: `PASS`

Backend verdict: `BACKEND_SERVING_LAYER_READY`

Recommendation: `READY_FOR_FRONTEND_LEADERBOARD`

## Frozen input and scope

The only ranking input is STEP-0016 release
`goatlab-ranking-release-2026-v2-probabilistic`, fingerprint
`2b2b5d91cf519ed091aa8179a800cbe4f018c85510cacc684e0f9ed5fdab4093`.
The loader re-hashes every artifact declared in its immutable manifest before any database
write. It validates the five Parquet schemas, 5,103 profiles/identities, 1,882 rankable rows,
3,221 unavailable rows, 35,721 dimension rows, frozen 100-entry Top-100 order, and 1,882 × 2,500
aligned draws. No generated STEP-0016 artifact, Gold input, basketball formula, methodology
version, ranking policy, or V1 output changes.

## Migration and transactional load

ADR-0041 accepts a minimal checksum-locked SQL migration runner rather than adding Alembic to a
repository with no ORM models. Migration 0001 implements the STEP-0016 PostgreSQL design plus
the documented release-fingerprint, exact-profile, and exact-Top-100 serving extensions. It
uses ordinary PostgreSQL 17 features supported by Neon: relational keys/checks, JSONB, indexes,
transactional COPY, advisory locks, and immutable-row PL/pgSQL triggers. No Neon extension is
required. Existing migration checksums cannot change silently.

The loader verifies all frozen bytes, starts one transaction, inserts the release manifest,
COPY-loads normalized rows and response payloads, then compares every loaded identity, status,
probability, dimension, profile, and Top-100 payload to the source. It commits only after exact
reconciliation. Local isolated-PostgreSQL test results:

| Check | Result |
|---|---|
| First full load | `LOADED` in 1.917 s |
| Repeat same ID/fingerprint | `ALREADY_LOADED` in 0.877 s; no new rows |
| Deliberate mid-import failure | Full rollback; `ranking_versions=0`, `players=0`; retry succeeded |
| Same ID/different fingerprint | Hard failure |
| SQL UPDATE of published release | Rejected by immutable-row trigger |
| Post-load counts | 5,103 players/profiles; 1,882 ranking/probability rows; 35,721 dimensions; 100 Top-100 entries; 3,221 unavailable |

## Serving and API

`PostgresRankingRepository` serves release metadata, normalized search/filter/pagination,
exact profiles, Top 100, and methodology from PostgreSQL. The existing artifact-backed adapter
remains available for offline use. Shared `PairedDrawStore` verifies the release and NPZ hashes
at startup, loads/decompresses draws once on first comparison, and optionally retains up to
4,096 recent unordered pair results in a process-local LRU. It preserves aligned draw identity,
computes pairwise probabilities on demand, and splits exact ties symmetrically. It does not
precompute 1,770,021 pairs.

The read-only FastAPI app exposes `/api/v1/health`, `/releases`, `/releases/{id}`,
`/leaderboard`, `/top100`, `/players/{id}`, `/compare/{a}/{b}`, and `/methodology`. Pydantic
domain/envelope models generate a valid OpenAPI description. Unknown players/releases return
404, a same-player comparison returns 400, and a known unavailable player returns structured
422 without fabricated probability. Health reports DB/release/draw state and uses HTTP 503 when
degraded. API startup fails on missing/mismatched configured release or draw artifact; it never
falls back to another release. CORS origins are explicit and configurable; production forbids
`*`. The API has no write routes. Deploy it with a SELECT-only DB role.

Artifact and PostgreSQL adapters produced identical serialized leaderboard first-100 rows,
Top-100 payloads, methodology/release records, pairwise comparisons, and deterministic sample
profiles including an unavailable player, George Mikan, Jordan, LeBron, Curry, Kobe, and Gobert.
No reputational judgment enters these comparisons.

## Local benchmark and checks

Warm localhost PostgreSQL/FastAPI TestClient benchmark, 25 requests per repeated operation;
illustrative, not a deployment SLA:

| Operation | Median | P95 |
|---|---:|---:|
| Leaderboard first 100 | 10.225 ms | 10.713 ms |
| Player profile | 2.485 ms | 2.861 ms |
| Pairwise after lazy load | 8.077 ms | 8.533 ms |

The first pairwise call, including a second hash check and NPZ decompression, took 117.200 ms.
Repeated requests do not re-read the ~30 MB file. Local full load is under two seconds. These
numbers include a new ordinary PostgreSQL connection per repository operation; connection
pooling remains a future
deployment optimization.

`pytest -q` with a local test Postgres ran **388 passed, 1 opt-in live-network test skipped**.
Tests cover migrations, checksum history, rollback, idempotency, immutability, entire post-load
reconciliation, adapter equivalence, API errors/filters/Top 100, draw complementarity,
OpenAPI, and degraded health. `ruff check .` and strict targeted mypy on
`src/goatlab/product` passed. Full-package mypy still reports two pre-existing redundant-cast
diagnostics in unchanged `src/goatlab/rankings/overall_v2.py` (lines 59, 119); the frozen
Overall implementation was not changed to silence them.

## Deployment boundary

The server was tested only against isolated local PostgreSQL, not a live Neon project. External
publication remains gated by `PUBLICATION_RIGHTS_REVIEW_REQUIRED`; no source-rights conclusion
is encoded as deployment approval. Production still needs infrastructure provisioning,
SELECT-only API credentials, TLS/CORS configuration, and a frontend. Basketball measurement
uncertainty remains the frozen methodological disclosure, not something this backend reduces.
