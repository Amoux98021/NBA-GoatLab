# STEP-0016 — Probabilistic Leaderboard Data Product

Date: 2026-09-19

Step status: `PASS`

Product verdict: `PRODUCTION_DATA_PRODUCT_READY` for the local versioned data layer; external
publication remains subject to source-rights review.

Recommendation: `READY_FOR_API_AND_DATABASE_IMPLEMENTATION`.

Release: `goatlab-ranking-release-2026-v2-probabilistic`.

Release fingerprint: `2b2b5d91cf519ed091aa8179a800cbe4f018c85510cacc684e0f9ed5fdab4093`.

## Scope and frozen input reconstruction

STEP-0015P closed basketball methodology. This engineering step consumes Peak
`goatlab-v1-peak-v2`, Longevity `goatlab-v1-longevity-v2-tiered`, Defense
`goatlab-v1-defense-v2-tiered`, Overall research substrate `goatlab-v1-overall-v2-tiered`, and
policy `goatlab-v1-ranking-policy-v2-probabilistic` unchanged. The seven 17/14/16/14/18/10/11
weights, status gates, and rank calibration are unchanged. The old V1 Top 100 is preserved.

The builder verifies STEP-0015P's frozen hashes, STEP-0015N/O fingerprints, and Gold files before
replaying the 2,500 frozen joint draws. It matches all 5,103 STEP-0015N player rows and all 1,882
STEP-0015O rank rows with **zero field/status mismatches and maximum numerical difference 0.0**.
All 100 archived V1 Top-100 players remain distribution-rankable. No network access occurs.

## Release output

The release contains 5,103 identity/profile records: 1,882 distribution-rankable and 3,221
unavailable. The 1,882 entries are sorted by `(frozen median rank, canonical player_id)`.
Display position is navigational, not an exact scientific order. The first 100 entries form the
*GOATLab Top 100 — Probabilistic Leaderboard* product view. This view is not a new basketball
methodology or an assertion of exact ordinal certainty.

The 100 slots contain 5 `OFFICIAL`, 10 `PROVISIONAL`, and 85 `INTERVAL_NATIVE` Overall statuses.
Top-100 membership classes are 82 robust, 12 likely, and 6 bubble. The lowest Top-100 membership
probability among display entries is 50.6%; this makes the boundary uncertainty visible rather
than hiding it. The separate boundary artifact contains 36 players, including 18 outside the
first 100 slots; its rule is 10%–below-90% membership probability plus a 90% rank band crossing
rank 100. Mean 90% rank-band width for the 100 entries is 27.36 ranks. No status changes quality.

## Storage and service architecture

ADR-0040 selects compact JSON/Parquet summaries plus a versioned compressed aligned-draw
artifact. The latter holds 2,500 Overall and rank draws for each of the 1,882 players and is
fingerprinted. Pairwise comparison is computed on demand from corresponding draw indexes; there
are 1,770,021 possible unordered pairs, so no redundant all-pair cache is produced. Exact draw
ties, if any, split symmetrically and their probability is exposed. Pairwise labels use the
frozen 90%/65%/35% boundaries.

`RankingRepository` is a read-only, artifact-backed service abstraction with leaderboard,
profile, pairwise, release, and methodology operations. It validates release artifact hashes on
load. The Pydantic domain/API response contracts are stable for a thin future FastAPI adapter.
No live database or public endpoint is created in this step. Search is normalized over canonical
names and does not perform fuzzy identity merging.

PostgreSQL-compatible DDL and five DB-load Parquet tables cover release-scoped `ranking_versions`,
`players`, `player_rankings`, `player_rank_probabilities`, and `player_dimensions`. A new release
ID, not an in-place update, is required for changed content. The SQL and API contracts are in
`docs/product/`.

## Artifact and size accounting

Generated files are ignored under `data/product/<release_id>/`. Committed
[release metadata](../product/step-0016-release-record.json) records the output fingerprint.

| Artifact | Size |
|---|---:|
| Full leaderboard JSON | 2,636,265 bytes |
| Compact Top-100 JSON | 77,827 bytes |
| Boundary/bubble JSON | 8,911 bytes |
| Full profiles JSONL | 24,311,858 bytes |
| Player identities JSONL | 1,533,258 bytes |
| Paired serving distributions NPZ | 29,635,982 bytes |
| Five DB-load Parquet tables, combined | 1,104,425 bytes |

Profiles are one JSONL row per player rather than 5,103 small files. Research residual pools and
raw source records are not served. The production files contain derived ranking analytics and
canonical identity/career metadata, not NBA game rows or downloaded vendor responses.

## Validation and performance

The build validates unique IDs, exact rankable/unavailable counts, all seven dimension records
per profile, nested Overall/rank intervals, monotone Top-1/5/10/25/50/100 probabilities, status
consistency, exactly 100 Top-100 entries, excluded unavailable players, V1 Top-100 rankability,
version completeness, finite numbers, draw alignment, and deterministic tie breaking.

Local artifact-backed read timings (single warm host, illustrative not a service SLO): repository
hash check/load 0.073 seconds; first-100 query below 0.001 seconds; first profile lazy-load 0.239
seconds; first pairwise request including draw lazy-load 0.077 seconds; warm pairwise request
below 0.001 seconds. A deployed adapter should keep the repository warm rather than recreate it
per HTTP request.

The offline build command is:

```bash
PYTHONPATH=src:. .venv/bin/python -m pipelines.product.build_probabilistic_leaderboard
```

One repeat uses `--expected-fingerprint` with the release fingerprint. Immutable writes reject
any byte change under the same release ID. The first full build took 96.177 seconds and wrote
15 files. The second full replay took 96.361 seconds, made zero network requests, wrote zero new
files, and reproduced the same fingerprint and row order.

Repository checks: `pytest -q` passed 379 tests with one opt-in live-network test skipped;
`ruff check .` and targeted strict mypy on `src/goatlab/product` passed. Full-package mypy remains
blocked by two pre-existing redundant-cast diagnostics in unchanged
`src/goatlab/rankings/overall_v2.py` (lines 59 and 119); this step does not change the frozen
Overall implementation to silence them.

## Publication and rights boundary

The committed [frontend disclosure contract](../product/frontend-uncertainty-disclosures.md)
requires visible rank bands, probability semantics, and the explanation that wider uncertainty
does not mean lower quality. [The source-rights inventory](../product/privacy-and-licensing-review.md)
finds no raw vendor payloads or private user data in these artifacts, but NBA.com's current
statistics terms impose use/attribution restrictions. This step does **not** determine rights for
a public or commercial deployment and does not deploy the release. Source-rights review or
permission is a distinct pre-launch gate.

## Permanent result

No basketball methodology, dimension score, Overall V1 output, STEP-0015N/O Gold artifact, or
archived ranking changed. Productization may now proceed to a transactional Postgres loader and
thin FastAPI adapter, followed by frontend implementation and publication-rights review.
