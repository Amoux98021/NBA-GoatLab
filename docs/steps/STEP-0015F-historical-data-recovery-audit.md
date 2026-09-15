# STEP-0015F — Historical Data Recovery & Source Reconciliation Audit

Date: 2026-09-14

Result: **PASS**

Recovery verdict: **MATERIAL_RECOVERY**

Recommendation: **RERUN_MEASUREMENT_WITH_RECOVERED_FACTS**

## Objective

Separate evidence that was never recorded from evidence omitted by GOATLab's selected source or
aggregation, recover observed Regular Season facts, and rerun the frozen research method without
statistical imputation.

## Constitutional and scope controls

- `GOATLAB-HIST-V1` and all published V1 dimension/Overall outputs remain immutable.
- New factual records follow Bronze → versioned research Silver → research Gold.
- Missing and historically unrecorded observations remain NULL, never zero.
- No APG, rebound, steal, block, TS, or Presence value is predicted.
- Awards, postseason outcomes, championships, reputation, and player names do not enter recovery.
- Candidate D, Peak 70/30, and Longevity 35/40/25 formulas are unchanged.

## Inputs and fingerprints

- Corpus: `GOATLAB-HIST-V1`, fingerprint
  `283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c`.
- STEP-0015E fingerprint:
  `731130b7fffd53ff084321b78175c7651f7c04387d9d574f5add205428bcbf63`.
- Constitution fingerprint:
  `f7a67adb161de086e9d47b0eaa3b9606cfb42cc70f15341c2a225586403c6ad5`.

The audit exactly reproduces the expected 5,881 early-limited rows, including 5,863 APG gaps,
5,321 TS gaps, 5,242 action gaps, 2,074 Presence gaps, and 4,311 PPG-plus-team-only rows.

## Source audit and decision

The frozen bulk PlayerGameLogs records are season-complete at row level but early metric fields are
not always complete. The official NBA Stats PlayerCareerStats endpoint exposes exact
`SeasonTotalsRegularSeason` rows keyed by official player ID. ADR-0033 adopts those totals as a
supplemental pre-1996 research source.

The deterministic scope includes 2,234 players with a qualified pre-1996 Candidate D season:
2,231 return rows and three return a terminal empty contract. Acquisition used 1,728 network
requests in the resumed complete pass, reused 506 cached responses, and recorded one retry. Every
scope has a terminal state.

The already cached STEP-0011 LeagueLeaders rates serve only as a source-direct fallback. Rounded
rates are never expanded into totals. No third-party player-stat dataset is ingested.

## Historical availability

Official recording/applicability boundaries are validated as follows:

- 1946-47: GP, PTS, FGM/FGA, FG%, FTM/FTA, FT%, AST, PF;
- 1950-51: total rebounds;
- 1951-52: minutes;
- 1973-74: OREB, DREB, STL, BLK;
- 1977-78: turnovers.

The machine-readable map covers each of the 80 seasons and records current observations, recovered
observations, remaining gaps, applicability, derivation semantics, and provenance.

## Existing-corpus findings

Complete player-game groups produce 98,647 exact field aggregates/GP counts, 3,981 tolerance
matches, and 7,666 material source conflicts. The prior partition-wide gate omitted 9,532 exact
aggregates from the player-season table. This is a proven pipeline/aggregation-coverage problem.

Across the existing pre-1996 Silver table and PlayerCareerStats, 109,572 comparisons are exact,
5,532 differ by at most one, and 9,299 materially conflict. Dedicated official totals are selected
in the new research artifact; prior values remain frozen and every discrepancy is reported.

## Recovery results

| Item | Before missing | Recovered | Remaining |
|---|---:|---:|---:|
| APG | 5,863 | 5,861 | 2 |
| TS factual inputs | 5,321 | 5,319 | 2 |
| rebound/action evidence | 5,242 | 4,675 | 567 |
| early-limited rows | 5,881 | 5,314 reclassified | 567 |

The standard totals-derived TS estimate reconciles to all 12,437 official advanced overlaps within
0.0005; mean absolute difference is 0.000250. Historical free-throw possession assumptions remain
explicitly limited.

## Evidence-regime rebuild

| Regime | Before | After |
|---|---:|---:|
| `EARLY_LIMITED` | 5,881 | 567 |
| `TRADITIONAL_BOX` | 55 | 2,717 |
| `EXPANDED_BOX_NO_PRESENCE` | 2,153 | 4,486 |
| `FULL_PORTABLE` | 14,368 | 14,687 |

Candidate D increases from 16,576/22,457 scored rows (2,950 players) to 21,107/22,457
(3,893 players). This is the unchanged formula operating on better factual inputs.

## Masking and remaining measurement limits

The post-recovery expanded/traditional/early-with-Presence/early-minimal artificial-mask MAEs are
7.25/7.96/8.41/11.34 points. These are only slight improvements over
7.27/8.00/8.41/11.35 and still fail the existing bridge gates. Factual recovery materially solves
creation and shooting collection gaps; it does not solve missing Presence or pre-introduction
defensive evidence.

## Downstream coverage impact

- Fixed-architecture Peak research coverage: 1,761 → 2,326 players (+565).
- Fixed-architecture Longevity research coverage: 2,950 → 3,893 players (+943).
- Peak Spearman to V1 on the new overlap: 0.8805; Top-100 overlap: 0.53.
- Longevity Spearman to V1 on the new overlap: 0.7750; Top-100 overlap: 0.74.

Neither counterfactual is promoted. The magnitude of the input change is precisely why the
measurement audit must be rerun before any methodology decision.

## Case studies

Russell, Chamberlain, Pettit, Baylor, Robertson, and West gain observed assists, shooting, and
rebound evidence across their historical seasons. Mikan gains shooting and assists in 1948-49 and
1949-50, but those seasons remain early-limited because total rebounds were not yet recorded.
Later Mikan seasons become traditional-box eligible. No case name affects acquisition or logic.

## Artifacts

Committed reports include the availability map, current-corpus field audit, external-source
inventory, source reconciliation, identity crosswalk, evidence-regime comparison, recovery impact,
case studies, acquisition summary, verdict, and this methodology narrative. Generated Bronze,
Silver, and Gold data remain ignored.

## Validation and result

Tests cover exact historical aggregation, identity, trade TOTAL selection, TS derivation,
introduction guards, source precedence, missingness semantics, frozen-output preservation, and
deterministic fingerprints. Final verification produced 228 passing tests with one opt-in network
test skipped, repository-wide Ruff checks passing, strict Mypy passing across 30 package files,
and a second zero-network build matching fingerprint
`0eb5514e6f5055160e41dd2260be279418133d228eaec50772e9063e89b6dc25`.

STEP-0015F passes because all source scopes are terminal, provenance and conflicts are explicit,
the recovery is factual and reproducible, and no frozen output is changed. The recovery verdict is
`MATERIAL_RECOVERY`; the next step should rerun STEP-0015D/E measurement and invariance tests on
these recovered facts before considering any promotion.
