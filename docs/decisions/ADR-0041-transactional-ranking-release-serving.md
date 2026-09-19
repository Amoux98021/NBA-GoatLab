# ADR-0041 — Transactional PostgreSQL serving for immutable ranking releases

Status: Accepted

Date: 2026-09-19

Related: ADR-0002, ADR-0039, ADR-0040, STEP-0016, STEP-0017

## Context

STEP-0016 produced a fingerprinted release with five Parquet load tables, exact profile/Top-100
JSON, and aligned paired draws. Its draft SQL lacked release fingerprint, artifact hashes, and
complete profile payloads. Serving the product reliably requires one atomic import, exact
release identity, and equivalence with the artifact-backed adapter. The basketball methodology
and generated release are frozen.

## Decision

Use checksum-locked SQL migrations, ordinary PostgreSQL tables, and Psycopg COPY inside a single
transaction. `ranking_versions` extends the STEP-0016 draft with the immutable release
fingerprint, manifest, artifact/source hashes, methodology versions, counts, and rights gate.
Core identity, ranking, dimension, and probability columns remain STEP-0016-compatible.
Rank-band columns are copied from the already-frozen `rank_json`; this is a database projection,
not recalculation.

Add `player_profiles` and `top100_entries` JSONB tables for exact response equivalence with the
frozen product artifacts. The normalized tables remain queryable for search, filtering,
pagination, and whole-table reconciliation. Database triggers reject UPDATE/DELETE of published
release rows. A repeat load with the same release ID and fingerprint reconciles and returns a
no-op; a differing fingerprint fails. Any exception during COPY or reconciliation rolls back.

The paired Overall/rank draw NPZ remains outside PostgreSQL, fingerprint-verified and loaded once
per process. Pairwise probabilities are computed on demand with the frozen symmetric half-tie
rule; no all-pair table is created. The public API exposes GET routes only. Deployment must use a
read-only database role distinct from the controlled loader role.

## Consequences

The migration-managed schema is a documented implementation extension of the STEP-0016 draft
DDL; it does not alter the release bytes or basketball methodology. PostgreSQL 17 local tests
exercise transaction rollback, idempotency, immutable rows, complete reconciliation, API
equivalence, and Top-100 identity. Neon compatibility uses standard PostgreSQL and requires no
extension. A later release receives a new ID and migration as needed, never an in-place rewrite.
