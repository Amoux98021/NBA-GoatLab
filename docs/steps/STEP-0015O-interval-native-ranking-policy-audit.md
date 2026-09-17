# STEP-0015O — Interval-Native Ranking & Publication Policy Audit

Date: 2026-09-17

Status: `PASS`

Publication verdict: `VALID_PROBABILISTIC_RANKING_ONLY`

Overall readiness: `OVERALL_V2_STILL_NOT_READY`

Research policy: `goatlab-v1-ranking-policy-v2-uncertainty-research`

## Objective

Determine whether the frozen STEP-0015N joint Overall distributions support a scientifically
honest cross-era ranking without requiring every player to have an official or provisional exact
Overall point. No dimension, weight, calibration gate, joint-draw architecture, V1 output, or
active-career rule was changed.

## Reconstruction

STEP-0015N fingerprint
`b6248062490ca6b2d63e616af5ac759a59abc9ea3e9dc15dd4f2bd264741bb95` and the frozen player/rank
Parquet hashes were verified. All 5,103 player rows, 1,197 reference careers, six joint evidence
patterns, 2,500 Overall draws, centers, statuses, and Peak/Longevity path values reconstructed with
maximum difference 0.0 and zero status mismatches.

## Rankable population

`DISTRIBUTION_RANKABLE` means a calibrated Overall distribution exists. It includes official,
provisional, and interval-only Overall outputs. `NOT_RANKABLE` means a required usable distribution
does not exist.

| Scope | Distribution-rankable | Not rankable | Total |
|---|---:|---:|---:|
| All canonical players | 1,882 | 3,221 | 5,103 |
| BROAD_HIGH_RECALL | 1,882 | 774 | 2,656 |
| Archived V1 Top 100 | 100 | 0 | 100 |

The rankable set contains 312 official, 284 provisional, and 1,286 interval-only Overall
distributions. Interval-only status is not a quality penalty and is not an exclusion rule.

## Candidate deterministic summaries

Four predeclared summaries were evaluated: central Overall sort, median rank, expected rank, and
pairwise expected wins. Expected rank and expected pairwise wins are algebraically equivalent for a
complete draw population. None passed every frozen exact-ranking gate.

Selected diagnostics by evidence pattern are shown below for central Overall sort; no summary was
selected for publication.

| Pattern | Spearman | Kendall | Rank MAE | Top 10 | Top 25 | Top 50 | Top 100 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full reference | 0.9995 | 0.9816 | 7.87 | 90% | 92% | 96% | 99% |
| Partial Presence | 0.9950 | 0.9444 | 22.71 | 90% | 88% | 94% | 94% |
| Mixed | 0.9914 | 0.9216 | 32.82 | 90% | 84% | 90% | 91% |
| Historical transition | 0.9876 | 0.9056 | 39.68 | 80% | 80% | 88% | 86% |
| No Presence | 0.9831 | 0.8879 | 48.05 | 70% | 76% | 88% | 86% |
| Traditional only | 0.9711 | 0.8516 | 62.54 | 60% | 72% | 84% | 78% |

The gate requires Spearman at least 0.98 and at least 90% overlap at all four Top-N cutoffs. No
candidate meets that rule across evidence patterns. Median rank is retained only as a convenient
diagnostic center.

## Probabilistic calibration

Each draw ranks every distribution-rankable player jointly. Rank bands use player-grouped,
five-fold, signed conformalized-quantile calibration on percentile rank. Signed calibration may
contract conservative raw bands or expand under-covering bands; it changes neither scores nor rank
centers. Every deployed band contains its median rank and 50/80/90/95 bands are nested.

| Pattern | 50% coverage / width | 80% | 90% | 95% |
|---|---:|---:|---:|---:|
| Full reference | 52.88% / 17.2 | 82.12% / 35.8 | 92.23% / 48.1 | 96.16% / 61.0 |
| Partial Presence | 50.46% / 38.6 | 81.54% / 72.3 | 91.14% / 92.1 | 95.49% / 110.2 |
| Mixed | 52.05% / 53.1 | 80.28% / 105.1 | 90.39% / 136.1 | 95.32% / 161.0 |
| Historical transition | 50.54% / 65.6 | 80.12% / 127.6 | 90.23% / 159.9 | 95.32% / 193.0 |
| No Presence | 50.38% / 80.7 | 80.62% / 148.6 | 90.81% / 190.5 | 95.49% / 227.1 |
| Traditional only | 50.21% / 100.3 | 80.53% / 190.2 | 90.14% / 243.7 | 95.57% / 286.4 |

Top-N probability Brier ranges across all six patterns were 0.0012–0.0038 for Top 10,
0.0017–0.0074 for Top 25, 0.0023–0.0100 for Top 50, and 0.0021–0.0233 for Top 100. Weighted
expected calibration errors remained 0.0015–0.0085. Pairwise directional Brier ranged from 0.0080
to 0.0503 and expected calibration error from 0.0026 to 0.0085.

These results support calibrated probability statements and broad placement bands even where a
single exact ordinal summary is not rank-grade.

## Pairwise and partial-order semantics

The validated research thresholds are:

- `STRONG_ORDER`: probability at least 90%;
- `LEAN_ORDER`: probability from 65% to below 90%;
- `INDETERMINATE_ORDER`: probability from 35% through 65%;
- symmetric reverse labels below 35%.

On deterministic 20,000-pair samples per form, the 90–95% prediction bin produced empirical win
rates of 92.3%–96.6%. The above-95% bin produced 99.6%–100.0%. A bounded 200-player graph audit
found no strong or lean cycles in any form; this is evidence about the audited graph, not a theorem
that cycles cannot occur.

Close exact ranks are rarely meaningful. Among adjacent central ranks separated by less than 0.1
Overall point, mean pairwise support for the displayed order was 51.22%, and 99.18% of pairs were
indeterminate. Even at less than 2.0 points, 96.86% were indeterminate.

## Fairness and evidence strength

Controlled masking primarily widens rank uncertainty: the mean 90% band grows from 48.1 ranks in
the full form to 92.1 under partial Presence, 136.1 under mixed evidence, and 243.7 under traditional
evidence. It does not apply a confidence penalty.

Mixed-form signed subgroup bias remained within 0.75 percentile rank for every broad role. The
traditional form retained material role interaction: bigs and forwards moved upward by about 1.79
and 1.41 percentile ranks while guards and wings moved downward by about 1.79 and 1.18. This weak
form is therefore suitable for calibrated ranges/probabilities, not an exact headline rank. Career
midpoint-decade bias was smaller than one percentile rank in every tested form.

## Publication policy result

The audit accepts only probabilistic research publication semantics:

- show median rank as a labeled diagnostic summary, never exact truth;
- foreground 80% and 90% rank bands and Top-10/25/50/100 probabilities;
- show `Official`, `Provisional`, or `Interval-native` evidence status without changing quality;
- show a diagnostic Overall center only when clearly paired with its range and non-official label;
- classify unavailable players as unranked/insufficient evidence;
- preserve `TO_DATE_NO_PROJECTION` for active careers;
- state that all rank distributions are conditional on the frozen measurement architecture because
  shared cross-player calibration-model uncertainty is not modeled.

No exact Top-100 membership rule was frozen. A probabilistic boundary may be described as robust
(at least 90%), likely (65%–90%), bubble (35%–65%), likely outside (10%–35%), or robust outside
(below 10%), but these labels do not form an official list.

## Jordan / LeBron diagnostic

This was inspected only after policy logic was frozen. LeBron has median rank 1, a 90% band of
1–2, Top-1 probability 86.32%, and Top-5 probability 99.68%. Jordan has median rank 2, a 90% band
of 1–7, Top-1 probability 8.96%, and Top-5 probability 91.88%. The simulated probability Jordan
exceeds LeBron is 10.20%. These are conditional research comparisons, not a policy target.

## Top 100 and Overall decision

`VALID_PROBABILISTIC_RANKING_ONLY` does not satisfy the product requirement for a permanent exact
Top 100. Therefore:

- no GOATLab V2 Top 100 was generated;
- no entrant, exit, overlap, or movement table was presented as a successor ranking;
- `goatlab-v1-overall-v2-tiered` remains unpromoted;
- `goatlab-v1-overall-v1` and its archived Top 100 remain unchanged;
- Overall readiness is `OVERALL_V2_STILL_NOT_READY`.

## Outputs

Committed reports:

- `docs/data/interval-native-ranking-policy-audit.md`
- `docs/data/distribution-rankable-population.json`
- `docs/data/rank-summary-validation.json`
- `docs/data/rank-band-calibration.json`
- `docs/data/topn-probability-calibration.json`
- `docs/data/pairwise-rank-calibration.json`
- `docs/data/ranking-cycle-audit.json`
- `docs/data/interval-ranking-fairness.json`
- `docs/data/top100-policy-comparison.json`
- `docs/data/interval-ranking-diagnostics.json`
- `docs/data/ranking-policy-status.json`
- `docs/data/interval-native-ranking-policy-summary.json`

Generated Gold outputs remain ignored under
`data/gold/interval_native_ranking_policy_audit/`. The conditional Top-100 artifact is absent by
construction.

## Tests and reproducibility

The implementation adds deterministic rank, calibration, interval-nesting, pairwise consistency,
distribution-rankability, V1-preservation, and conditional-Top-100 tests. The complete repository
suite is run after the final deterministic fingerprint rebuild.

Output fingerprint: `544843af8d316c6b5d54786b29562451ce01e3f6b5c35a0fe936e27fa2290a15`.

## Decision and next work

STEP status is `PASS`: the requested audit completed reproducibly.

STEP-0015 should not close while the permanent exact Top-100 requirement remains binding. The
remaining blocker is product/governance, not another tunable basketball formula: either explicitly
adopt a probabilistic-first leaderboard as the product contract, or validate an exact summary that
passes all frozen cross-era gates. No automatic STEP-0015P is opened here.
