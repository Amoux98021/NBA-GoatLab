# STEP-0015D — Universal player-season value measurement audit

## 1. Objective

Develop and audit a historically portable, era-relative measure of overall individual Regular
Season basketball value for one player-season, without overwriting any V1 output or treating the
primitive as an eighth GOAT dimension.

## 2. Motivation

STEP-0015C retained Peak's 70/30 window architecture but rejected its V1 SeasonQuality input because
a team-season constant dominated attribution. The same upstream quality construct also informs
Longevity. STEP-0015D therefore tests the measurement layer before either downstream dimension can
be revised.

## 3. Constitutional requirements

- Individual Regular Season performance must dominate team context.
- Multiple offensive and defensive pathways may produce elite value.
- Missing evidence is not zero, and evidence confidence cannot alter quality.
- Awards, postseason performance, championships, reputation, player-name features, and projections
  are excluded.
- Modern evidence is validation-only unless a bridge passes.
- V1 SeasonQuality, Peak, Longevity, Defense, and Overall remain immutable baselines.

## 4. Inputs and fingerprints

The pipeline verifies Constitution `f7a67adb161de086e9d47b0eaa3b9606cfb42cc70f15341c2a225586403c6ad5`,
STEP-0014 `0dcd568b6ba69250f097b50835882582e75d043f42ae4057ff5721dbfc6e9b2a`,
STEP-0015 `02bacaaacbff1a038ca0b5a82c6d3b51e34e192426e51ad8f0b72cd89bda97aa`,
STEP-0015B `103c3cf826393e70712b8aa2f5692ef32dad077b1556870ebb33a211cf8c171f`,
and STEP-0015C `a9db1e7f75b3f3b8af9474bf556917b98f8aceeeb890fdc9ba36bdf7c3de7287`.
No network access is used.

## 5. Evidence and regimes

The audit inventories 22,457 qualified Regular Season rows for all 5,103 players. Actual channel
coverage produces four row-level regimes: 5,881 early-limited, 55 traditional-box, 2,153
expanded-box/no-Presence, and 14,368 full-portable rows. Regimes intentionally overlap in calendar
time because coverage is empirical.

## 6. Candidate methods

Four predeclared candidates test transparent portable evidence, multi-path value, a full-observation
defensive measurement benchmark, and continuous-reliability Presence. The selected research
candidate uses 60/40 stronger/secondary scoring and creation; a defensive channel with 10% team,
up to 35% reliability-weighted observed Presence, and remaining weight on individual actions; then
55/45 stronger/secondary offense and defense. Total team weight is capped at 5.5%.

This is `goatlab-v1-player-season-value-v2-research`, explicitly not production methodology.

## 7. Masking, influence, and fairness

On 14,155 rich-evidence rows, hiding Presence causes 5.73-point MAE and hiding both Presence and
expanded actions causes 8.48-point MAE. Early masking makes the candidate unavailable. Errors vary
by role and archetype. Candidate D's offense/defense covariance shares are 63.47%/36.53%; team
context's share is 0.13% and its value correlation is 0.071. Adjacent-season Spearman is 0.7700;
team-change pairs move more than same-team pairs.

The prior expected-Presence fallback has only 0.0174 player-grouped out-of-fold R-squared. No latent
defensive value is represented as observed.

## 8. Downstream diagnostics

Peak retains 70% complete contiguous three-year value plus 30% apex. Its research counterfactual
has 1,761 scores and 0.9057 Spearman with V1. Longevity retains its 35/40/25 breadth/area/run formula,
has 2,950 diagnostic scores, and 0.7832 Spearman with V1. Their candidate correlation is 0.8691.
The Peak-only Overall counterfactual has 0.9937 Spearman and 90%/96%/90%/95% Top-10/25/50/100
overlap on 1,391 common ranked players. Nothing is promoted.

## 9. Independent validation

Validation-only MVP and All-NBA First Team seasons are concentrated in the selected research
candidate's elite tail, and adjacent seasons have substantial persistence. These labels were not
used to fit, weight, select, or calibrate a formula.

## 10. Known limitations

- Candidate coverage is 73.81%, far below universal historical requirements.
- Early-limited rows cannot be mapped to the proposed construct.
- Presence remains a noisy WOWY-style proxy, not causal or lineup-adjusted impact.
- Role-aware box actions are not total defense.
- The expected-Presence bridge failed out-of-sample.
- Regime masking remains materially and non-uniformly wrong.
- Action primitive influence allocations explain a composite and are not causal event shares.

## 11. Tests and reproducibility

Offline unit and artifact tests cover formula determinism, missingness, observed zero, continuous
Presence reliability, team-context cap, confidence separation, evidence regimes, ownership,
Regular Season scope, unchanged Peak/Longevity architectures, frozen V1 preservation, bounded
counterfactuals, and deterministic hashes. The complete suite passed 206 tests with one opt-in
network test skipped. Ruff passed, strict Mypy passed for 28 source files, and the four new Python
files passed format validation. A second zero-network execution reproduced all five Gold files and
committed report hashes. The output fingerprint is
`f96ee13b7aa7ba6101e2ad80b757cc28179a52b378cbd961ceb3f739bdcae282`; Gold occupies 2,275,129
bytes and the certification run took 7.15 seconds.

## 12. Result

**PASS + PROMISING_BUT_NOT_READY.** PASS describes the completed reproducible audit. The separate
measurement verdict declines production promotion. No ADR is created because no production
methodology decision is accepted.

## 13. Next step

Research an uncertainty-aware historical evidence bridge for missing creation and defensive impact,
then rerun the same masking and coverage gates. Do not promote Peak or Longevity until a universal
PlayerSeasonValue construct passes.
