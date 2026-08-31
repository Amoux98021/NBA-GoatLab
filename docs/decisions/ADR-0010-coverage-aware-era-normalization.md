# ADR-0010: Coverage-aware era normalization and rate availability

## Context

GOATLAB-HIST-V1 proves that endpoint and column availability are not equivalent to historically reliable observations. Early minute fields can be non-null but overwhelmingly non-positive placeholders. Advanced player possessions exist only in official Advanced/Totals from 1996-97 onward. A uniform feature grid would fabricate comparability across eras.

## Decision

Create Gold methodology version era-normalized-player-season-v1 from immutable Silver TOTAL rows. A feature is calculated only when every required source metric is RELIABLE under ADR-0007 and any feature-specific empirical gate passes. Unavailable results remain NULL with explicit eligibility and coverage reasons.

For each eligible season/type/metric distribution, calculate population standard z-score; median/MAD robust z-score as 0.6744897501960817 × (value - median) / MAD; midrank empirical percentile as (count below + 0.5 × count equal) / population size; and ratio index 100 × value / reference only for a positive, meaningful reference. Zero variance, zero MAD, and invalid denominators produce method-specific unavailable statuses.

Per-game rates require valid totals and games. Per-36 additionally requires RELIABLE player-game minutes and at least 99% positive minute observations. Per-75 uses only official Advanced/Totals player possessions when at least 99% are positive; it is unavailable before 1996-97 and is not reconstructed from historical box scores. Official player-minutes-weighted pace may describe post-1996 league context, but no historical or team possession estimate is invented.

Shooting formulas are FGM/FGA, FTM/FTA, FG3M/FG3A, (FGM + 0.5 × FG3M)/FGA for eFG%, and PTS / (2 × (FGA + 0.44 × FTA)) for TS%. Required inputs must pass coverage gates. Shooting league references use aggregate qualified makes and attempts; Regular Season and Playoffs are isolated.

## Alternatives considered

- Generate the same feature columns for every era and impute missing history.
- Treat non-null minutes as sufficient when nearly all values are zero.
- Estimate pre-1996 possessions from sparse historical box scores.
- Normalize TEAM rows or mix Regular Season and Playoff populations.
- Clip extreme but mathematically valid z-scores.

## Consequences

Gold is deliberately sparse across history. PPG remains available in all 160 partitions, per-36 qualifies in 100, and official per-75 in 60. Early stars can have valid scoring normalization and NULL rebound, assist, efficiency, or minute rates in the same season. Every feature remains traceable to source metrics, population, coverage gate, formula, corpus fingerprint, and methodology version. No composite or ranking is created.

## Status

Accepted — 2026-08-31.
