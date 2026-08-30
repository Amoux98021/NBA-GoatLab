# GOATLAB-HIST-V1 historical player-fact corpus

## Scope and status

`GOATLAB-HIST-V1` is the frozen V1 research corpus produced by STEP-0006. It covers all 80 seasons from 1946-47 through 2025-26 for Regular Season and Playoffs. It excludes all later seasons and is separate from any future live/current-season refresh.

**Decision: PASS.** All 280 intended bulk acquisition scopes were accounted for, every source request returned rows, every generated Silver partition reproduced from cache, and no unexplained systematic reconciliation mismatch remained.

## Source matrix

| Endpoint | Seasons | Types | Scopes | Source rows |
|---|---|---|---:|---:|
| `PlayerGameLogs` | 1946-47–2025-26 | Regular, Playoffs | 160 | 1,481,850 |
| `LeagueDashPlayerStats` Base/Totals | 1996-97–2025-26 | Regular, Playoffs | 60 | 20,668 |
| `LeagueDashPlayerStats` Advanced/Totals | 1996-97–2025-26 | Regular, Playoffs | 60 | 20,668 |

All calls were season/type bulk requests; no per-player requests were made. The controlled acquisition made 234 network requests and reused 46 valid cache entries. One retry recovered successfully. There were no empty, unsupported, or failed final scopes.

## Frozen outputs

| Silver entity | Rows | Partitions |
|---|---:|---:|
| `player_game_stats` | 1,481,725 | 160 |
| `player_season_stats` TEAM | 40,553 | included below |
| `player_season_stats` TOTAL | 37,472 | included below |
| `player_season_stats` combined | 78,025 | 160 |
| `player_season_advanced` | 20,668 | 60 |
| **Total** | **1,580,418** | **380** |

The ignored Silver tree occupies 31,928,415 bytes. The selected ignored Bronze artifacts occupy 436,742,963 bytes across 560 payload/metadata files. Every Silver partition has a row count, byte size, and SHA-256 hash in `historical-corpus-v1-manifest.json`. The aggregate fingerprint is `283c528f487024e5292eaac06018364ee863ba623244e5dca4a0f958f100c70c`.

## Identity, teams, and games

- 5,103 official player IDs were observed: 4,792 matched legacy identities and 311 are official-source-only provisional identities. None is unresolved. Provisional means biography enrichment remains incomplete; it does not mean the numeric business key is ambiguous.
- 45 official team IDs produced 74 observed historical name versions. Thirty official IDs matched the legacy source; 15 represent official-only historical clubs. Twenty-seven stale legacy-window conflicts were retained as evidence and did not invalidate official rows. None is unresolved.
- 73,135 distinct official game IDs were represented. Of these, 64,034 match the legacy game table and 9,101 are official-only, primarily outside the legacy snapshot's cutoff.

Names and abbreviations remain diagnostic. Official numeric NBA IDs are the source business keys.

## Reconciliation

All 60 Base/Totals partitions from 1996-97 through 2025-26 passed. The comparison evaluated 408,047 aligned values: 362,422 exact matches and 45,625 tolerance matches, with zero mismatches and zero players present on only one side. Tolerances account for provider rounding of percentages and retained minute precision. The fixed systematic-mismatch gate blocks a field with at least a 1% mismatch rate or mismatches in at least three partitions; no field triggered it.

## Coverage qualification

The full matrix contains 3,040 season × type × metric records:

| Classification | Records |
|---|---:|
| RELIABLE | 2,072 |
| PARTIAL | 113 |
| SPARSE | 167 |
| UNAVAILABLE | 588 |
| UNKNOWN | 100 |

These labels use the unchanged ADR-0007 thresholds. Column presence and endpoint success are never interpreted as metric reliability. Pre-introduction placeholders are forced to canonical NULL and reported as source anomalies.

## Quality findings

Accepted Silver contains zero duplicate player-game keys, duplicate TOTAL rows, invalid shooting relationships, negative counts, orphan player/team/game IDs, provenance gaps, reliable-coverage rebound inconsistencies, or detected NULL-to-zero conversions.

The pipeline quarantined 125 source rows, all classified as `SOURCE_ANOMALY` and none as `PIPELINE_ERROR`. They occur in early-era PlayerGameLogs and contain made-shot/free-throw values exceeding attempts or missing attempts. The unchanged Bronze records remain available for audit; the pipeline did not repair them.

The standard July 1–June 30 date gate flags 3,743 rows: 3,586 in 2019-20 and 157 playoff rows in 2020-21. These are expected consequences of the COVID-delayed schedules, not fabricated corrections or pipeline failures. They remain in Silver and in the quality report.

## Reproducibility and performance

The required second build ran cache-only, made zero network calls, observed all 380 expected partitions, found no hash mismatch, and reproduced the aggregate corpus fingerprint exactly. A further fixed-input report check reproduced all seven committed JSON artifacts byte-for-byte.

The acquisition run took 373.72 seconds wall-clock, including 365.73 seconds of new network response time. Transformation took 397.10 seconds and reconciliation 0.36 seconds; total recorded build work was 783.71 seconds. Peak resident memory was approximately 600.7 MB. The complete local NBA API cache occupied 437,122,200 bytes at build time.

## Boundaries

This corpus contains player traditional and advanced facts only. It does not contain GOAT weights, era normalization, awards valuation, rankings, peak/longevity features, models, fan inputs, or frontend behavior. Generated Bronze and Silver files remain Git-ignored; the committed manifest and reports are the audit record.
