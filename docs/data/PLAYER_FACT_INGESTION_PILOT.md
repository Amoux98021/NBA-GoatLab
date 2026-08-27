# NBA API player-fact ingestion pilot

## Scope and execution

STEP-0005 ran a bounded Bronze-to-Silver pilot for 1946-47, 1961-62, 1973-74, 1979-80, 1984-85, 1996-97, 2022-23, and 2025-26, for Regular Season and Playoffs. It used 16 bulk `PlayerGameLogs` artifacts and, for 1996-97, 2022-23, and 2025-26, six Base/Totals and six Advanced/Totals artifacts. All 28 requests resumed from the ignored STEP-0004 cache; this validation run made no network request and no per-player request.

## Materialized data

| Layer / entity | Rows |
|---|---:|
| Bronze PlayerGameLogs | 148,989 |
| Bronze Base/Totals | 2,198 |
| Bronze Advanced/Totals | 2,198 |
| Silver `player_game_stats` | 148,988 |
| Silver `player_season_stats` | 7,982 |
| Silver season TEAM rows | 4,153 |
| Silver season TOTAL rows | 3,829 |
| Silver `player_season_advanced` | 2,198 |

The writer created 38 deterministic Zstandard-compressed Parquet files totaling 3,204,124 bytes. Player-game and player-season output has 16 season/type partitions each; advanced output has six. Generated Bronze and Silver files remain Git-ignored. Each Bronze manifest entry records the complete request contract, `nba_api` 1.11.4, retrieval timestamp, source outcome, row count, cache key, source payload SHA-256, and source ID.

## Identity and team reconciliation

Official `PLAYER_ID` resolved all 2,138 distinct players to deterministic canonical IDs. Of these, 1,889 (88.35%) matched the legacy identity table and 249 received provenance-bearing `NBA_API_PROVISIONAL` identities; zero remained unresolved. Names were diagnostics only.

Official `TEAM_ID` resolved all 38 source team IDs into 53 observed name-version records. Thirty IDs matched legacy teams. Eight early clubs absent from the current legacy team table were preserved from official IDs, and 27 stale legacy-window conflicts were reported without rejecting official rows. Abbreviations were not used as keys.

Official `GAME_ID` resolved all 7,328 games: 5,653 matched the legacy game table and 1,675 were official-only, including post-snapshot seasons and legacy gaps.

## Aggregation and official reconciliation

Metrics were aggregated only when the season/type partition was empirically `RELIABLE` and the player's contributing rows were complete. `games_played` counts distinct game appearances. Percentages use summed makes divided by summed attempts and remain NULL for a zero or unavailable denominator. No NULL is converted to zero.

| Scope | Derived players | Official players | Compared values | Exact | Tolerance | Mismatch |
|---|---:|---:|---:|---:|---:|---:|
| 1996-97 Regular | 441 | 441 | 8,734 | 7,689 | 1,045 | 0 |
| 1996-97 Playoffs | 189 | 189 | 3,681 | 3,377 | 304 | 0 |
| 2022-23 Regular | 539 | 539 | 10,738 | 9,380 | 1,358 | 0 |
| 2022-23 Playoffs | 217 | 217 | 4,240 | 3,860 | 380 | 0 |
| 2025-26 Regular | 582 | 582 | 11,586 | 10,125 | 1,461 | 0 |
| 2025-26 Playoffs | 230 | 230 | 4,514 | 4,100 | 414 | 0 |
| **Total** | — | — | **43,493** | **38,531** | **4,962** | **0** |

Tolerance matches are limited to documented floating-point/rounding behavior, principally official percentage rounding and minutes precision. Player sets matched exactly in every reconciled partition.

## Empirical coverage

The 304 metric/partition observations classify as 190 `RELIABLE`, 24 `PARTIAL`, 26 `SPARSE`, 54 `UNAVAILABLE`, and 10 `UNKNOWN`. This demonstrates why response success is not metric reliability. Examples include 1946-47 Regular Season FGA at 7.88% non-null and AST at 2.01%; 1973-74 Regular Season OREB/DREB at approximately 31%; and several 1984-85 Regular Season metrics near 98.5%, conservatively still `PARTIAL` under the 99% V1 threshold. From 1996-97 forward, all 18 observable traditional metrics in this contract were `RELIABLE`; `started` remained `UNAVAILABLE` because the endpoint does not expose it.

## Quality findings

Silver contained no duplicate player-game keys, duplicate total rows, orphans, invalid dates/types, negative counts, impossible shooting relationships, reliable-coverage rebound inconsistencies, provenance gaps, or detected NULL-to-zero conversions.

One 1946-47 Regular Season source row was explicitly quarantined before Silver: game `0024600055`, player `76137`, team `1610610031` reported FTM 1 with FTA 0, while FGA was NULL. The unmodified row remains in Bronze. No automatic repair was attempted.

## Result

**PASS.** The pilot satisfies the fixed criteria for reproducible bulk acquisition, deterministic identity/team resolution, duplicate-safe Silver facts, qualified aggregation, official total reconciliation, NULL preservation, empirical metric qualification, and resumability. PASS applies to controlled expansion of this ingestion design, not to universal historical completeness.

Machine-readable evidence:

- `player-fact-pilot-summary.json`
- `metric-coverage-pilot.json`
- `player-identity-reconciliation.json`
- `team-crosswalk-report.json`
