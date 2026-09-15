# Overall uncertainty architecture audit

Methodology: `goatlab-v1-overall-v2-uncertainty-research`

Result: **PASS + LIMITED_OVERALL_UNCERTAINTY_ARCHITECTURE**

Recommendation: **READY_FOR_OVERALL_PROMOTION_AFTER_DEFENSE**

## Decision

The fixed seven-dimension Overall can propagate currently modeled Peak and Longevity uncertainty
without changing any nominal weight. The valid research architecture applies the fixed weighted
sum inside each paired Peak/Longevity career draw and summarizes the resulting Overall
distribution. Offense, Defense, Playoffs, Accolades, and Winning remain fixed because no validated
uncertainty distributions exist for them in this step.

The median paired-draw Overall is selected as the central estimator. Mean and weighted marginal
medians are close, but the paired-draw median preserves the upstream median semantics and never
pretends an interval-valued input is exact.

## Validation

The 1,200-player full-form validation population is masked into six realistic career evidence
patterns. Overall uncertainty is attenuated by the 31% combined Peak/Longevity weight. Mixed,
partial-Presence, no-Presence, and historical-transition patterns pass Overall point gates even
when a constituent Longevity value is interval-only. Traditional-only careers fail because
10.25% exceed five points of error, just above the predeclared 10% limit.

| Pattern | MAE | Spearman | Bias | >5 points | 90% coverage | Mean 90% width | Point gate |
|---|---:|---:|---:|---:|---:|---:|---|
| Full reference | 0.11 | 0.9999 | -0.01 | 0.00% | 90.00% | 0.53 | pass |
| Mixed | 1.16 | 0.9957 | +0.03 | 4.50% | 90.33% | 4.80 | pass |
| Partial Presence | 0.97 | 0.9961 | +0.13 | 4.17% | 90.25% | 3.95 | pass |
| No Presence | 1.33 | 0.9944 | +0.07 | 6.08% | 89.92% | 5.46 | pass |
| Early transition | 1.55 | 0.9929 | +0.03 | 7.83% | 90.08% | 6.42 | pass |
| Traditional only | 1.94 | 0.9901 | -0.16 | 10.25% | 89.92% | 7.85 | fail |

The research gates are MAE <= 2, Spearman >= 0.98, absolute bias <= 1, no more than 10% above
five points, and 87%–93% coverage for the nominal 90% interval.

## Dependence and variance

Peak and Longevity draws are positively correlated in every pattern. Mean within-draw correlation
ranges from 0.55 to 0.65 in the five non-reference patterns; traditional-only is 0.647. The
covariance contribution is positive and the analytic variance identity agrees with empirical
variance to numerical tolerance. Independent recombination narrows mean 90% intervals—for
example, 7.95 to 6.55 points for traditional careers and 4.83 to 4.12 for mixed careers—so it is
not an acceptable primary model.

## Status and eligibility

Across all 5,103 players, 602 receive an official research Overall point, 1,280 receive a
provisional research Overall point, and 3,221 are unavailable. No real player lands in
`OVERALL_INTERVAL_ONLY` under the current combination of usable evidence patterns, although that
status remains required for future patterns that have a usable distribution but fail point gates.

Within `BROAD_HIGH_RECALL`, counts are 602 official, 1,280 provisional, and 774 unavailable. The
frozen V1 Top 100 remains in its archived order: 16 official and 84 provisional under this
research status audit.

An interval-only Longevity can support a provisional Overall point because its full uncertain
contribution is propagated at 14% and the resulting Overall distribution passes the Overall-level
gate. The Longevity midpoint never becomes an official input point.

## Forbidden baselines

Dropping Longevity and renormalizing changes the intended construct and introduces roughly
0.5–0.7 points of signed bias in non-reference patterns. A confidence multiplier creates a large
negative bias of roughly four Overall points. A fixed interval midpoint can resemble the paired
median numerically, but it erases uncertainty, covariance, rank bands, and membership probability;
that numerical similarity does not make it constitutionally admissible.

## Ranking diagnostics

Ranking outputs are research-only. Pairwise central-order accuracy rises with separation: in the
mixed pattern it is 61.7% around a 0.5-point gap, 84.3% around two points, 95.5% around five, and
99.4% around ten. Top-N probability Brier scores for the mixed pattern are 0.00082, 0.00165,
0.00334, and 0.00609 for Top 10/25/50/100. Central Top-N overlaps are 100%, 96%, 94%, and 94%.
Close pairwise comparisons remain uncertain and should be presented as such.

## Frozen V1 comparison and limitations

Among 1,882 players with usable diagnostic distributions, the new diagnostic center versus
archived Overall V1 has Spearman 0.9730, Pearson 0.9757, MAE 3.22, and bias +0.01. This is a
diagnostic methodology transition, not an improvement target and not a new ranking.

The interval covers only modeled Peak/Longevity measurement uncertainty. Defense V1 is held fixed
despite its known attribution problem; all rows therefore carry
`DEFENSE_V1_FROZEN_PENDING_REVISION`. Other dimension uncertainty and shared calibration-model
uncertainty across players are not modeled. Accolades `NOT_QUERIED` remains unknown and blocks
Overall rather than becoming zero. No Overall V2 or Top 100 is published.
