# STEP-0015H — Evidence-Regime Measurement Linking & Uncertainty Audit

Date: 2026-09-15

Result: **PASS**

Architecture verdict: **LIMITED_TIERED_ARCHITECTURE**

## Objective

Test whether Candidate D's factual historical evidence regimes can be treated as measurement
forms linked to the `FULL_PORTABLE` reference scale, with calibrated uncertainty and without
predicting missing statistics.

## Binding controls

- Candidate D remains frozen as `goatlab-v1-player-season-value-v2-research`.
- No V1 dimension, Peak, Longevity, Defense, or Overall output is modified.
- No award, postseason, championship, player identity, external ranking, or modern-only validator
  enters a linker.
- Confidence, uncertainty, and quality are separate.
- `FULL_PORTABLE` is the reference form, not asserted truth.

## Inputs and reconstruction

- STEP-0015G fingerprint:
  `120c319c8b3883b2066187947d3a6b813aa4d590231035fdd02943486268dd4f`.
- Recovered Silver hash:
  `0a94bc25061d860f1916d7f691f4d53e16260c3c0e9932ef86ff2791603a52c3`.
- Candidate D hash:
  `d2dd838acd5f3e9e7fd732ebf967c53a59944fba1067eca95bbb148725a7f00a`.
- Frozen dimensions:
  `0dcd568b6ba69250f097b50835882582e75d043f42ae4057ff5721dbfc6e9b2a`.
- Frozen Overall:
  `02bacaaacbff1a038ca0b5a82c6d3b51e34e192426e51ad8f0b72cd89bda97aa`.

All 22,457 rows, 21,107 Candidate D scores, evidence regimes, provenance, and confidence metadata
reproduce. Raw and percentile mismatches are zero; maximum difference is `0.0`.

## Methods

The audit creates paired measurements by masking each of 14,687 full-form seasons into seven
weaker factual forms. It compares identity, linear, equipercentile, isotonic, and optional
broad-role isotonic linkers. Selection uses player-grouped five-fold validation with a simplicity
tolerance. Random folds, leave-decade-out folds, and earlier/later directional transfer are
reported as secondary transport tests.

Split-conformal 80/90/95% intervals use disjoint fit, calibration, and player-grouped test folds.
Empirical OOF intervals are retained as a secondary comparison. The predeclared point gates are
applied exactly; failed forms are interval-only even when their linked mean bias is near zero.

## Findings

Linking solves location/scale error but cannot restore missing order information. The no-Team-
Context form (MAE 2.07, Spearman 0.9960), expanded proxy actions with Presence (1.60, 0.9972), and
traditional box with Presence (3.53, 0.9867) pass every point gate. Expanded/no-Presence (6.13,
0.9640), traditional/no-Presence (7.62, 0.9415), early offense-plus-Presence (13.37, 0.8081), and
offense-only (8.55, 0.9271) do not.

Nominal 90% split-conformal coverage is 89.83%–90.20% across forms. Mean 90% widths range from
6.72 points for expanded proxy actions with Presence to 51.84 for early offense plus Presence.
The width, rather than a score penalty, expresses weaker evidence.

Actual historical status is 14,687 `OFFICIAL_POINT`, 3,831 `PROVISIONAL_POINT`, 3,937
`INTERVAL_ONLY`, and two `UNAVAILABLE`. The official label describes the reference measurement
form inside this research architecture; it does not promote Candidate D itself.

Pre-1950 receives interval-only treatment when observed offense exists, never invented rebounds.
The 1970s team-context omission is repairable as a provisional measurement, but missing
STL/BLK/Presence still prevents many traditional-form point estimates.

Pairwise analysis confirms why intervals matter: expanded/no-Presence ordering is only about 70%
correct for seasons separated by roughly five full-form points, rising to about 97% around twenty
points. Robust non-overlap declarations are less frequent and much more accurate.

## Downstream diagnostics

The frozen Peak 70/30 architecture is extended diagnostically with correlated uncertainty draws,
yielding 2,456 player intervals and alternate plausible windows. Longevity reports P80/P90
exceedance probabilities and an approximate expected P80 run for 4,186 players. Neither dimension
is promoted; both require a dedicated aggregation audit.

## Quality, reproducibility, and result

The implementation is deterministic, monotone, player-group cross-fitted, era-transfer audited,
and contains no missing-stat imputation or player-specific logic. Generated analytical Parquet
remains ignored; committed JSON reports and documentation retain fingerprints and reason codes.

STEP-0015H is **PASS** because reconstruction, linking, transport, interval calibration, status,
pairwise, and downstream diagnostics complete reproducibly. The substantive verdict is
**LIMITED_TIERED_ARCHITECTURE**: some forms support provisional points, while no-Presence and
sparse forms remain interval-only.

The complete suite passes with 252 tests and one opt-in network test skipped. Ruff, strict Mypy
across 32 package files, JSON/Parquet checks, and Git whitespace validation pass. A second offline
run makes zero network requests and reproduces fingerprint
`4b1ff850f9d0df43ffd271af16277d94abd3f14cba1a9a8aa679cb3983710f54` in approximately 31 seconds.

Recommended next step: **READY_FOR_PEAK_LONGEVITY_UNCERTAINTY_AUDIT**.
