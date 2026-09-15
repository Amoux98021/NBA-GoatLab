# STEP-0015I — Peak & Longevity Uncertainty Propagation Audit

Date: 2026-09-15

Result: **PASS**

Peak verdict: **PEAK_UNCERTAINTY_LIMITED**

Longevity verdict: **LONGEVITY_UNCERTAINTY_LIMITED**

## Objective

Determine whether the frozen 70/30 Peak and 35/40/25 Longevity architectures can consume the
uncertainty-aware STEP-0015H PlayerSeasonValue evidence without changing their constitutional
meanings or presenting sparse historical evidence with false precision.

## Binding controls and inputs

Candidate D, STEP-0015H linking, V1 Peak, V1 Longevity, V1 Defense, and V1 Overall remain frozen.
The audit uses no award, postseason, championship, player-name feature, projection, or manually
selected window. Input fingerprints are:

- STEP-0015H: `4b1ff850f9d0df43ffd271af16277d94abd3f14cba1a9a8aa679cb3983710f54`
- linked seasons: `2908de32b614b96e405630334e07aeb262d690536c0c33fc7fe77b6f51ff6dc4`
- anchor pairs: `1821e4d7a15fccb70819f49d234f019ce75cba06613a86c80cc07e04fb8d202a`
- Constitution: `f7a67adb161de086e9d47b0eaa3b9606cfb42cc70f15341c2a225586403c6ad5`

All 22,457 season rows, 14,687 anchors, linked values, intervals, statuses, and regimes reproduce
with zero mismatches and maximum numerical difference `0.0`. Preliminary STEP-0015H coverage of
2,456 Peak and 4,186 Longevity players also reproduces.

## Uncertainty method

Residual dependence is material. Adjacent-season correlation ranges from 0.120 for expanded
no-Presence to 0.614 for traditional-with-Presence. Player-effect variance shares range from
43.63% to 71.12%; same-team residual correlation generally exceeds changed-team correlation.

Four methods were compared. Independent draws are baseline-only. Player-block and role-block
methods preserve progressively more dependence. The selected `U3_STRATIFIED_BLOCK` method
preserves a player component and samples empirical residual paths within measurement form, broad
role, archetype, and score band when supported. It achieved the best joint calibration on the
predeclared mixed pattern: Peak MAE 4.22/Spearman 0.9804/90% coverage 90.33%; Longevity MAE
4.23/Spearman 0.9277/90% coverage 95.33%.

The final deterministic budget is 2,500 draws. Against 2,500 draws, the 1,000-draw mean absolute
difference is 0.15 Peak points for the median and 0.32 Longevity points. Rare discrete run/ECDF
boundary cases retain large worst-case differences, so 300 draws are insufficient and 2,500 is
retained.

## Aggregate validation

The full-form reference set has 1,270 careers with at least five full-portable seasons and a
complete three-season window. Six realistic patterns are tested: full reference, no Presence,
traditional-only, early traditional-to-expanded, late partial Presence, and mixed
provisional/interval.

Peak supports a point estimate for partial-Presence and mixed patterns. Their MAE/Spearman/bias
are respectively 3.10/0.9891/0.54 and 3.93/0.9842/0.07, with calibrated 90% coverage. Traditional
and historical-transition patterns remain interval-only. The simulation reselects the window and
apex per draw, slightly improves best-window recovery, and reduces net maximum-selection bias.

Longevity does not support a non-full point pattern. Partial-Presence and mixed MAEs are 3.44 and
3.72, but Spearman values of 0.9417 and 0.9388 miss the 0.95 gate and their 90% intervals are
conservative. Traditional-only MAE is 6.10 and Spearman 0.8773. The intervals are informative, but
the ranking-grade point interpretation is not validated.

## Peak mechanics

Every draw finds complete contiguous three-season windows, selects the best window, selects the
apex, and applies 70/30. Incomplete/gapped windows never qualify. Final output reports central
Peak, nested 80/90/95 intervals, best-window probability, supported alternative windows, and
`STABLE_WINDOW`, `COMPETING_WINDOWS`, or `UNCERTAIN_WINDOW` independently of score.

There are 974 official-form points, 1,411 provisional points, 71 interval-only results, and 2,647
unavailable players. Among the 2,456 measured players, 1,994 windows are stable, 385 compete, and
77 are uncertain.

## Longevity mechanics

The common linked-scale thresholds are fixed at P80=80 and P90=90 for every era. In every draw,
the audit calculates the number of P80 seasons, capped fractional area from P80 to P90, and exact
longest consecutive P80 run before applying 35/40/25. Outputs retain season exceedance
probabilities, expected capped area, median/modal run, run probabilities, and intervals.

There are 1,976 official-form points, 2,210 interval-only results, and 917 unavailable players.
No provisional Longevity point is emitted because no tested non-full career pattern passes all
aggregate gates.

## Scaling, distinctness, and ordering

Each draw is transformed through a fixed `BROAD_HIGH_RECALL` midrank ECDF. The reference is never
redrawn, so uncertainty represents player measurement rather than population drift. Peak uses
2,456 fixed reference values; Longevity uses 2,656.

Across 2,456 jointly measured players, Peak-Longevity Spearman is 0.8789 and Pearson is 0.8806;
Longevity retains 22.45% residual variance after its linear relationship with Peak. Peak uses only
apex height, while Longevity uses thresholded and capped duration across the observed career.

Pairwise ordering is weak for close scores and improves with separation. For the early-transition
pattern, uncertainty-aware Peak ordering rises from 62.97% at a two-point gap to 97.98% at twenty
points. Interval-declared robust orders are uncommon at close gaps but highly accurate where made.

## Historical and active-career findings

All eight early-era cases receive provisional Peak points but interval-only Longevity. Their best
windows often compete because shared measurement-form residuals persist across a career; this is
reported rather than resolved by reputation. The predetermined modern controls show the same
behavior when artificially masked, and full-form targets usually remain within calibrated
intervals.

Active players are marked `TO_DATE_NO_PROJECTION`. Peak considers only completed qualifying
windows through 2025-26; Longevity uses only observed seasons and never projects future thresholds
or runs.

## Tests, outputs, and result

The implementation adds typed deterministic aggregation utilities and checks exact reconstruction,
dependency-preserving draws, window contiguity/reselection, exact longest runs, frozen weights and
thresholds, interval nesting, no leakage, active-career treatment, full-universe output, and
fingerprints. Generated Parquet remains ignored; committed JSON and Markdown retain audit evidence.

The full suite passes with 265 tests and one opt-in network test skipped. Ruff and strict Mypy over
33 package files pass. An offline rebuild makes zero network requests and exactly reproduces
fingerprint `4f44cf63450105d8c215aa20a0b3078dc8b9b5c907f2f03553eff390195a150a`
in approximately 55 seconds. Principal Parquet hashes are Peak
`77b19ada90ba9d6163aaaaeccf341355d5ef9af12f5af04c6902ae7dbe569ea2`, Longevity
`40944bb52d31edbcb6dc54dc0b83396827ed7a201fb4d73bebf1429af0313c9b`, and masked validation
`7789c2704a2dcd224a0902af25c8be2bd6173f1e21d3b6f9632259b8dc018f9f`.

STEP-0015I is **PASS** because every required reconstruction, dependence, propagation,
convergence, calibration, status, scaling, case-study, and reproducibility audit completes. Both
dimensions are **LIMITED**: Peak is valid for several aggregate evidence patterns, while Longevity
outside the full form remains interval-only. No production methodology is created.

Recommended next step: **MORE_AGGREGATION_RESEARCH**, focused on cross-era Longevity ordering,
threshold/run calibration, and conservative full-form uncertainty before any joint promotion.
