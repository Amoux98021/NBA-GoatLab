# STEP-0015E — Historical Evidence Bridge & Measurement-Invariance Audit

Date: 2026-09-14

Result: **PASS**

Bridge verdict: **NO_VALID_BRIDGE**

Recommendation: **REQUIRES_MORE_MEASUREMENT_WORK**

## Objective

Test whether missing creation and defensive-impact evidence can place early, intermediate, and
modern player-seasons on the same PlayerSeasonValue scale without inventing historical precision.
This is a measurement audit, not a promotion step.

## Binding constraints

- The GOATLab V1 Constitution controls missingness, ownership, and era fairness.
- Awards, postseason outcomes, championships, names, and conventional rankings are excluded from
  every predictor and selection rule.
- V1 Defense, Peak, Longevity, Overall, and STEP-0015D Candidate D remain unchanged.
- Missing evidence is never zero.
- Confidence and uncertainty never multiply quality.

## Inputs and reconstruction

The audit verifies the frozen STEP-0015D fingerprint
`f96ee13b7aa7ba6101e2ad80b757cc28179a52b378cbd961ceb3f739bdcae282`.

All 22,457 Candidate D rows, 16,576 scored rows, regimes, intermediate components, confidence
states, Peak counterfactual, and Longevity counterfactual reproduce. Maximum numerical difference
is 0 and there are zero mismatches.

## Evidence regimes and missing channels

Regimes remain observation-defined, not date-assigned:

| Regime | Player-seasons | Core limitation |
|---|---:|---|
| Early limited | 5,881 | APG absent in 5,863; action evidence absent in 5,242; TS absent in 5,321 |
| Traditional box | 55 | Presence absent; STL absent and BLK mostly absent |
| Expanded box/no Presence | 2,153 | Presence absent |
| Full portable | 14,368 | Required research channels observed; isolated action gaps are already handled upstream |

Among early rows, 4,311 expose only PPG plus shared team context. Another 783 lack team context.
This is the direct explanation for the unscored early population.

## Candidate bridges

Five policies were frozen before validation:

1. Strict observed evidence: no imputation.
2. Creation proxy only: PPG, then PPG+TS, estimate APG where validation permits.
3. Defensive bridge only: observed actions and bounded team context estimate the full defensive
   measurement.
4. Combined uncertainty-aware bridge: grouped creation plus defensive estimates.
5. Partial identification: use intervals when point gates fail.

Ridge models use quadratic terms and pairwise interactions only, fixed parameters, and player-ID
grouped folds. Player IDs define folds but are not model inputs. Decade-block transfer is reported
separately.

## Creation results

| Model | R² | Spearman | MAE (points) | >10-point error |
|---|---:|---:|---:|---:|
| PPG directly | 0.4208 | 0.7104 | 17.05 | 60.82% |
| PPG grouped ridge | 0.5043 | 0.7097 | 16.63 | 66.07% |
| PPG decade-block | 0.5045 | 0.7098 | 16.63 | 66.02% |
| PPG+TS grouped ridge | 0.5313 | 0.7286 | 16.13 | 64.81% |
| PPG+TS decade-block | 0.5310 | 0.7285 | 16.14 | 64.77% |

PPG contains real rank information about APG, but not enough to reconstruct individual creation.
The nearly identical random, grouped, and era-block performance means leakage is not hiding a
portable solution.

## Defensive measurement results

Against the complete-evidence defensive target:

| Available evidence | Grouped Spearman | MAE | Era-block Spearman | Interpretation |
|---|---:|---:|---:|---|
| Actions only | 0.7315 | 13.06 | — | incomplete |
| Actions + bounded team | 0.7515 | 11.45 | — | incomplete |
| Expanded, no Presence | 0.7606 | 9.48 | 0.7603 | not a Presence bridge |
| Traditional RPG + team | 0.6808 | 10.50 | 0.6808 | role distortion remains |
| Presence + team only | 0.7204 | 10.12 | 0.7200 | creation/actions still missing |
| Team only | 0.1710 | 14.01 | 0.1721 | fundamentally non-individual |

The latent-factor candidate explains 36.51% of measurement variance. Pooled loadings are actions
0.5615, team context 0.3239, and Presence 0.7615, but decade-specific loading similarity drops to
0.5933 in the 2000s and team context changes sign in the 1990s. Configural stability is not good
enough to claim an invariant latent defense construct.

## Historical masking and predeclared gates

The gate requires MAE <=5, Spearman >=0.95, absolute bias <=2, no more than 15% above ten-point
error, and absolute major-role bias <=3.

| Mask | MAE | Spearman | >10 points | Max role bias | Pass |
|---|---:|---:|---:|---:|---|
| Expanded box/no Presence | 7.27 | 0.9531 | 29.87% | 0.82 | No |
| Traditional box | 8.00 | 0.9405 | 32.71% | 2.33 | No |
| Early with Presence | 8.41 | 0.9278 | 33.45% | 2.66 | No |
| Early minimal | 11.35 | 0.8737 | 47.10% | 2.80 | No |

All masks are approximately mean-unbiased because they are compared as within-season ranks. That
does not rescue their individual errors. No mask passes every gate.

## Role and archetype findings

Aggregate role biases remain under the three-point gate, but individual error rates are high in
every role. The early-minimal mask exceeds ten-point error for roughly half the sample, and the
creation bridge systematically regresses specialized creators toward scoring-derived expectation.
Named-player artificial masks are reported only after model freezing and are not selection inputs.

## Out-of-era and same-player validation

Decade-block creation and defense results closely match player-grouped results; portability does
not improve when nearby observations are excluded. Candidate D has 2,543 scored adjacent-season
regime transitions with 14.30 mean absolute movement versus 14.58 across 10,211 same-regime
pairs. The aggregate transition comparison does not prove invariance because only scored rows can
enter it and some individual jumps are large.

## Interval calibration

Grouped out-of-fold residual intervals attain nominal empirical coverage. Mean 90% interval widths:

- expanded box/no Presence: 26.92 points;
- traditional box: 30.21 points;
- early with Presence: 33.37 points;
- early minimal: 42.30 points.

These intervals truthfully convey uncertainty but are too wide to authorize their midpoints as
universal point scores. The counterfactual output therefore labels 5,098 rows `INTERVAL_ONLY`,
16,576 `OBSERVED_RESEARCH_SCORE`, and 783 `UNAVAILABLE`.

## Effective influence and team context

No rejected bridge changes Candidate D. Its existing effective-influence audit remains: offense
63.47% and defense 36.53% covariance share. Primitive shares are APG 34.66%, PPG 22.63%, RPG
14.69%, STL 11.02%, BPG 11.02%, TS 6.18%, Presence -0.33%, and team context 0.13%.
Direct team weight is capped at 5.5%. Rejected proxy models may indirectly inherit team signal,
which is another reason they are not promoted.

## Early-era cases

Bill Russell, Wilt Chamberlain, Oscar Robertson, Bob Pettit, George Mikan, Elgin Baylor, and Jerry
West are reported from observed facts. Where PPG plus team/Presence anchors permit a calculation,
the audit shows a central diagnostic and 90% interval with `INTERVAL_ONLY`; where anchors are
absent, the result remains `UNAVAILABLE`. None of these identities enters model fitting.

## Downstream counterfactuals

Because no bridge passes, failed midpoint estimates are excluded from downstream scoring.
Candidate D therefore retains:

- Peak: 1,761 players, Spearman 0.9057 to V1, Top-100 overlap 0.59;
- Longevity: 2,950 players, Spearman 0.7832 to V1, Top-100 overlap 0.71.

The validated Peak 70/30 and Longevity 35/40/25 architectures remain unchanged. Neither is
promoted and no Overall counterfactual is warranted from a failed bridge.

## Rejected alternatives

- Filling APG from PPG or PPG+TS: insufficient creation identification.
- Filling Presence from actions/team: repeats the failure demonstrated in STEP-0015B.
- Team-only early defense: correlation is too low and the evidence is shared.
- One-factor latent defense: weak explained variance and unstable loadings.
- Renormalizing remaining channels: changes the construct rather than recovering it.
- Treating interval midpoints as official scores: hides 27–42 point 90% widths.

## Tests and reproducibility

The pipeline is offline and deterministic. Tests cover grouped folds, era-block transfer,
missing-not-zero behavior, interval ordering, predeclared gates, forbidden inputs, exact STEP-0015D
reconstruction, frozen outputs, status accounting, and report fingerprints. Full-suite results and
the final fingerprint are recorded after the deterministic second run.

- pytest: 217 passed, one opt-in network test skipped;
- Ruff: all source, pipeline, and test files passed;
- strict Mypy: all 29 typed package source files passed;
- artifact/data validation: committed report and reconstruction tests passed;
- deterministic second run: passed with fingerprint
  `731130b7fffd53ff084321b78175c7651f7c04387d9d574f5add205428bcbf63`;
- runtime: approximately 10.0 seconds offline;
- generated output: six ignored Parquet files, 22,457 season rows plus 10,449 downstream/case rows,
  approximately 2.59 MiB.

## Result and next step

The audit itself passes: all required reconstruction, bridge, masking, invariance, uncertainty,
transition, case-study, and downstream diagnostics are reproducible. The scientific verdict is
`NO_VALID_BRIDGE`.

The next step should be a source/evidence feasibility audit focused on additional historically
factual individual evidence and interval-native publication. Until then, Candidate D is not ready
for a promotion audit.
