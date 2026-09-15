# ADR-0037 — Preserve joint dimension uncertainty in Overall

Status: Accepted

Date: 2026-09-15

## Context

Peak V2 and tiered Longevity share the same PlayerSeasonValue season evidence. Their measurement
errors are therefore dependent. STEP-0015K prohibited dropping an interval-valued required
dimension, redistributing its weight, or treating an interval midpoint as exact, but did not define
how a weighted Overall could consume the resulting distributions.

## Decision

Research Overall calculations use paired Peak and Longevity values from the same deterministic
`U3_STRATIFIED_BLOCK` career draw:

`0.17 Peak + 0.14 Longevity + 0.16 Offense + 0.14 Defense + 0.18 Playoffs + 0.10 Accolades + 0.11 Winning`

The other five dimensions remain fixed until they have validated uncertainty models. The Overall
central estimate is the median of the paired Overall draws. Intervals are player-grouped,
cross-fitted calibration layers applied to the paired distribution and are explicitly limited to
currently modeled Peak/Longevity measurement uncertainty.

An interval-only input may support a provisional Overall point only when the complete weighted
distribution passes the predeclared Overall-level gates. This is aggregation of uncertainty, not
promotion of the input midpoint. Missing required dimensions still make Overall unavailable.

Statuses are `OFFICIAL_OVERALL_POINT`, `PROVISIONAL_OVERALL_POINT`,
`OVERALL_INTERVAL_ONLY`, and `OVERALL_UNAVAILABLE`. Confidence never multiplies quality; weights
are never renormalized; and unknown Accolades are never zero.

## Consequences

- Positive Peak–Longevity covariance is retained. Independent marginal recombination is a rejected
  diagnostic because it narrows 90% intervals across every validated evidence pattern.
- Rank bands and Top-N probabilities are conditional on the current calibration architecture;
  shared cross-player calibration-model uncertainty is not yet modeled.
- The architecture is accepted as limited research infrastructure. It does not promote Overall,
  publish a new Top 100, or resolve the known Defense V1 attribution defect.
- Every research Overall row carries `DEFENSE_V1_FROZEN_PENDING_REVISION`.
