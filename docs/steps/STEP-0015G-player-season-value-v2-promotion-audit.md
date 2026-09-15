# STEP-0015G — PlayerSeasonValue V2 Recalibration & Promotion Audit

Date: 2026-09-14

Result: **PASS**

Promotion verdict: **DO_NOT_PROMOTE**

## Objective

Re-run Candidate D on the factual STEP-0015F corpus and decide whether its universal
PlayerSeasonValue point scale is ready for production. This is a promotion audit, not a formula or
ranking optimization step.

## Constitutional and scope controls

- V1 SeasonQuality, Peak, Longevity, Defense, and Overall remain unchanged.
- Candidate D is reconstructed before any audit and remains research-versioned.
- Only Regular Season, era-relative individual evidence enters value.
- Awards and modern PIE are validation-only; playoffs, championships, names, and external rankings
  never enter scoring or promotion gates.
- Missing evidence remains NULL. Confidence is separate from value.
- Official and frozen source facts are never averaged.

## Inputs and reconstruction

- STEP-0015F fingerprint:
  `0eb5514e6f5055160e41dd2260be279418133d228eaec50772e9063e89b6dc25`.
- Recovered Silver hash:
  `0a94bc25061d860f1916d7f691f4d53e16260c3c0e9932ef86ff2791603a52c3`.
- Recovered Candidate D hash:
  `d2dd838acd5f3e9e7fd732ebf967c53a59944fba1067eca95bbb148725a7f00a`.
- Constitution hash:
  `f7a67adb161de086e9d47b0eaa3b9606cfb42cc70f15341c2a225586403c6ad5`.
- Frozen STEP-0014 dimension fingerprint:
  `0dcd568b6ba69250f097b50835882582e75d043f42ae4057ff5721dbfc6e9b2a`.
- Frozen STEP-0015 Overall fingerprint:
  `02bacaaacbff1a038ca0b5a82c6d3b51e34e192426e51ad8f0b72cd89bda97aa`.

All 22,457 Silver and Candidate rows reproduce. The 21,107 scoreable values, empirical regimes,
components, and within-season percentiles have zero mismatches and zero maximum numerical
difference. Source precedence and field-level provenance are present on every fact row.

## Reconstructed Candidate D

1. Scoring is the existing 65% PPG / 35% TS blend when TS exists.
2. Offensive value combines Scoring and APG creation as 60% stronger / 40% secondary.
3. Defensive evidence uses 10% team context, up to 35% continuously reliability-weighted observed
   Presence, and the remainder on individual action evidence. Presence is never predicted.
4. Overall player-season value combines offense and defense as 55% stronger / 45% secondary.
5. Raw values are ranked by midrank ECDF within season.

The offense audit also reruns 65/35 stronger-secondary and direct 70/30 alternatives. Recovery
does not expose a new instability that justifies changing the predeclared 60/40 multi-path choice:
its mean realized scoring/creation split is 50.32%/49.68%. The formula is therefore unchanged.

## Source-conflict audit

The 9,299 material field conflicts reproduce exactly across 5,607 player-seasons and 1,665
players. Minutes account for 4,591; PTS 1,249; FTA 1,227; FTM 601; FGM 533; and all remaining
fields 1,098. The audit classifies 811 as traded-total scope differences; the remaining likely
causes include minute precision, incomplete game-log aggregation, historical corrections, and
source-version differences. These cause labels are diagnostic rather than asserted facts.

Canonical precedence remains official PlayerCareerStats before 1996 and frozen GOATLAB-HIST-V1
thereafter. A complete alternate-source counterfactual produces 4,631 score pairs. Percentile MAE
is 0.321 points, maximum 15.917, 2.96% move more than two points, 0.54% more than five, and 0.19%
more than ten. Source choice is therefore stable in aggregate and does not block promotion by
itself, though the largest individual cases remain documented.

## Coverage and remaining missingness

Candidate D scores 21,107/22,457 seasons (93.99%) for 3,893 players:

| Regime | Rows | Scoreable | Coverage |
|---|---:|---:|---:|
| `FULL_PORTABLE` | 14,687 | 14,687 | 100.00% |
| `EXPANDED_BOX_NO_PRESENCE` | 4,486 | 3,990 | 88.94% |
| `TRADITIONAL_BOX` | 2,717 | 2,430 | 89.44% |
| `EARLY_LIMITED` | 567 | 0 | 0.00% |

Confidence among scored rows is 7,457 strong, 10,760 moderate, and 2,890 limited. The 1,350
unavailable rows comprise 567 without rebound/action evidence and 783 without team context, with
two also missing creation and efficiency. All 565 player-seasons in the 1940s remain unavailable;
1950s coverage is 942/944.

Pre-1950 seasons remain unavailable rather than receiving predicted rebounds. Pre-1973 STL/BLK
remain unavailable but are not zero. Artificially masking STL/BLK on full-evidence rows has 3.26
point MAE overall, with signed role effects of +3.83 for bigs and -3.31 for guards; this is a
material confidence/role limitation even though it is smaller than missing-Presence error.

## Effective influence and defensive input

Covariance-allocated primitive shares on the recovered corpus are:

| Primitive | Variance share |
|---|---:|
| APG | 32.96% |
| PPG | 22.52% |
| RPG/action allocation | 16.49% |
| STL/action allocation | 11.13% |
| BLK/action allocation | 11.13% |
| TS | 6.61% |
| Presence | -1.02% |
| Team context | 0.18% |

Action shares allocate a constructed role-aware action axis and are not causal raw-event shares.
Presence's negative covariance share is possible because the channel is noisy and correlated with
the rest of the formula; it does not mean Presence has a negative nominal coefficient. Team
context's mean/max total weights are 5.00%/5.50%, so team evidence remains contextual and
non-dominant.

## Actual coverage versus masking robustness

Factual recovery and counterfactual masking answer different questions. The former proves what is
observed; the latter tests whether different evidence regimes retain the same construct.

| Artificial regime | MAE | RMSE | Spearman | More than 10 points |
|---|---:|---:|---:|---:|
| Expanded box, no Presence | 7.25 | 8.84 | 0.9535 | 29.67% |
| Traditional box | 7.96 | 9.94 | 0.9410 | 32.48% |
| Early with Presence | 8.41 | 11.00 | 0.9278 | 33.47% |
| Early minimal | 11.34 | 14.54 | 0.8739 | 47.03% |

The decisive fact is that non-full regimes are not rare hypotheticals. Expanded and traditional
regimes contain 6,420 actually scored seasons, 30.42% of all scores. Their masking errors therefore
remain a production-scale comparability problem despite 93.99% raw coverage.

## Role, archetype, and temporal audits

Scored mean percentiles are 52.86 for guards, 51.14 wings, 48.01 forwards, and 48.29 bigs. Equal
means are neither expected nor enforced. The STL/BLK mask shows opposing guard/big residuals, and
historical non-full regimes remain unevenly distributed; no positional ceiling or quota is used.

Across 16,143 adjacent season pairs, adjacent Spearman is 0.7620. Regime-transition and same-regime
mean absolute changes are 14.71 and 14.69 points, respectively, so recovery removes an aggregate
transition cliff. Team-change seasons remain more volatile (16.95) than same-team seasons (13.64).
This continuity result is reassuring but cannot establish measurement invariance.

## Independent validation

The 67 available MVP seasons average the 98.33rd percentile and 97.01% are at or above P90. The
361 available All-NBA First seasons average the 95.66th percentile and 87.81% are at or above P90.
Modern PIE has Spearman 0.7384 and Pearson 0.7391 across 12,437 overlaps. Awards and PIE are noisy,
overlapping validators and never enter the formula or verdict optimization.

## Early-era and downstream counterfactuals

Russell, Pettit, Baylor, West, Robertson, Chamberlain, and Kareem become Peak- and
Longevity-eligible, but each retains one to three unavailable seasons. Mikan has five scoreable
seasons and two pre-rebound unavailable seasons. These are partial-career research estimates, not
evidence that the formula is universally invariant.

Fixed-architecture Peak produces 2,326 player scores and correlates 0.8805 with V1; Top-100 overlap
is 0.53. Fixed-architecture Longevity produces 3,893 scores and correlates 0.7750 with V1;
Top-100 overlap is 0.74. Candidate Peak/Longevity Spearman is 0.8714: the constructs remain
mechanically distinct, though strongly related.

Because Candidate D fails promotion, no frozen-weight Overall counterfactual is produced. This
avoids presenting an unapproved shared primitive as a near-public ranking methodology.

## Validation, reproducibility, and limitations

The complete repository suite passes with 238 tests and one opt-in network test skipped. Ruff,
strict Mypy across 31 package files, JSON/Parquet artifact checks, and Git whitespace validation
pass. A second cache-only run issues zero network requests and reproduces fingerprint
`120c319c8b3883b2066187947d3a6b813aa4d590231035fdd02943486268dd4f`; runtime is approximately
16 seconds.

Remaining limitations are substantive: Presence is observational WOWY-style evidence rather than
causal RAPM; historical STL/BLK and pre-1950 rebounds do not exist; 783 otherwise richer rows lack
team context; role metadata are incomplete; role-action allocation is not a causal decomposition;
and source-conflict cause labels remain diagnostic. Modern PIE and awards are imperfect validators.

## Verdict

STEP-0015G is **PASS** because reconstruction, conflict sensitivity, coverage, influence, fairness,
continuity, validation, and downstream audits are complete and reproducible.

Promotion is **DO_NOT_PROMOTE**. Factual recovery solved the dominant offensive collection failure,
and source conflicts are stable, but Candidate D still assigns universal point scores to 6,420
seasons whose defensive evidence regimes fail construct-equivalence masking by a material margin.
Coverage percentage cannot substitute for measurement invariance.

The next step should redesign PlayerSeasonValue as an uncertainty-aware, regime-explicit
measurement system: preserve official full-evidence point scores, publish bounded/interval or
provisional estimates for non-full defensive regimes, and test downstream rank eligibility without
silently treating those estimates as equally precise universal points.
