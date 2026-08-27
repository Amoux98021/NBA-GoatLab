# Data dictionary

This document indexes project-owned data concepts. The machine-readable contracts are exported to `docs/data/canonical-schema-v1.json`; field-level source lineage is in `docs/data/NBADB_TO_CANONICAL_MAPPING.md`.

## Missingness vocabulary

- **Observed zero:** the metric was applicable and recorded with value zero.
- **Missing value:** the metric should be present under known coverage but the value is absent.
- **Historically unavailable:** the metric was not officially recorded or did not exist for the observation's era.
- **Source unavailable:** the provider or acquired snapshot lacks usable coverage despite conceptual applicability.

None of these states may be silently converted into another.

## Silver V1 entities

| Entity | Grain / canonical key | Purpose |
|---|---|---|
| `players` | one person; `player_id` | Project identity, NBA crosswalk, biography, draft, and career bounds. |
| `seasons` | one NBA season; `season_id` | Season label/year contract. V1 uses start year as the ID. |
| `franchises` | one franchise lineage; `franchise_id` | Stable lineage across team city/name versions. |
| `teams` | one franchise name/version window; `team_id` | Team identity valid for a bounded historical period. |
| `games` | one game; `game_id` | Schedule context, participants, type, score, and winner. |
| `player_game_stats` | player × game × team | Nullable traditional player box-score observations. |
| `player_season_stats` | player × season × type × scope × team | Traditional totals, per-game rates, and shooting percentages; includes team rows and one total row. |
| `player_season_advanced` | player × season × type × scope × team | Nullable advanced statistics kept separate because coverage differs by era. |
| `player_awards` | one award event; `award_id` | Canonical award vocabulary and optional level/team designation. |
| `metric_coverage` | entity × metric × provider × season type | Reliability window, source/derived status, cross-era eligibility, and methodology evidence. |

All canonical entities carry `source_id` and `updated_at`. `updated_at` must be timezone-aware. Canonical models reject undeclared fields.

## Closed vocabularies

- `season_type`: `REGULAR`, `PLAYOFF`, `PLAY_IN`, `ALL_STAR`, `PRESEASON`.
- `row_scope`: `TEAM`, `TOTAL`.
- `metric_origin`: `RAW`, `DERIVED`.
- `coverage_status`: `OBSERVED`, `PARTIAL`, `HISTORICALLY_UNAVAILABLE`, `SOURCE_UNAVAILABLE`, `UNKNOWN`.
- `award_type`: `MVP`, `FINALS_MVP`, `DPOY`, `ROY`, `MIP`, `SIXTH_MAN`, `ALL_NBA`, `ALL_DEFENSE`, `ALL_STAR`, `SCORING_TITLE`, `REBOUND_TITLE`, `ASSIST_TITLE`, `STEAL_TITLE`, `BLOCK_TITLE`.

Percentages in traditional season facts use fractions in `[0, 1]`. Advanced percentage/rate fields remain provider-definition values and are nullable; their unit/definition must be stated in `metric_coverage.methodology` before analytical use.

## Official NBA Stats source mapping notes

- `PlayerGameLogs` grain is player × game × team. Candidate key: (`PLAYER_ID`, `GAME_ID`, `TEAM_ID`). STEP-0004 found no duplicate candidate keys in the representative matrix.
- `LeagueDashPlayerStats` Base/Totals maps to canonical `player_season_stats` total rows. Its empirical response boundary in this probe is 1996-97; earlier tested seasons returned successful empty result sets.
- `LeagueDashPlayerStats` Advanced/Totals maps to `player_season_advanced` total rows and empirically begins at 1996-97.
- Official `PLAYER_ID` maps to `nba_player_id`, then to deterministic canonical `player_id`. NBA `GAME_ID` maps similarly. Names and abbreviations are not keys.
- Documented historical introductions remain authoritative missingness guards: rebounds 1950-51, minutes 1951-52, games started 1970-71, steals/blocks/offensive/defensive rebounds 1973-74, turnovers 1977-78, and three-point statistics 1979-80. Endpoint placeholders before these boundaries are not observations.
- PlayerGameLogs does not expose `started`; it remains NULL. Team-version resolution must use the canonical team crosswalk rather than fabricate a version ID.

## STEP-0005 physical Silver contract

Generated Silver data is deterministic Parquet partitioned by canonical season start year and season type:

- `data/silver/player_game_stats/season=YYYY/season_type=REGULAR|PLAYOFF/`
- `data/silver/player_season_stats/season=YYYY/season_type=REGULAR|PLAYOFF/`
- `data/silver/player_season_advanced/season=YYYY/season_type=REGULAR|PLAYOFF/`

These generated datasets are ignored by Git. Their manifest records row counts, byte sizes, and SHA-256 fingerprints.

`player_season_stats` contains both `TEAM` and `TOTAL` rows. For a player × season × season type, at most one `TOTAL` row is allowed. Totals are sums only for empirically RELIABLE metrics whose contributing player rows are complete. `games_played` is the count of distinct qualified game appearances. Shooting percentages divide summed makes by summed attempts only for a positive denominator. Per-game fields divide qualified totals by `games_played`. Any unavailable numerator, denominator, or source coverage yields NULL.

The STEP-0005 empirical coverage report uses an analytical qualification vocabulary distinct from the Silver `metric_coverage.coverage_status` enum:

- `RELIABLE`: at least 99% of partition rows are non-null.
- `PARTIAL`: at least 80% but less than 99% are non-null.
- `SPARSE`: more than 0% but less than 80% are non-null.
- `UNAVAILABLE`: historical rules or the source contract establish inapplicability.
- `UNKNOWN`: the metric is conceptually applicable but has no usable observation.

Each record stores row, non-null, null, observed-zero, and distinct-player counts plus percentages, endpoint, documented status, and thresholds. Column existence alone never produces `RELIABLE`.
