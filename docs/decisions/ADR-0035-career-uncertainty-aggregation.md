# ADR-0035: Preserve within-career dependence in Peak and Longevity uncertainty

- Status: Accepted
- Date: 2026-09-15
- Related: ADR-0031, ADR-0032, ADR-0034, STEP-0015I

## Context

STEP-0015H supplies calibrated season-level empirical intervals, but its preliminary downstream
diagnostics did not validate how those errors combine across a career. Linker residuals recur by
player, evidence form, role, archetype, and team continuity. Independent season draws therefore
understate aggregate dependence, while fixing the best Peak window before simulation understates
maximum-selection uncertainty.

## Decision

Research Peak and Longevity aggregation will use fixed-seed empirical block simulation that:

1. preserves a player-level residual component and samples remaining residuals within evidence
   form, broad role, archetype, and score band where support exists;
2. reselects the best complete contiguous three-season Peak window and apex in every draw;
3. computes P80 breadth, capped P80-P90 area, and the exact longest consecutive P80 run in every
   Longevity draw;
4. transforms each draw through one frozen `BROAD_HIGH_RECALL` ECDF reference rather than moving
   the population scale; and
5. reports quality, interval, window/run uncertainty, and aggregate status separately.

The constitutional 70/30 Peak and 35/40/25 Longevity weights remain unchanged. Awards,
postseason, championships, player identity, and future active-career projections are excluded.

## Consequences

- The selected research method is `U3_STRATIFIED_BLOCK` with 2,500 draws.
- Peak and Longevity remain research-only and receive separate limited verdicts.
- Weak evidence patterns may remain interval-only even when a central simulation summary exists.
- No season-level PlayerSeasonValue, V1 dimension, or V1 Overall artifact is overwritten.
- Later promotion work must address Longevity rank calibration and the conservative full-form
  interval baseline before an official methodology can be created.
