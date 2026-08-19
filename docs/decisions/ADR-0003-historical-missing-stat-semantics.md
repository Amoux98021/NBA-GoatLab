# ADR-0003: Historical missing-stat semantics

## Context

Many NBA statistics were introduced after the league began, and provider coverage also varies. Treating all absent values as zero would systematically penalize earlier players and corrupt cross-era analysis.

## Decision

Preserve `NULL != 0`. Distinguish observed zero, missing value under expected coverage, historically unavailable metrics, and unavailable provider/source coverage where practical. Maintain a Silver `metric_coverage` entity with season, provider, derivation, eligibility, and methodology context. Statistical fact fields remain nullable unless absence has a defensible observed-zero meaning.

## Alternatives considered

- Fill every null with zero.
- Impute historical values in Silver.
- Keep only complete modern-era rows.

## Consequences

Downstream calculations must be null-aware and coverage-aware. Cross-era eligibility becomes explicit. Any later imputation belongs in a versioned Gold feature or experiment, never in raw facts.

## Status

Accepted — 2026-08-19.
