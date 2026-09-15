# Historical Data Recovery Audit

Methodology: `goatlab-historical-data-recovery-audit-v1`

Research facts: `goatlab-historical-player-season-facts-v2-research`

Date: 2026-09-14

## Finding

The prior sparse-history diagnosis substantially reflected source and aggregation coverage, not
only statistics that the league never recorded. STEP-0015F recovered exact official season facts
without predicting any player statistic. The result is **MATERIAL_RECOVERY** and supports
`RERUN_MEASUREMENT_WITH_RECOVERED_FACTS`.

Published V1 Defense, Peak, Longevity, and Overall outputs remain unchanged. The new Silver table
is research-versioned and the downstream Candidate D, Peak, and Longevity results remain
counterfactual.

## Sources and scope

The deterministic acquisition scope is all 2,234 players with at least one qualified pre-1996
Candidate D season. The official NBA Stats `PlayerCareerStats` endpoint returned
`SeasonTotalsRegularSeason` rows for 2,231 player IDs. Three IDs returned a stable empty JSON
contract and remain `SOURCE_UNAVAILABLE`: Bobby Watson (`79635`), Terrence Rencher (`720`), and
Corey Williams (`200603`).

The source order is:

1. official `PlayerCareerStats` season totals for the pre-1996 research artifact;
2. frozen `GOATLAB-HIST-V1` facts where no eligible supplemental value exists, and universally
   from 1996 onward;
3. already cached official `LeagueLeaders` per-game values as a source-direct fallback only.

LeagueLeaders rates are never multiplied into invented totals. Conflicting values are never
averaged. Official player IDs are the only primary identity key; the 2,234-row crosswalk has zero
unresolved identities.

## Historical availability

The recovered season-level map establishes continuous season presence after these official
recording boundaries:

| Statistics | First season |
|---|---:|
| GP, PTS, FGM/FGA, FG%, FTM/FTA, FT%, AST, PF | 1946-47 |
| total rebounds | 1950-51 |
| minutes | 1951-52 |
| OREB, DREB, STL, BLK | 1973-74 |
| turnovers | 1977-78 |

This does not imply every individual row is populated. It means the statistic is historically
applicable and the post-recovery source has at least one observation in every season from that
boundary onward. Missing values before a recording boundary are forced to NULL with
`HISTORICALLY_NOT_RECORDED`, even when an endpoint exposes a placeholder.

## Existing-corpus audit and reconciliation

The frozen PlayerGameLogs source already contains many complete player-season groups. When a group
has exact GP and no missing observations, 98,647 field aggregates/GP counts match the official
career record exactly, 3,981 differ by at most one, and 7,666 materially disagree. Another 9,532 exact
player-game aggregates were omitted from the existing season table by the old partition-wide
coverage gate. This is a real aggregation-coverage defect, not evidence that the statistic was
unrecorded.

Across existing pre-1996 Silver totals and official PlayerCareerStats, 109,572 comparisons are
exact, 5,532 are within one, and 9,299 differ materially. Minutes are the clearest incomplete-bulk
source symptom: their mean absolute difference is 197.90 and maximum difference is 3,055. The
versioned research table selects the dedicated official career total before 1996 and retains every
disagreement in `historical-source-reconciliation.json`.

## Factual recovery

The exact STEP-0015E baseline is reproduced before recovery.

| Missing evidence among 5,881 original early-limited rows | Recovered | Remaining missing |
|---|---:|---:|
| APG | 5,861 | 2 |
| adequate shooting totals for standard TS | 5,319 | 2 |
| rebound/action evidence | 4,675 | 567 |
| `EARLY_LIMITED` regime | 5,314 moved out | 567 remain |

The 567 remaining early-limited rows are concentrated before total rebounds began in 1950-51,
plus the documented source gaps. STL, BLK, OREB, DREB, and TOV are never backfilled before their
recording introductions. Defensive Presence remains an observed research channel and is not
predicted here.

## Shooting efficiency

GOATLab continues to label TS as the standard analytical estimate
`PTS / (2 × (FGA + 0.44 × FTA))`, derived from observed factual totals. Against 12,437 official
advanced-TS overlaps, mean absolute difference is 0.000250 and maximum difference is 0.000500;
all comparisons are within source rounding. The 0.44 factor is not an exact possession
reconstruction, and historical free-throw rule changes remain a comparability limitation.

## Evidence regimes and downstream coverage

| Regime | Before rows | After rows | After players |
|---|---:|---:|---:|
| `EARLY_LIMITED` | 5,881 | 567 | 350 |
| `TRADITIONAL_BOX` | 55 | 2,717 | 724 |
| `EXPANDED_BOX_NO_PRESENCE` | 2,153 | 4,486 | 1,520 |
| `FULL_PORTABLE` | 14,368 | 14,687 | 3,092 |

Without changing its formula, Candidate D rises from 16,576 to 21,107 scored player-seasons
(73.81% to 93.99%) and from 2,950 to 3,893 players. Confidence after recovery is 7,457 strong,
10,760 moderate, and 2,890 limited seasons.

The fixed 70/30 Peak counterfactual rises from 1,761 to 2,326 players. The fixed 35/40/25
Longevity-input counterfactual rises from 2,950 to 3,893. Neither is promoted.

## Masking recheck

Recovery supplies observations; it does not make artificial information-removal masks valid.
Post-recovery MAE is 7.25 for expanded-box/no-Presence, 7.96 for traditional-box, 8.41 for
early-with-Presence, and 11.34 for early-minimal masks. These are small changes from 7.27, 8.00,
8.41, and 11.35 and still fail the predeclared point-bridge gates. Missing-Presence and genuinely
unrecorded defensive channels therefore remain measurement limitations.

## Early-era diagnostics

Bill Russell, Wilt Chamberlain, Bob Pettit, Elgin Baylor, Oscar Robertson, and Jerry West move from
early-limited rows into factual traditional/expanded regimes for relevant seasons. George Mikan's
1948-49 and 1949-50 seasons gain observed shooting and assist evidence but remain early-limited
because total rebounds were not yet recorded; his later seasons gain traditional-box evidence.
These names were selected after methodology and never influenced source scope or precedence.

## Remaining limitations

- Total rebounds do not exist at ranking-grade resolution before 1950-51.
- OREB, DREB, STL, and BLK remain historically unrecorded before 1973-74; TOV before 1977-78.
- Defensive Presence is not universally observed and is not recoverable from season totals.
- Three official player IDs lack a usable PlayerCareerStats result set.
- The standard TS estimate retains historical free-throw-possession assumptions.
- Corrected official career totals and game-log aggregates disagree in a minority of rows; the
  research precedence is explicit, but promoting a new frozen corpus requires a separate release.

## Reproducibility

The 37 MiB Bronze cache is Git-ignored. Generated output is one 22,457-row Silver Parquet plus four
Gold diagnostics (about 3.6 MiB total). The final cache-only run issues zero requests and is checked
against output fingerprint
`0eb5514e6f5055160e41dd2260be279418133d228eaec50772e9063e89b6dc25` in
`historical-data-recovery-summary.json`.
