# ADR-0002: Bronze, Silver, and Gold architecture

## Context

The project must preserve source evidence while supporting stable cross-provider analytics and later methodology experiments.

## Decision

Use three layers: Bronze for untouched/source-faithful records and ingestion metadata; Silver for project-owned canonical entities and facts; Gold for derived analytics, era normalization, career features, dimension scores, and model/ranking inputs.

## Alternatives considered

- Query vendor tables directly from notebooks and models.
- Use one cleaned dataset for facts and derived opinions.
- Materialize only final ranking tables.

## Consequences

Storage and transformation work increase, but lineage, reproducibility, provider replacement, and methodological isolation improve. Every downstream model must consume versioned canonical/Gold fields rather than vendor column names.

## Status

Accepted — 2026-08-19.
