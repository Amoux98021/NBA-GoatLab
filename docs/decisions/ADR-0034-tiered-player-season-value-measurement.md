# ADR-0034 — Tiered PlayerSeasonValue measurement semantics

- Status: Accepted
- Date: 2026-09-15
- Decision owners: GOATLab methodology
- Related: ADR-0030, ADR-0031, ADR-0032, STEP-0015H

## Context

Candidate D observes different factual evidence across NBA history. STEP-0015G showed that 93.99%
raw score coverage did not establish measurement equivalence: missing Presence and STL/BLK changed
the score's ordering and meaning. STEP-0015H tests whether those evidence regimes can instead be
treated as measurement forms linked to the richer `FULL_PORTABLE` Candidate D form.

## Decision

Adopt tiered research semantics, without promoting Candidate D:

- `OFFICIAL_POINT` is reserved for the unchanged `FULL_PORTABLE` reference form.
- `PROVISIONAL_POINT` requires grouped-player out-of-sample MAE <= 5, Spearman >= 0.95, absolute
  bias <= 2, every major-role absolute bias <= 3, no more than 15% errors above ten points, and
  empirical 90% interval coverage between 87% and 93%.
- `INTERVAL_ONLY` is used when held-out intervals calibrate but the point estimate fails any point
  gate.
- `UNAVAILABLE` is used when observed factual evidence cannot support even the relevant
  measurement form.

Score linking may map a weaker form's observed score to the `FULL_PORTABLE` reference scale. It may
not predict a missing basketball statistic. Confidence and interval width remain separate from
quality and never multiply the estimate. `FULL_PORTABLE` is a reference instrument, not asserted
basketball truth.

For missing Team Context, retain the channel's nominal absence rather than renormalizing other
channels; link that reduced measurement form and propagate uncertainty. This treatment is allowed
because it passes every predeclared point gate. Traditional, no-Presence, and offense-only forms
remain interval-only when their point gates fail.

## Consequences

The architecture can represent uncertainty honestly and recover ranking-grade point treatment for
the narrow missing-team-context problem. It does not make sparse defensive regimes point-comparable.
Pre-1950 seasons may receive intervals from observed offensive evidence but not official point
scores. Candidate D, Peak, Longevity, Defense, and Overall remain unpromoted and frozen.

Downstream Peak and Longevity need a dedicated audit because selecting windows and crossing P80/P90
thresholds are uncertain operations, not simple arithmetic on independent interval endpoints.
