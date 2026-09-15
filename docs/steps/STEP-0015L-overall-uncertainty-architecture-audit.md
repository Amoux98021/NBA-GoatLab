# STEP-0015L — Overall Uncertainty Architecture Audit

Date: 2026-09-15

Result: **PASS**

Architecture verdict: **LIMITED_OVERALL_UNCERTAINTY_ARCHITECTURE**

Recommendation: **READY_FOR_OVERALL_PROMOTION_AFTER_DEFENSE**

## Objective

Determine whether the frozen seven-dimension weighted Overall can honestly propagate a mixture of
point and interval-valued evidence while preserving every constitutional weight. This step audits
uncertainty mechanics only. It does not modify any dimension, promote Overall, or publish a new
Top 100.

## Inputs and exact reconstruction

STEP-0015K fingerprint
`3325c28ae452b84d347b067e509a2c1038a3102a0ce0e56ccd68b25681a2bc5f` is verified before work.
The pipeline reproduces 5,103 Peak V2 rows, 5,103 tiered Longevity rows, and 5,103 eligibility
rows with zero status mismatch and maximum numerical difference 0.0. Frozen V1 hashes remain:

- dimensions: `4fcd1aeb7dfff5ab85a2afafc96b1b6845736d49801946d43480d387fb17d6c4`;
- Overall: `ab9ae910754d82cb260eb3fe0c747c6b58351ce20510be9707f9b484525e9547`;
- Top 100: `1a08c1f61f428b84a8599cfdfc0dcf62eec4e5976d6f22949bc3b02dc66d8f`.

## Frozen architecture

For each of 2,500 paired `U3_STRATIFIED_BLOCK` career draws:

`Overall = .17 Peak + .14 Longevity + .16 Offense + .14 Defense + .18 Playoffs + .10 Accolades + .11 Winning`

Peak window reselection, Longevity thresholds/runs, fixed ECDFs, within-career dependence, and
`TO_DATE_NO_PROJECTION` remain upstream invariants. The same draw index supplies Peak and
Longevity. The other five dimensions are fixed. No weight is redistributed.

## Central estimator and intervals

The selected central estimator is the median of the paired Overall draws. Mean and weighted
dimension medians are audited alternatives. Player-grouped, cross-fitted calibration preserves
the shape of each paired-draw distribution and produces nested 80/90/95 intervals. These ranges
describe measurement uncertainty under the current method, not future outcomes or quality
penalties.

## Validation and gates

The validation population contains 1,200 full-form careers with all five fixed dimensions. Each
is remeasured under six historical patterns. Point gates are MAE <= 2, Spearman >= 0.98, absolute
bias <= 1, no more than 10% above five points, and 87%–93% nominal 90% coverage.

Mixed evidence passes at MAE 1.157, Spearman 0.9957, and bias +0.026. Partial Presence passes at
0.970, 0.9961, and +0.125. No-Presence and early-transition patterns also pass after weighted
aggregation. Traditional-only is retained as interval-only because its >5-point share is 10.25%,
despite MAE 1.935, Spearman 0.9901, and bias -0.158.

Calibrated 80/90/95 coverage for mixed evidence is 79.83%/90.33%/95.17%; partial Presence is
80.25%/90.25%/95.00%; traditional-only is 80.17%/90.00%/95.17%. Outer interval levels are expanded
when separately calibrated bounds would cross, preserving interval nesting.

## Joint dependence and cancellation

There is no general cancellation. Peak–Longevity uncertainty is positively correlated and the
covariance term increases Overall variance in every pattern. Mean paired-draw correlation is
0.586 for mixed, 0.550 for partial Presence, and 0.647 for traditional careers. Independent
marginal recombination understates mean 90% interval width by about 15%–21% across these patterns.
Analytic `a²Var(P)+b²Var(L)+2abCov(P,L)` and empirical variance agree to numerical tolerance.

## Status taxonomy and actual counts

- `OFFICIAL_OVERALL_POINT`: all required dimensions are official and the Overall gate passes;
- `PROVISIONAL_OVERALL_POINT`: a provisional or interval-valued input is fully propagated and the
  complete Overall distribution passes its point gate;
- `OVERALL_INTERVAL_ONLY`: every dimension has a usable distribution but its Overall pattern
  fails the point gate;
- `OVERALL_UNAVAILABLE`: at least one required dimension has neither a point nor useful interval.

| Scope | Official | Provisional | Interval only | Unavailable |
|---|---:|---:|---:|---:|
| All 5,103 | 602 | 1,280 | 0 | 3,221 |
| `BROAD_HIGH_RECALL` 2,656 | 602 | 1,280 | 0 | 774 |
| Frozen V1 Top 100 | 16 | 84 | 0 | 0 |

The prior Top 100 is not reordered. Its V1 points remain archived methodology facts.

## Blocking reasons

Counts are non-exclusive: 2,963 Accolades `NOT_QUERIED`; 2,647 Peak constitutionally ineligible;
2,335 Playoffs insufficient sample; 2,210 Longevity interval-only; 973 Defense unavailable; 917
Longevity unavailable; 916 Offense unavailable; 71 Peak interval-only; and one Winning
unavailable. Interval-only is a modeled distribution, not the same state as unavailable.

## Forbidden approaches

`DROP_AND_RENORMALIZE`, `INTERVAL_MIDPOINT_AS_EXACT`, and `CONFIDENCE_PENALTY` are evaluated only
as rejected diagnostics. Renormalization changes the construct; midpoint substitution discards
covariance and uncertainty; confidence multiplication produces approximately four points of
negative bias in non-reference patterns. None enters any final research output.

## Pairwise, rank, and Top-N diagnostics

For mixed evidence, central ordering accuracy is 61.7% at an approximately 0.5-point gap, 73.8%
at one, 84.3% at two, 91.7% at three, 95.5% at five, and 99.4% at ten. Research labels use 90% as
robust, 65%–90% as lean, and 35%–65% as uncertain, with symmetric reverse labels.

Rank simulations preserve within-player Peak/Longevity dependence. Players are conditionally
independent across careers given the frozen calibration model; shared linker/calibration
uncertainty is not modeled. Median rank, 80/90 bands, and Top 10/25/50/100 probabilities are
diagnostic only. On mixed validation, central Top-N overlaps are 100%/96%/94%/94%, with Brier
scores 0.00082/0.00165/0.00334/0.00609.

## Player examples

Early-era examples all have provisional research Overall points because their interval-only
Longevity distributions attenuate sufficiently at 14% to pass the Overall gate. Their diagnostic
centers and 90% intervals include: Mikan 96.72 [94.94, 97.30], Russell 97.09 [96.44, 97.15], Wilt
95.40 [94.57, 95.54], West 96.52 [95.53, 96.78], and Kareem 98.21 [97.94, 98.25].

Among named modern examples, Curry is official (93.64 [93.50, 93.71]); Jordan, LeBron, Bird,
Duncan, Shaq, Garnett, Hakeem, Jokic, Giannis, and Gobert are provisional because Longevity is
interval-only. These are status illustrations, not rankings.

## V1 comparison and Defense caveat

For 1,882 usable diagnostic rows, research centers versus archived V1 Overall have Spearman
0.9730, Pearson 0.9757, MAE 3.224, RMSE 4.517, and bias +0.006. Changes arise only from the Peak
and Longevity successor inputs; other contribution change is zero.

Every row is labeled `DEFENSE_V1_FROZEN_PENDING_REVISION`. The architecture can be evaluated for
1,882 players, but Overall cannot be promoted while Defense retains its demonstrated attribution
defect. This step does not substitute Defense V2.

## Outputs, tests, and result

Six ignored Gold Parquets contain masked validation, all-player uncertainty/status, conditional
rank uncertainty, the unreordered V1 Top-100 transition, named examples, and V1 comparison. Small
JSON/YAML reports and the accepted architecture ADR are committed. All outputs are deterministic.
The combined output fingerprint is
`cb740fc68a77df3cb30b68e854e413c670394638ff2bf7b47401b905c7a81580`.

STEP-0015L is **PASS + LIMITED_OVERALL_UNCERTAINTY_ARCHITECTURE**. The fixed weighted sum can
honestly aggregate paired uncertainty for supported evidence patterns, but missing dimensions and
traditional-only patterns remain unavailable/interval-native. Overall V1 stays frozen, no Overall
V2 is promoted, and no new Top 100 is created. The next step is
**READY_FOR_OVERALL_PROMOTION_AFTER_DEFENSE**.
