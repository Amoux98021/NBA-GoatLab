# STEP-0015J — Longevity Threshold, Run & Aggregate Calibration Audit

Date: 2026-09-15

Result: **PASS**

Longevity verdict: **LONGEVITY_AGGREGATION_LIMITED**

Recommendation: **READY_FOR_PEAK_PROMOTION_WITH_LONGEVITY_INTERVAL_POLICY**

## Objective

Forensically identify why uncertainty-aware Longevity preserves absolute score reasonably well but
does not preserve ranking order at the declared point-grade threshold. The audit holds the
constitutional architecture fixed at 35% P80 breadth, 40% capped P80-P90 area, and 25% longest
consecutive P80 run. It does not reopen PlayerSeasonValue, Peak, P80/P90, or the published V1
methodologies.

## Frozen inputs and reconstruction

The audit verifies these frozen inputs before analysis:

- STEP-0015H fingerprint:
  `4b1ff850f9d0df43ffd271af16277d94abd3f14cba1a9a8aa679cb3983710f54`
- STEP-0015I fingerprint:
  `4f44cf63450105d8c215aa20a0b3078dc8b9b5c907f2f03553eff390195a150a`
- linked-season hash:
  `2908de32b614b96e405630334e07aeb262d690536c0c33fc7fe77b6f51ff6dc4`
- masked-anchor hash:
  `1821e4d7a15fccb70819f49d234f019ce75cba06613a86c80cc07e04fb8d202a`

All 7,620 STEP-0015I masked career-pattern rows reproduce with zero mismatches and maximum
numerical difference `0.0`. All 5,103 actual-player Longevity rows reproduce with maximum
difference `0.0`. The frozen Peak Parquet retains hash
`77b19ada90ba9d6163aaaaeccf341355d5ef9af12f5af04c6902ae7dbe569ea2`;
Peak scores, intervals, statuses, and window probabilities are unchanged.

## Method

The audit reuses `U3_STRATIFIED_BLOCK`, 2,500 deterministic draws, and the same empirical
within-career residual dependence as STEP-0015I. Every draw calculates exact P80 breadth, capped
P80-P90 area, and longest calendar-consecutive P80 run. It then performs:

- component-level raw and ECDF-point error analysis;
- one- and two-component uncertainty ablations;
- P80/P90 neighborhood forensics;
- explicit `RUN_BRIDGE_EVENT` detection;
- five central-estimator comparisons;
- fixed-reference ECDF order tests;
- career-length and evidence-pattern stratification;
- player-grouped aggregate conformal interval calibration;
- pairwise reversal attribution;
- P78/P88 through P82/P92 and 20%/25%/30% run-weight diagnostics.

Threshold and weight variants are diagnostics only. P80/P90 and 35/40/25 remain unchanged.

## Component calibration

Component errors below are expressed on their independently ECDF-transformed 0–100 scales.

| Evidence pattern | Breadth MAE / rho | Area MAE / rho | Run MAE / rho |
|---|---:|---:|---:|
| Mixed | 4.60 / 0.8941 | 4.59 / 0.8949 | 5.11 / 0.8881 |
| Partial Presence | 4.15 / 0.9089 | 4.05 / 0.9096 | 4.65 / 0.9022 |
| Traditional only | 7.09 / 0.8555 | 7.28 / 0.8532 | 7.64 / 0.8455 |
| Early transition | 6.08 / 0.8742 | 6.16 / 0.8728 | 6.70 / 0.8638 |

Longest run is the weakest isolated component, but the ablation result rejects a single-cause
story. In mixed evidence, allowing uncertainty only in breadth, area, or run yields final-score
MAEs of 2.24, 2.37, and 2.13. For partial Presence the corresponding MAEs are 2.01, 2.11, and
1.93. Multiple correlated threshold-derived component errors cause the final rank degradation.

## P80 and P90 findings

P80 is the main shared discontinuity. Among the 234 full-form anchor season positions with a
central score from 79 to 81, 89.7% remain probabilistically uncertain under mixed masking and
89.7% under partial-Presence masking. Such a season can change all three components at once:
elite breadth, capped area, and run continuity.

P90 affects only the upper cap of the area component. Around 89–91, the capped-area variance is
material, but P90 does not alter breadth or run. It contributes fine-grained score error rather
than the three-way structural discontinuity produced by P80.

Nearby threshold diagnostics do not repair the point-ranking failure. None of P78/P88 through
P82/P92 raises all realistic non-full patterns through the declared gates. This is evidence that
the result is not an unusually unlucky P80/P90 selection; the constitutional thresholds remain
frozen.

## Longest-run and bridge events

A `RUN_BRIDGE_EVENT` is a season with P80 probability strictly between 0.25 and 0.75 that joins
credible P80 sequences on both sides in consecutive calendar seasons. There are 827 events across
647 validation career-pattern cases, or 8.49% of tested career-patterns. Conditional on the
connector being above versus below P80, the longest run differs by 2.04 seasons on average and
final Longevity differs by 8.00 points. The average potential run gain is 2.35 seasons.

The actual historical output contains 248 bridge events among 187 players. These events are
reported explicitly. They justify interval width for affected careers, but do not by themselves
explain all ranking error: capped area causes the largest number of observed pairwise reversals.

Changing the run weight diagnostically from 25% to 20% or 30% produces only small calibration
changes and no point-gate reversal. The 25% constitutional weight is not changed.

## Central estimator and ECDF order

Five summaries were tested: final-draw median, final-draw mean, fixed-ECDF transformation of
expected raw components, expected transformed components, and modal run with expected breadth and
area. The **median of the final fixed-scale draw distribution** remains selected. It has mixed
MAE/rho 3.72/0.9388 and partial-Presence 3.44/0.9417.

The draw mean is less rank-stable (mixed rho 0.8950), while transforming expected components
creates 5–10 point positive bias because ECDF and threshold/run transformations are nonlinear and
the reference has many ties. Therefore the valid order is:

`season draws -> exact raw components -> fixed component ECDFs -> 35/40/25 -> fixed final ECDF -> median`

The reference ECDF is never redrawn. Its raw final distribution has 546 unique values among 1,270
validation careers (57.01% tie share). This amplifies small raw changes in dense/tied regions, but
the component errors exist before the final ECDF; the common scale is an amplifier, not the sole
cause.

## Aggregate calibration and intervals

| Pattern | Bias | MAE | RMSE | Spearman | >10 points | Point gate |
|---|---:|---:|---:|---:|---:|---|
| Full reference | -0.07 | 0.38 | 1.92 | 0.9974 | 0.39% | Pass |
| Mixed | +0.16 | 3.72 | 9.18 | 0.9388 | 9.37% | Fail rho |
| Partial Presence | +0.16 | 3.44 | 9.03 | 0.9417 | 8.58% | Fail rho |
| Traditional only | -0.76 | 6.10 | 12.96 | 0.8773 | 18.27% | Fail |
| Early transition | -0.24 | 5.17 | 11.48 | 0.9038 | 14.57% | Fail |

Player-grouped, cross-fitted aggregate conformal intervals achieve 90% coverage of 90.08% for
mixed, 90.24% for partial Presence, 90.08% for traditional-only, and 90.16% for early transition.
Mean 90% widths are respectively 18.60, 16.16, 52.67, and 37.68 points. This replaces the overly
conservative propagated intervals for research-2 output without changing central quality.

Full-reference 90% coverage is 90.31% with mean width 1.43. This audit uses masked-anchor residuals
and does not mistake natural adjacent-season performance volatility for measurement error.

## Ranking and career-length findings

Capped area causes the most pairwise reversals, followed by breadth and run. At a ten-point
full-form gap, ordering accuracy is 92.13% for mixed, 93.64% for partial Presence, and 80.13% for
traditional careers. At twenty points it rises to 98.64%, 99.44%, and 94.38%.

Long careers calibrate best because repeated evidence can average some error: partial-Presence
long-career MAE/rho is 2.43/0.9831 and mixed is 3.06/0.9686. Short careers retain low MAE but weak
rank correlation; traditional medium careers are worst at 7.41/0.8792. Correlated player-level
measurement effects prevent simple averaging from resolving every long career.

## Status and historical cases

No non-full pattern passes every predeclared point gate. The research-2 status distribution is
therefore unchanged:

- 1,976 `OFFICIAL_LONGEVITY_POINT`
- 0 `PROVISIONAL_LONGEVITY_POINT`
- 2,210 `LONGEVITY_INTERVAL_ONLY`
- 917 `LONGEVITY_UNAVAILABLE`

The eight requested early-era cases remain interval-only. Their expected breadth, area, run,
central diagnostic, and 90% intervals are retained in the case-study artifact. This is not a
quality penalty and does not create a point rank. Active careers remain `TO_DATE_NO_PROJECTION`.

## Tests and reproducibility

- full repository suite: 275 passed, one opt-in network test skipped;
- Ruff lint: all repository files pass;
- Ruff format: all four changed Python files pass;
- strict Mypy: 34 source files pass;
- artifact validation: exact row counts, interval nesting, statuses, frozen inputs, forbidden-input
  controls, and fingerprint pass;
- cache-only replay: zero network requests and fingerprint
  `15dd0713f3629e0e4a39b0ac718061053e08054ff49f498fe284e3cce83b1c9c` reproduced;
- replay runtime: approximately 126 seconds.

Generated Gold contains 13,854 rows across six ignored Parquet artifacts. The largest artifact is
the 7,620-row masked component validation table. No generated Bronze, Silver, or Gold data is
committed.

## Verdict

The frozen Longevity philosophy is coherent under correlated simulation and supports calibrated
point estimates for full-reference evidence plus intervals for weaker forms. It does not support
ranking-grade point estimates for important non-full historical evidence patterns. The problem is
not merely longest-run discreteness and is not fixed by a central-summary, threshold, run-weight,
or ECDF-order change.

STEP-0015J is **PASS** because reconstruction, decomposition, ablation, threshold/run forensics,
interval calibration, status assignment, case studies, regression checks, and reproducibility all
complete. The verdict is **LONGEVITY_AGGREGATION_LIMITED**. No production methodology is created.

Peak remains the stronger downstream candidate from STEP-0015I, while Longevity must retain an
interval policy for weaker evidence. Recommended next step:
**READY_FOR_PEAK_PROMOTION_WITH_LONGEVITY_INTERVAL_POLICY**.
