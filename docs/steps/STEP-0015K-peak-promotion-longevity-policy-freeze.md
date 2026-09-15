# STEP-0015K — Peak V2 Promotion & Longevity Interval Policy Freeze

Date: 2026-09-15

Result: **PASS**

Peak verdict: **PROMOTE_PEAK_V2_WITH_LIMITATIONS**

Longevity verdict: **FREEZE_LONGEVITY_TIERED_POLICY**

Overall verdict: **OVERALL_REMAINS_FROZEN**

Recommendation: **READY_FOR_OVERALL_UNCERTAINTY_ARCHITECTURE_AUDIT**

## Objective

Consolidate the validated findings from STEP-0015H through STEP-0015J. This step promotes the
uncertainty-aware Peak successor, freezes the evidence-dependent Longevity output policy, defines
production-facing status semantics, and audits seven-dimension point eligibility. It does not
redesign PlayerSeasonValue, Peak, or Longevity; change weights or thresholds; calculate a new
Overall score; or alter the published V1 ranking.

## Binding inputs and reconstruction

The pipeline verifies these fingerprints and artifact hashes before writing successors:

| Input | Fingerprint / SHA-256 | Reconstruction |
|---|---|---|
| STEP-0015H | `4b1ff850f9d0df43ffd271af16277d94abd3f14cba1a9a8aa679cb3983710f54` | 22,457 rows, 0 mismatches, max difference 0.0 |
| STEP-0015I | `4f44cf63450105d8c215aa20a0b3078dc8b9b5c907f2f03553eff390195a150a` | 5,103 Peak rows, 0 mismatches, max difference 0.0 |
| STEP-0015J | `15dd0713f3629e0e4a39b0ac718061053e08054ff49f498fe284e3cce83b1c9c` | 5,103 Longevity rows, 0 mismatches, max difference 0.0 |

The season measurement contract preserves raw Candidate D, linked estimate where eligible, score
status, evidence regime, nested 80/90/95 intervals, confidence, Presence reliability, observed and
missing channels, and reason codes. These fields are not collapsed into one number.

## Peak V2 promotion

`goatlab-v1-peak-v2` uses the frozen architecture:

`Peak = 70% best contiguous three-year PlayerSeasonValue + 30% single-season apex`

Within each of 2,500 fixed-seed `U3_STRATIFIED_BLOCK` draws, the pipeline draws a correlated career
path, reselects the best complete three-year window, reselects the apex, applies 70/30, and maps the
result through the fixed `BROAD_HIGH_RECALL` ECDF. It does not freeze a central-estimate window,
redraw the population scale, use incomplete windows, or project active careers.

### Final validation

| Evidence pattern | Bias | MAE | Spearman | 90% coverage | Gate |
|---|---:|---:|---:|---:|---|
| Full/reference | -0.004 | 0.377 | 0.9999 | 100.00% | official point |
| Mixed | +0.073 | 3.933 | 0.9842 | 90.79% | pass |
| Partial Presence | +0.544 | 3.099 | 0.9891 | 91.73% | pass |
| No Presence | +0.265 | 4.405 | 0.9806 | 93.39% | fail interval gate |
| Traditional only | -0.267 | 6.660 | 0.9548 | 91.34% | fail error gates |
| Early transition | +0.232 | 5.242 | 0.9720 | 92.52% | fail MAE gate |

The evidence justifies point use for reference, mixed, and partial-Presence careers. Traditional
and other weak patterns retain calibrated ranges but do not receive ranking-grade points. The
promotion verdict is therefore `PROMOTE_PEAK_V2_WITH_LIMITATIONS`, not universal point promotion.

### Peak statuses and unavailable reasons

| Status / reason | Players |
|---|---:|
| `OFFICIAL_PEAK_POINT` | 974 |
| `PROVISIONAL_PEAK_POINT` | 1,411 |
| `PEAK_INTERVAL_ONLY` | 71 |
| `PEAK_UNAVAILABLE` | 2,647 |
| fewer than three qualifying seasons | 2,529 |
| no contiguous qualifying three-season window | 118 |
| measurement unavailable with otherwise sufficient career | 0 |

The last decomposition matters: generic unavailable reporting previously mixed measurement limits
with careers that cannot constitutionally supply a three-season Peak. A two-season career is
ineligible for this construct; it is not a historical-data failure.

## Longevity policy freeze

`goatlab-v1-longevity-v2-tiered` reaffirms P80 = 80, P90 = 90, and:

`35% elite breadth + 40% capped P80-P90 area + 25% longest P80 run`

STEP-0015J established that run is the weakest isolated component, capped area causes the most
pairwise reversals, and P80 uncertainty moves all three components together. P78/P88 through
P82/P92 and run weights from 20% to 30% do not reverse the conclusion. The philosophy is not
rejected; point precision is evidence-dependent.

The final status distribution is:

- 1,976 `OFFICIAL_LONGEVITY_POINT`;
- zero `PROVISIONAL_LONGEVITY_POINT`;
- 2,210 `LONGEVITY_INTERVAL_ONLY`;
- 917 `LONGEVITY_UNAVAILABLE`.

An interval-only row retains a central diagnostic, nested intervals, expected elite breadth,
capped-area distribution, longest-run distribution, run-bridge metadata, confidence, and reason
codes. Its central diagnostic is not an official ranking point.

## Overall eligibility contract

The frozen seven-dimension availability audit yields:

| Class | Players | Meaning |
|---|---:|---|
| `COMPLETE_POINT_DIMENSIONS` | 641 | all seven required dimensions have ranking-grade points |
| `INTERVAL_DIMENSION_PRESENT` | 1,241 | no required dimension is absent, but at least one is interval-only |
| `REQUIRED_DIMENSION_UNAVAILABLE` | 3,221 | at least one required dimension is unavailable |

No Overall score or rank is calculated. An interval or missing Longevity dimension may not be
dropped, have its 14% redistributed, be replaced with a midpoint as though exact, or trigger a
confidence penalty. The next research question is how to propagate dimension uncertainty through
the fixed weighted architecture and report Overall intervals, pairwise probabilities, and robust
rank bands.

## Policy examples

All requested early-era examples have provisional Peak points and interval-only Longevity. Their
Peak central / 90% interval and Longevity central diagnostic / 90% interval are:

| Player | Peak | Best window | Longevity |
|---|---|---|---|
| George Mikan | 95.58 [87.99, 98.55] | 1948-50 | 91.92 [82.46, 100.00] |
| Bob Pettit | 99.82 [96.40, 100.00] | 1958-60 | 97.95 [88.49, 100.00] |
| Bill Russell | 99.82 [96.44, 100.00] | 1961-63 | 98.81 [89.36, 100.00] |
| Wilt Chamberlain | 99.37 [95.46, 100.00] | 1965-67 | 98.44 [88.98, 100.00] |
| Oscar Robertson | 99.82 [95.95, 100.00] | 1960-62 | 99.27 [89.81, 100.00] |
| Elgin Baylor | 99.25 [95.00, 100.00] | 1960-62 | 98.21 [88.75, 100.00] |
| Jerry West | 98.51 [92.85, 100.00] | 1964-66 | 99.23 [89.77, 100.00] |
| Kareem Abdul-Jabbar | 99.82 [98.19, 100.00] | 1969-71 | 99.83 [90.37, 100.00] |

Modern examples demonstrate that statuses follow evidence, not reputation. Stephen Curry is the
only requested example with both an official Peak point and official Longevity point, and thus a
complete point-dimension profile. Jordan, LeBron, Shaq, Duncan, Garnett, Jokic, Giannis, and Gobert
have provisional Peak points but interval-only Longevity; their Overall eligibility is
`INTERVAL_DIMENSION_PRESENT`. These are eligibility labels, not rankings.

## Active careers and public explanation

Active players remain `TO_DATE_NO_PROJECTION`. Peak uses completed qualifying windows and
Longevity uses observed seasons through 2025-26. No future awards, games, seasons, runs, or titles
are simulated.

Historical players are not penalized because a statistic was unavailable. GOATLab reports wider
uncertainty or a range when evidence cannot support the same point precision. A range is not a
lower score. Confidence describes how precisely the evidence measures quality; it does not measure
or reduce quality itself.

## Outputs and reproducibility

Five ignored Gold Parquets contain 42,773 rows: the season contract, Peak V2, tiered Longevity,
Overall eligibility, and named policy examples. Small JSON/YAML registries and reports are
committed. The combined deterministic fingerprint is
`3325c28ae452b84d347b067e509a2c1038a3102a0ce0e56ccd68b25681a2bc5f`.

V1 preservation hashes are unchanged:

- dimension scores: `4fcd1aeb7dfff5ab85a2afafc96b1b6845736d49801946d43480d387fb17d6c4`;
- Overall V1: `ab9ae910754d82cb260eb3fe0c747c6b58351ce20510be9707f9b484525e9547`;
- Top 100 V1: `1a08c1f61f428b84a8599cfdfc0dcf62eec4e5976d6f6f22949bc3b02dc66d8f`.

## Result

STEP-0015K is **PASS**. Peak V2 is promoted with explicit limitations; the Longevity interval
policy is frozen; Overall remains frozen; and no new Top 100 is generated. The STEP-0015 forensic
branch is closed at this policy boundary. The next step is
**READY_FOR_OVERALL_UNCERTAINTY_ARCHITECTURE_AUDIT**.
