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
