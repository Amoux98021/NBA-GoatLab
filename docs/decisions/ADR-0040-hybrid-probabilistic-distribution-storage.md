# ADR-0040 — Hybrid storage for probabilistic ranking releases

Status: Accepted

Date: 2026-09-19

Related: ADR-0002, ADR-0039, STEP-0016

## Context

The STEP-0015O policy needs calibrated per-player Overall/rank distributions, summary bands,
Top-N probabilities, and arbitrary pairwise comparisons. Summary-only storage cannot reproduce
pairwise comparisons. Precomputing 1,770,021 unordered pair records adds redundant serving data
and invites drift from the frozen joint draws. Transactional storage of all 2,500 draws per
player is unnecessary for ordinary leaderboard reads.

## Decision

Use a hybrid release: compact versioned player/rank/probability/dimension summaries in database-
ready Parquet and JSON, plus one compressed, fingerprinted paired Overall/rank draw artifact in
versioned file/object storage. The artifact-backed service lazily loads it for pairwise requests
and computes probabilities on demand from aligned draw indices. Each release ID maps to immutable
content; a new data/methodology result requires a new release ID.

No raw vendor responses, player-game records, or validation residual pools are published.
Research Gold remains upstream, not a live API dependency. The Overall research architecture
and exact-point non-promotion verdict are unchanged.

## Alternatives

- All draws in PostgreSQL: larger transactional footprint with little benefit to list reads.
- Summary-only: loses exact arbitrary pairwise comparison and empirical rank distributions.
- All-pair precompute: redundant large cache, expensive rebuild, and risk of release drift.
- Reduced quantile grid: smaller but not exact for the frozen empirical pairwise policy.

## Consequences

The first product build replays frozen draws and verifies STEP-0015O row-level identity. The
serving artifact is ignored by Git but carries a release manifest SHA-256. A future object-store
deployment must verify that hash, preserve draw alignment, and use a transactional DB import.
