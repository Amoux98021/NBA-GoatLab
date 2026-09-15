# PlayerSeasonValue Measurement Linking Audit

Methodology: `goatlab-v1-player-season-value-measurement-linking-audit-v1`

Research output: `goatlab-v1-player-season-value-v2-linked-research`

Result: **PASS + LIMITED_TIERED_ARCHITECTURE**

## Question and scope

This audit asks whether factual evidence regimes can operate as different measurement forms of
the same frozen Candidate D construct. It does not predict assists, rebounds, steals, blocks,
Presence, TS, or any other missing statistic. It does not change Candidate D, any V1 dimension, or
Overall V1. `FULL_PORTABLE` is the richest portable reference instrument, not basketball truth.

All 22,457 recovered Silver rows and all 21,107 Candidate D scores reproduce STEP-0015G exactly.
Raw and percentile maximum difference is `0.0`.

## Measurement forms

The 14,687 factual `FULL_PORTABLE` seasons form paired anchors. Each is scored again after
artificially removing only the channels named by the weaker form.

| Form | Factual evidence retained |
|---|---|
| `FULL_PORTABLE` | Candidate D's full portable factual evidence; reference form |
| `EXPANDED_NO_PRESENCE` | expanded box/action evidence, no observed Presence |
| `EXPANDED_PROXY_ACTION_WITH_PRESENCE` | expanded box proxy actions and observed Presence, without role-adjusted action metadata |
| `TRADITIONAL_BOX` | PPG, TS, APG, rebound proxy; no STL/BLK or Presence |
| `TRADITIONAL_WITH_PRESENCE` | traditional box plus observed Presence |
| `EARLY_OFFENSE_WITH_PRESENCE` | observed offense plus Presence; no invented rebound channel |
| `OFFENSE_ONLY_EARLY` | observed scoring/efficiency/creation; defense absent |
| `NO_TEAM_CONTEXT` | bounded team term omitted without renormalizing other channels |

## Linkers and cross-fitting

The audit compares no linking, linear location/scale linking, smoothed equipercentile linking,
isotonic linking, and broad-role isotonic linking. The primary evaluation uses five deterministic
player-grouped folds. Random folds are secondary. Leave-decade-out and directional earlier/later
transfer test transport. Role conditioning is accepted only where it materially improves held-out
calibration; it is a measurement modifier, not a role quota or equal-ceiling rule.

Selected methods and grouped-player results are:

| Form | Selected | Raw MAE | Linked MAE | Linked Spearman | >10 points |
|---|---|---:|---:|---:|---:|
| expanded, no Presence | quantile | 8.98 | 6.12 | 0.9640 | 20.58% |
| expanded proxy actions + Presence | role isotonic | 10.33 | 1.59 | 0.9972 | 0.20% |
| traditional box | role isotonic | 10.43 | 7.59 | 0.9418 | 28.67% |
| traditional + Presence | role isotonic | 10.46 | 3.53 | 0.9868 | 4.25% |
| early offense + Presence | linear | 14.83 | 13.37 | 0.8081 | 54.93% |
| offense only | role isotonic | 9.95 | 8.54 | 0.9274 | 34.41% |
| no Team Context | quantile | 9.49 | 2.07 | 0.9960 | 0.00% |

Linking removes large location/scale differences for several forms but cannot recover ordering
information that is absent. Expanded/no-Presence, traditional-box, and early forms therefore fail
the predeclared point gates despite near-zero aggregate signed bias.

## Uncertainty

The primary intervals are split-conformal: for each player-grouped test fold, a separate grouped
fold calibrates absolute residuals and the remaining folds fit the linker. Empirical OOF residual
intervals are retained as a secondary method; quantile-regression intervals were not selected
because a one-dimensional monotone score form did not justify extra unstable parameters.

| Form | 80% actual / width | 90% actual / width | 95% actual / width |
|---|---:|---:|---:|
| expanded, no Presence | 80.04% / 19.26 | 90.01% / 23.76 | 94.90% / 26.92 |
| expanded proxy actions + Presence | 80.27% / 5.03 | 90.20% / 6.72 | 94.97% / 8.29 |
| traditional box | 80.28% / 23.65 | 90.03% / 30.23 | 94.85% / 35.37 |
| traditional + Presence | 80.24% / 11.43 | 90.07% / 15.17 | 95.04% / 18.48 |
| early offense + Presence | 80.05% / 41.98 | 90.04% / 51.84 | 95.03% / 59.09 |
| offense only | 80.05% / 26.39 | 90.05% / 33.29 | 95.11% / 38.84 |
| no Team Context | 80.16% / 6.62 | 89.83% / 8.26 | 95.08% / 9.69 |

Widths vary by form, role, and score band. `FULL_PORTABLE` also receives a reference-instrument
sensitivity interval based on the held-out no-Team-Context perturbation. That interval is not
validated against unknowable basketball truth and must not be described as such.

## Status rules and actual history

`PROVISIONAL_POINT` requires MAE <= 5, Spearman >= 0.95, absolute overall bias <= 2, every
major-role bias <= 3, no more than 15% errors above ten points, and calibrated 90% coverage from
87% through 93%. Failing point gates with calibrated intervals yields `INTERVAL_ONLY`.

Applied to all 22,457 factual seasons:

| Status | Rows |
|---|---:|
| `OFFICIAL_POINT` | 14,687 |
| `PROVISIONAL_POINT` | 3,831 |
| `INTERVAL_ONLY` | 3,937 |
| `UNAVAILABLE` | 2 |

The provisional rows comprise 1,297 expanded-proxy-action seasons with Presence, 1,751
traditional seasons with Presence, and 783 rows missing only bounded Team Context. The interval
rows include 2,693 expanded seasons without Presence, 679 traditional seasons without Presence,
438 early offense-plus-Presence seasons, and 127 offense-only seasons.

Pre-1950 factual offense supports 565 interval-only measurements; two rows remain unavailable.
No rebound is invented. The 1970s issue is not one problem: omitting only Team Context is
well-calibrated, but traditional defensive forms without STL/BLK or Presence remain interval-only.

## Role, archetype, transport, and ordering

Selected linkers keep every major-role signed bias within three points, but role MAE remains high
when defensive channels are absent. Expanded/no-Presence biases bigs by +1.11 and guards by -1.54;
traditional-box role MAEs range from 6.81 for guards to 8.69 for unknown-role rows. Role-aware
linking materially improves traditional forms but does not make them point-grade. Archetype
residuals remain largest for profiles whose distinguishing evidence is precisely the removed
channel.

Grouped, random, and leave-decade-out results are close in aggregate. Directional era-transfer
results are recorded separately; this guards against treating random-fold calibration as proof of
historical invariance.

Pairwise ordering becomes reliable only as full-form separation grows. For expanded/no-Presence,
linked accuracy is 60.6%, 70.1%, 82.5%, 91.2%, and 96.7% at approximately 2-, 5-, 10-, 15-, and
20-point separations. A 90% robust-order declaration is uncommon at small separations but exceeds
99% accuracy for declared expanded-form orders at ten points or more. Traditional-box linking
improves raw ordering but remains weaker.

## Downstream uncertainty diagnostics

Peak retains the frozen 70% contiguous-three-year / 30% apex architecture. A deterministic
300-draw research diagnostic uses a shared player shock plus season-specific variation to avoid
treating career-season errors as independent. It produces 2,456 player diagnostics and reports
the best-supported and alternative plausible windows. This is not a promoted Peak.

Longevity reports season-level probabilities above P80/P90 and an approximate expected longest
P80 run for 4,186 players. It does not silently replace the frozen 35/40/25 architecture. Hard
thresholds and run length need a dedicated uncertainty audit before any promotion.

## Verdict

The result is `LIMITED_TIERED_ARCHITECTURE`. Different forms can share a reference scale only in
tiers. Presence-bearing and no-Team-Context forms pass point gates; no-Presence and sparse forms
support calibrated ranges but not ranking-grade points. Candidate D is still research-only.

The recommended next step is `READY_FOR_PEAK_LONGEVITY_UNCERTAINTY_AUDIT`. It should validate
joint career-season dependence, window-selection uncertainty, and probabilistic P80/P90/run
semantics before reconsidering PlayerSeasonValue or downstream promotion.

The full suite passes with 252 tests and one opt-in network test skipped. Ruff, strict Mypy across
32 package files, JSON/Parquet artifact checks, and Git whitespace validation pass. A second
offline run issues zero network requests and reproduces fingerprint
`4b1ff850f9d0df43ffd271af16277d94abd3f14cba1a9a8aa679cb3983710f54`; runtime is approximately
31 seconds.

## Limitations

- `FULL_PORTABLE` is a reference form, not ground truth.
- Presence is observational and not causal RAPM.
- Intervals quantify form-to-form measurement error, not every source of basketball uncertainty.
- Role metadata are incomplete and `UNKNOWN` is substantial historically.
- Artificial masking cannot prove that player archetypes have identical historical distributions.
- Conformal calibration is marginal; subgroup coverage is diagnostic rather than guaranteed.
- Peak draws use an explicit approximate dependence model; Longevity run expectation is preliminary.
