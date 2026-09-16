# Defense V2 tiered promotion audit

STEP-0015M completed with `PASS + PROMOTE_DEFENSE_V2_WITH_LIMITATIONS`.

## Decision

The promoted method is `goatlab-v1-defense-v2-tiered`. Its rich reference form is 10% era-relative
Team Context, 38.5714% role-aware defensive actions, and 51.4286% reliability-weighted observed
Defensive Presence Impact. It preserves the prior 3:4 action-to-Presence balance while reducing
team-shared credit from 30% to 10%.

The reference form is the richest historically portable measurement form, not basketball truth.
Presence is observational, not causal and not RAPM. Missing Presence is never predicted.

## Reconstruction and evidence

Defense V1 and Candidate B reproduced with maximum numerical difference 0.0. STEP-0015B's
continuous artifact and STEP-0015H/L fingerprints were verified. The recovered corpus contains
22,457 Regular Season player-seasons: Team Context covers 21,674; rebound/action evidence 21,890;
STL/BLK 19,173; Presence 18,175; and reliable broad role 16,078. Presence is fully reliable in
15,616 rows and partially reliable in 2,559.

## Team Context audit

| Team weight | score/team correlation | between-team variance share | near-identical teammate rate |
|---:|---:|---:|---:|
| 10% | 0.1864 | 10.93% | 15.79% |
| 15% | 0.2725 | 14.36% | 16.72% |
| 20% | 0.3620 | 19.34% | 17.43% |
| 30% | 0.5413 | 33.63% | 19.41% |

Ten percent is selected because it is the smallest predeclared non-zero contextual term, retains
team environment evidence, and most strongly resolves the demonstrated inheritance flaw without
using player outcomes as a target.

## Season measurement linking

Primary results are five-fold player-grouped. Random and era-block results are retained in the
machine report. All interval coverages below are cross-fitted split-conformal.

| Form | Linker | MAE | Spearman | >10 error | 90% coverage | Mean 90% width | Point status |
|---|---|---:|---:|---:|---:|---:|---|
| actions + Presence, no context | linear | 2.49 | 0.9882 | 0.00% | 90.07% | 9.18 | provisional |
| actions + partial Presence | linear | 3.31 | 0.9710 | 0.47% | 90.04% | 13.62 | provisional |
| traditional + Presence | role-isotonic | 3.04 | 0.9780 | 1.24% | 90.25% | 12.80 | provisional |
| actions, no Presence | linear | 12.78 | 0.5764 | 60.63% | 89.91% | 45.79 | interval only |
| traditional, no Presence | linear | 13.32 | 0.5158 | 61.42% | 89.94% | 48.83 | interval only |
| rebound only | isotonic | 13.63 | 0.4758 | 61.19% | 90.03% | 50.69 | interval only |
| context + Presence | role-isotonic | 7.69 | 0.8764 | 32.90% | 90.00% | 28.72 | interval only |
| context only | linear | 15.14 | 0.1760 | 63.05% | 90.07% | 59.74 | unavailable |

Role-aware isotonic linking is used only where it materially improves held-out calibration. It is
not used to equalize role distributions.

## Career validation

The reference validation population contains 1,984 rich-evidence careers with at least three
seasons. Career Defense is the arithmetic mean of season Defense measurement followed by one fixed
reference ECDF; career length does not add quality credit.

| Pattern | MAE | Spearman | Bias | >10 error | 90% coverage | Point gate |
|---|---:|---:|---:|---:|---:|---|
| no Team Context | 3.19 | 0.9889 | 0.00 | 3.53% | 89.97% | pass |
| partial Presence | 4.61 | 0.9766 | 0.00 | 11.74% | 90.07% | pass |
| traditional + Presence | 5.71 | 0.9635 | 0.00 | 18.25% | 90.22% | fail |
| no Presence | 15.25 | 0.7617 | 0.00 | 56.80% | 90.37% | fail |
| traditional only | 18.25 | 0.6700 | 0.00 | 63.05% | 90.22% | fail |
| mixed transition | 9.45 | 0.9059 | 0.00 | 37.10% | 89.77% | fail |

Actual career statuses are 1,746 official points, 336 provisional points, 2,093 interval-only, and
928 unavailable. Season statuses are 13,923 official, 3,812 provisional, 4,595 interval-only, and
127 unavailable. Coverage is not maximized by converting ranges into points.

Career uncertainty candidates produced mean 90% widths of 9.62 (independent seasons), 13.34
(evidence-form blocks), and 15.77 (player blocks). The selected player-block policy reflects
within-player dependence; grouped career conformal validation provides the final coverage check.
The active-to-cutoff subset contains 325 official, 68 provisional, 125 interval-only, and 64
unavailable career outputs, under the same rules used for retired players.

## Attribution, influence, and validation

Team Context's rich-form covariance share is 4.34%, versus Presence 90.29%, rebound evidence
2.79%, blocks 1.47%, and steals 1.11%. Presence dominance is an explicit limitation: the method
prioritizes individual-impact evidence, but the signal remains observational and noisy.

The selected V2 produces a 3.52% near-identical rate among adjacent same-team-season comparisons;
action evidence differs materially in 87.67% and Presence in 62.30%. Prior common-pair collision
counts were 1,332 for V1, 142 for Candidate B, and 78 for STEP-0015B's continuous candidate.

Existing modern defensive rating is weak validation: V2 rho is 0.1355 versus V1 0.2813. This does
not support causal certainty and was not a fitting target. Award validation, also not a target,
shows 85.19% of DPOY winners at or above P90 and 74.07% at or above P95; All-Defense players have a
median V2 score of 91.26.

Form-transition adjacent-season movement averages 13.19 points versus 14.99 within form, so the
linking layer does not create a larger average score cliff. Status and interval changes remain
explicit at transitions.

## Joint uncertainty and Overall boundary

Defense residual correlation with Peak ranges from 0.345 to 0.576 and with Longevity from 0.144
to 0.267 across matched patterns. Defense cannot be independently sampled in a future Overall.
Direct draw alignment is not currently available; STEP-0015N should preserve empirical marginals
and use pattern-specific copula rank alignment to reproduce these covariance matrices.

Diagnostic replacement of fixed V1 Defense changes the common-player Overall center by +0.217
points on average, increases mean 90% interval width by 0.429, and has rho 0.9840 versus the
STEP-0015L center. This is sensitivity only. Overall weights, Overall V1, and the archived Top 100
remain unchanged.

## Limitations

- Presence is not causal and dominates rich-form variance.
- No-Presence and traditional-only careers remain interval-native.
- A direct common draw engine for Defense, Peak, and Longevity has not yet been built.
- The modern defensive-rating relationship is weak.
- Career intervals average season bounds and are validated by pattern-level career conformal
  checks; future joint Overall work should operate on aligned empirical draws.
