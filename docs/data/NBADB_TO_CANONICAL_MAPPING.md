# nbadb v238 to canonical Silver V1 mapping

This mapping is based only on the physical Kaggle `wyattowalsh/basketball` version 238 bundle audited in STEP-0002. The downloaded SQLite file has 16 legacy tables; it has no advertised `dim_*`, `fact_*`, `agg_*`, or `analytics_*` tables. Metadata descriptions are not treated as physical fields.

Status meanings:

- **Mapped:** copied or converted from an observed physical field.
- **Derived:** deterministically computed from mapped evidence.
- **Project metadata:** supplied by the ingestion/canonical methodology, not an NBA observation.
- **Unavailable:** no reliable physical source in this snapshot; no value is invented.

`source_id` for this snapshot is `nbadb:kaggle:wyattowalsh/basketball:v238`. `updated_at` is the explicit retrieval/canonicalization timestamp, never a fabricated source update time.

## `players`

| Canonical field | Status | Source table | Source column | Transformation / null behavior | Key behavior | Known limitations |
|---|---|---|---|---|---|---|
| `player_id` | Derived | `player` | `id` | UUIDv5 of `player:nba:<id>`; source ID must be non-null. | Canonical PK; name is never a key. | Cross-provider identity still needs an evidence crosswalk. |
| `nba_player_id` | Mapped | `player` | `id` | Preserve as string; null only for future non-NBA identities. | Unique alternate source key in this source. | SQLite declares no constraint. |
| `full_name` | Mapped | `player` | `full_name` | Trim; required. | Attribute only. | Display name can change. |
| `first_name` | Mapped | `player` | `first_name` | Preserve; nullable. | Not a key. | — |
| `last_name` | Mapped | `player` | `last_name` | Preserve; nullable. | Not a key. | — |
| `birth_date` | Mapped | `common_player_info` | `birthdate` | Join `person_id = player.id`; parse date; null if row/value absent. | Join uses provider ID. | `common_player_info` covers 3,632 of 4,815 `player` rows; e.g. some notable IDs are absent. |
| `country` | Mapped | `common_player_info` | `country` | Join and preserve; nullable. | Attribute only. | Provider vocabulary is not normalized in V1. |
| `height_cm` | Derived | `common_player_info` | `height` | Parse observed feet-inches text; multiply total inches by 2.54; unparseable/missing remains null. | Attribute only. | Listed height, not measurement-date history. |
| `weight_kg` | Derived | `common_player_info` | `weight` | Parse pounds and multiply by 0.45359237; unparseable/missing remains null. | Attribute only. | Listed weight, not measurement-date history. |
| `primary_position` | Mapped | `common_player_info` | `position` | Preserve source label; nullable. | Attribute only. | Career-long primary position is not independently verified. |
| `draft_year` | Mapped | `common_player_info` | `draft_year` | Numeric string to integer; `Undrafted`/non-numeric/missing becomes null. | Attribute only. | Draft facts can later be reconciled against `draft_history`. |
| `draft_round` | Mapped | `common_player_info` | `draft_round` | Numeric string to integer; non-numeric/missing becomes null. | Attribute only. | Same reconciliation limitation. |
| `draft_pick` | Mapped | `common_player_info` | `draft_number` | Numeric string to integer; non-numeric/missing becomes null. | Attribute only. | Represents overall draft number in this source, not round pick. |
| `career_start_year` | Mapped | `common_player_info` | `from_year` | Integral numeric to integer; missing remains null. | Attribute only. | Source can be stale and is not derived from game participation. |
| `career_end_year` | Mapped | `common_player_info` | `to_year` | Integral numeric to integer; missing remains null. | Attribute only. | Source observed values stop at 2023 and can be stale. |
| `is_active` | Mapped | `player` | `is_active` | `0/1` to boolean. | Attribute only. | Snapshot ends in 2022-23; activity is stale for current use. |
| `source_id` | Project metadata | — | — | Fixed audited snapshot identifier; never null. | Provenance field. | Does not imply every attribute came from one physical table. |
| `updated_at` | Project metadata | — | — | Explicit timezone-aware pipeline timestamp. | Audit field. | Not an upstream last-modified time. |

## `seasons`

| Canonical field | Status | Source table | Source column | Transformation / null behavior | Key behavior | Known limitations |
|---|---|---|---|---|---|---|
| `season_id` | Derived | `game` | `season_id` | Take final four digits of five-digit type-prefixed ID; integer start year. | Canonical PK; all season types collapse to one season. | Requires valid observed five-digit NBA ID. |
| `season_label` | Derived | `game` | `season_id` | `YYYY-(YYYY+1 suffix)`, e.g. `22022` → `2022-23`. | Unique alternate label. | — |
| `start_year` | Derived | `game` | `season_id` | Same integer as `season_id`. | Must equal canonical `season_id`. | — |
| `end_year` | Derived | `game` | `season_id` | `start_year + 1`. | Not a separate key. | NBA seasons spanning one year boundary only. |
| `games_scheduled` | Unavailable | — | — | Null. Actual observed game rows are not the scheduled-game count. | Attribute only. | Schedule rules changed by era and competition type. |
| `league` | Project metadata | Dataset scope | — | Constant `NBA`. | Attribute only. | ABA/non-NBA integration is not implemented. |
| `source_id` | Project metadata | — | — | Audited snapshot identifier. | Provenance field. | — |
| `updated_at` | Project metadata | — | — | Timezone-aware pipeline timestamp. | Audit field. | — |

## `franchises`

| Canonical field | Status | Source table | Source column | Transformation / null behavior | Key behavior | Known limitations |
|---|---|---|---|---|---|---|
| `franchise_id` | Derived | `team_history` / `team` | `team_id` / `id` | UUIDv5 of `franchise:nba:<team_id>`; union IDs across history/current tables. | Canonical PK grouping team versions. | Assumes provider team ID represents one lineage; relocations sharing/changing IDs need later review. |
| `current_name` | Derived | `team` primarily; `team_history` fallback | `full_name`; `city`, `nickname` | Use current `team.full_name`; otherwise latest history city + nickname; required. | Attribute only. | `team` includes only 30 current teams; defunct-only naming may be “latest known,” not current. |
| `source_id` | Project metadata | — | — | Audited snapshot identifier. | Provenance field. | — |
| `updated_at` | Project metadata | — | — | Timezone-aware pipeline timestamp. | Audit field. | — |

## `teams`

| Canonical field | Status | Source table | Source column | Transformation / null behavior | Key behavior | Known limitations |
|---|---|---|---|---|---|---|
| `team_id` | Derived | `team_history` | `team_id`, `year_founded`, `city`, `nickname` | UUIDv5 from NBA lineage ID plus version window/name evidence. Current-only fallback uses `team.id:current`. | Canonical version PK. | Version synthesis must quarantine overlapping/conflicting windows. |
| `nba_team_id` | Mapped | `team_history` / `team` | `team_id` / `id` | Preserve as string; nullable only for future non-NBA providers. | Source crosswalk; not canonical PK. | SQLite declares no constraint. |
| `franchise_id` | Derived | same | same ID | UUIDv5 lineage ID described above. | FK to `franchises`. | Same lineage assumption. |
| `team_name` | Derived | `team_history` | `city`, `nickname` | Join with one space; current fallback `team.full_name`; required. | Attribute only. | Historical punctuation/branding not independently verified. |
| `abbreviation` | Mapped/Unavailable | `team` | `abbreviation` | Direct for current row; historical rows remain null unless a later evidence-backed SCD mapping is added. | Not a key. | Per-game abbreviation exists but is not sufficient by itself to define validity windows. |
| `city` | Mapped | `team_history` / `team` | `city` | Preserve; nullable for incomplete rows. | Attribute only. | Source uses values such as `Golden State` that are branding, not municipalities. |
| `valid_from_year` | Mapped | `team_history` / `team` | `year_founded` | Integral year; required. | Part of version identity, not standalone key. | Column semantics are version-start in `team_history`, franchise founding in `team`. |
| `valid_to_year` | Mapped/Derived | `team_history` | `year_active_till` | Integral year; latest/current version may be set null only after joining current `team`. | Version boundary. | Source is stale: Lakers history ends at 2019 while game rows continue through 2023. Must not trust blindly. |
| `source_id` | Project metadata | — | — | Audited snapshot identifier. | Provenance field. | — |
| `updated_at` | Project metadata | — | — | Timezone-aware pipeline timestamp. | Audit field. | — |

## `games`

Source duplicates must be resolved before canonicalization. Identical game IDs published under `All Star` and `All-Star` normalize to `ALL_STAR` and collapse deterministically; any post-normalization conflict is quarantined rather than arbitrarily chosen.

| Canonical field | Status | Source table | Source column | Transformation / null behavior | Key behavior | Known limitations |
|---|---|---|---|---|---|---|
| `game_id` | Derived | `game` | `game_id` | UUIDv5 of `game:nba:<game_id>`; source must be non-null. | Canonical PK. | Physical source has 56 duplicate game-ID groups. |
| `nba_game_id` | Mapped | `game` | `game_id` | Preserve as string. | Unique alternate key after deduplication. | SQLite has no constraint. |
| `season_id` | Derived | `game` | `season_id` | Final four digits to start year. | FK to `seasons`. | Type prefix is discarded after `season_type` normalization. |
| `game_date` | Mapped | `game` | `game_date` | Parse date; missing is rejected/quarantined. | Attribute used for team-version resolution. | Time of day is not preserved in V1. |
| `season_type` | Derived | `game` | `season_type` | `Regular Season`→`REGULAR`; `Playoffs`→`PLAYOFF`; `All Star`/`All-Star`→`ALL_STAR`; `Pre Season`→`PRESEASON`. | Closed vocabulary and duplicate-normalization input. | `PLAY_IN` supported canonically but not separately labeled in the snapshot. |
| `playoff_round` | Unavailable | — | — | Null. | Attribute only. | `game` has no reliable round field; do not infer from date/game number in V1. |
| `home_team_id` | Derived | `game` | `team_id_home` | Resolve NBA team ID plus game year to one canonical team version; unresolved/ambiguous rows fail. | FK to `teams`. | Stale/overlapping team-history windows require reconciliation. |
| `away_team_id` | Derived | `game` | `team_id_away` | Same versioned resolution. | FK to `teams`; must differ from home. | Same limitation. |
| `home_score` | Mapped | `game` | `pts_home` | Integral numeric to integer; missing remains null. | Result attribute. | Source uses floating storage type. |
| `away_score` | Mapped | `game` | `pts_away` | Integral numeric to integer; missing remains null. | Result attribute. | Source uses floating storage type. |
| `winner_team_id` | Derived | `game` | `pts_home`, `pts_away`; cross-check `wl_home`, `wl_away` | Higher final score's canonical team; tie/incomplete is null; conflicts are validation failures. | FK to one participant. | Historical data should be final, but canonical contract supports incomplete games. |
| `source_id` | Project metadata | — | — | Audited snapshot identifier. | Provenance field. | — |
| `updated_at` | Project metadata | — | — | Timezone-aware pipeline timestamp. | Audit field. | — |

## `player_game_stats`

The physical bundle has no player box-score table. `play_by_play` is not a complete or defensible substitute for official player box scores. Every requested fact field is therefore unavailable from v238; the typed table exists but no v238 rows are materialized.

| Canonical field | Status | Source table | Source column | Transformation / null behavior | Key behavior | Known limitations |
|---|---|---|---|---|---|---|
| `game_id` | Unavailable | — | — | No row materialized. | Intended composite PK/FK component. | Requires a future player-game source. |
| `player_id` | Unavailable | — | — | No row materialized. | Intended composite PK/FK component. | Same. |
| `team_id` | Unavailable | — | — | No row materialized. | Intended composite PK/FK component. | Same. |
| `season_id` | Unavailable | — | — | No row materialized. | Intended FK/context. | Same. |
| `season_type` | Unavailable | — | — | No row materialized. | Closed vocabulary context. | Same. |
| `minutes` | Unavailable | — | — | Nullable; never zero-filled. | Fact attribute. | Same. |
| `points` | Unavailable | — | — | Nullable; never zero-filled. | Fact attribute. | Same. |
| `fgm` | Unavailable | — | — | Nullable; never zero-filled. | Fact attribute. | Same. |
| `fga` | Unavailable | — | — | Nullable; never zero-filled. | Fact attribute. | Same. |
| `fg3m` | Unavailable | — | — | Nullable; historically unavailable is not zero. | Fact attribute. | Same. |
| `fg3a` | Unavailable | — | — | Nullable; historically unavailable is not zero. | Fact attribute. | Same. |
| `ftm` | Unavailable | — | — | Nullable; never zero-filled. | Fact attribute. | Same. |
| `fta` | Unavailable | — | — | Nullable; never zero-filled. | Fact attribute. | Same. |
| `oreb` | Unavailable | — | — | Nullable; historically unavailable is not zero. | Fact attribute. | Same. |
| `dreb` | Unavailable | — | — | Nullable; historically unavailable is not zero. | Fact attribute. | Same. |
| `rebounds` | Unavailable | — | — | Nullable; never reconstructed from incomplete components. | Fact attribute. | Same. |
| `assists` | Unavailable | — | — | Nullable; never zero-filled. | Fact attribute. | Same. |
| `steals` | Unavailable | — | — | Nullable; historically unavailable is not zero. | Fact attribute. | Same. |
| `blocks` | Unavailable | — | — | Nullable; historically unavailable is not zero. | Fact attribute. | Same. |
| `turnovers` | Unavailable | — | — | Nullable; historically unavailable is not zero. | Fact attribute. | Same. |
| `personal_fouls` | Unavailable | — | — | Nullable; never zero-filled. | Fact attribute. | Same. |
| `plus_minus` | Unavailable | — | — | Nullable; never inferred from team margin as player plus-minus. | Fact attribute. | Same. |
| `started` | Unavailable | — | — | Nullable boolean distinguishes unknown from false. | Fact attribute. | Same. |
| `did_play` | Unavailable | — | — | Nullable boolean distinguishes unknown from DNP/played. | Fact attribute. | Same. |
| `source_id` | Project metadata | — | — | Required when future rows exist. | Provenance field. | No v238 rows. |
| `updated_at` | Project metadata | — | — | Required when future rows exist. | Audit field. | No v238 rows. |

## `player_season_stats`

No physical player-game or player-season statistical table exists. These rows must eventually be derived from reliable canonical player-game facts (or mapped from a separately audited aggregate source with lineage). v238 materializes none.

| Canonical field | Status | Source / intended derivation | Null and key behavior | Known limitations |
|---|---|---|---|---|
| `player_id` | Unavailable | Future canonical player-game facts. | Composite PK/FK component. | No v238 input. |
| `season_id` | Unavailable | Future canonical player-game facts. | Composite PK/FK component. | No v238 input. |
| `season_type` | Unavailable | Future canonical player-game facts. | Composite PK context. | No v238 input. |
| `row_scope` | Project methodology | `TEAM` per team; one `TOTAL` row across teams. | Composite PK component. | No rows yet. |
| `team_id` | Unavailable | Future canonical player-game facts. | Required for `TEAM`, null for `TOTAL`. | No v238 input. |
| `games_played` | Unavailable | Count reliable `did_play=true` rows. | Nullable, never assumed from schedule. | No v238 input. |
| `games_started` | Unavailable | Count reliable `started=true` rows. | Nullable when starter coverage is unknown. | No v238 input. |
| `minutes_total` | Unavailable | Sum observed minutes. | Nullable if coverage incomplete. | No v238 input. |
| `points_total` | Unavailable | Sum observed points. | Nullable if coverage incomplete. | No v238 input. |
| `fgm_total` | Unavailable | Sum observed FGM. | Nullable if coverage incomplete. | No v238 input. |
| `fga_total` | Unavailable | Sum observed FGA. | Nullable if coverage incomplete. | No v238 input. |
| `fg3m_total` | Unavailable | Sum observed 3PM only under eligible coverage. | Historically unavailable remains null. | No v238 input. |
| `fg3a_total` | Unavailable | Sum observed 3PA only under eligible coverage. | Historically unavailable remains null. | No v238 input. |
| `ftm_total` | Unavailable | Sum observed FTM. | Nullable if coverage incomplete. | No v238 input. |
| `fta_total` | Unavailable | Sum observed FTA. | Nullable if coverage incomplete. | No v238 input. |
| `oreb_total` | Unavailable | Sum observed OREB under eligible coverage. | Historically unavailable remains null. | No v238 input. |
| `dreb_total` | Unavailable | Sum observed DREB under eligible coverage. | Historically unavailable remains null. | No v238 input. |
| `rebounds_total` | Unavailable | Sum observed total rebounds. | Never rebuild from incomplete OREB/DREB. | No v238 input. |
| `assists_total` | Unavailable | Sum observed assists. | Nullable if coverage incomplete. | No v238 input. |
| `steals_total` | Unavailable | Sum observed steals under eligible coverage. | Historically unavailable remains null. | No v238 input. |
| `blocks_total` | Unavailable | Sum observed blocks under eligible coverage. | Historically unavailable remains null. | No v238 input. |
| `turnovers_total` | Unavailable | Sum observed turnovers under eligible coverage. | Historically unavailable remains null. | No v238 input. |
| `personal_fouls_total` | Unavailable | Sum observed personal fouls. | Nullable if coverage incomplete. | No v238 input. |
| `minutes_per_game` | Unavailable | `minutes_total / games_played` when valid. | Null for zero/unknown denominator. | No v238 input. |
| `points_per_game` | Unavailable | `points_total / games_played` when valid. | Null for zero/unknown denominator. | No v238 input. |
| `rebounds_per_game` | Unavailable | `rebounds_total / games_played` when valid. | Null for zero/unknown denominator. | No v238 input. |
| `assists_per_game` | Unavailable | `assists_total / games_played` when valid. | Null for zero/unknown denominator. | No v238 input. |
| `steals_per_game` | Unavailable | `steals_total / games_played` when eligible. | Historically unavailable remains null. | No v238 input. |
| `blocks_per_game` | Unavailable | `blocks_total / games_played` when eligible. | Historically unavailable remains null. | No v238 input. |
| `turnovers_per_game` | Unavailable | `turnovers_total / games_played` when eligible. | Historically unavailable remains null. | No v238 input. |
| `fg_pct` | Unavailable | `fgm_total / fga_total` when denominator > 0. | Fraction `[0,1]`; null for unknown/zero denominator. | No v238 input. |
| `fg3_pct` | Unavailable | `fg3m_total / fg3a_total` when denominator > 0 and eligible. | Historically unavailable/zero denominator remains null. | No v238 input. |
| `ft_pct` | Unavailable | `ftm_total / fta_total` when denominator > 0. | Fraction `[0,1]`; null for unknown/zero denominator. | No v238 input. |
| `source_id` | Project metadata | Future aggregate lineage identifier. | Required per row. | No v238 rows. |
| `updated_at` | Project metadata | Future pipeline timestamp. | Required per row. | No v238 rows. |

## `player_season_advanced`

No advanced player source exists physically. All metric values remain unavailable and nullable; no traditional statistic is relabeled as an advanced metric.

| Canonical field | Status | Source / intended derivation | Null and key behavior | Known limitations |
|---|---|---|---|---|
| `player_id` | Unavailable | Future audited advanced/player-game source. | Composite PK/FK component. | No v238 input. |
| `season_id` | Unavailable | Future audited advanced/player-game source. | Composite PK/FK component. | No v238 input. |
| `season_type` | Unavailable | Future audited advanced/player-game source. | Composite PK context. | No v238 input. |
| `row_scope` | Project methodology | `TEAM` or `TOTAL`. | Composite PK component. | No rows yet. |
| `team_id` | Unavailable | Future source. | Required for `TEAM`, null for `TOTAL`. | No v238 input. |
| `games_played` | Unavailable | Future source/derived coverage. | Nullable. | No v238 input. |
| `minutes` | Unavailable | Future source. | Nullable. | No v238 input. |
| `offensive_rating` | Unavailable | Future audited definition. | Nullable. | Provider formulas can differ. |
| `defensive_rating` | Unavailable | Future audited definition. | Nullable. | Provider formulas can differ. |
| `net_rating` | Unavailable | Future audited definition or OffRtg−DefRtg. | Nullable; derivation must be recorded. | Provider formulas can differ. |
| `pace` | Unavailable | Future audited definition. | Nullable. | Coverage and units vary. |
| `usage_pct` | Unavailable | Future audited definition. | Nullable. | Coverage and scale must be documented. |
| `true_shooting_pct` | Unavailable | Future audited definition. | Nullable. | Historical inputs can be incomplete. |
| `effective_fg_pct` | Unavailable | Future audited definition. | Nullable. | Historical 3P inputs can be unavailable. |
| `assist_pct` | Unavailable | Future audited definition. | Nullable. | Provider formula differences. |
| `oreb_pct` | Unavailable | Future audited definition. | Nullable. | Historical OREB coverage. |
| `dreb_pct` | Unavailable | Future audited definition. | Nullable. | Historical DREB coverage. |
| `rebound_pct` | Unavailable | Future audited definition. | Nullable. | Historical component coverage. |
| `turnover_pct` | Unavailable | Future audited definition. | Nullable. | Historical turnover coverage. |
| `pie` | Unavailable | Future NBA Stats definition. | Nullable. | Modern-era/provider-specific coverage. |
| `possessions` | Unavailable | Future audited raw/derived definition. | Nullable. | Estimation formulas vary. |
| `source_id` | Project metadata | Future lineage identifier. | Required per row. | No v238 rows. |
| `updated_at` | Project metadata | Future pipeline timestamp. | Required per row. | No v238 rows. |

## `player_awards`

No physical award table exists in nbadb v238. STEP-0009 therefore maps factual events from
official NBA Stats `PlayerAwards`; names remain diagnostic and are never identity keys.

| Canonical field | Status | Source table | Source column | Transformation / null behavior | Key behavior | Known limitations |
|---|---|---|---|---|---|---|
| `award_id` | Derived | `PlayerAwards` | complete raw row | UUIDv5 over deterministic source-event fingerprint. | Canonical PK. | Exact source duplicates collapse; distinct week/month events remain. |
| `player_id` | Mapped | Candidate identity registry | `player_id` | Join requested numeric ID to STEP-0008 canonical identity. | FK to `players`. | Candidate scope is not permanent eligibility. |
| `nba_player_id` | Mapped | `PlayerAwards` | `PERSON_ID` | Normalize integral numeric representations; must equal requested ID. | Source business key. | Names never repair a mismatch. |
| `season_id` | Derived | `PlayerAwards` | `SEASON` | Parse valid `YYYY-YY` to start year; calendar-only labels remain NULL. | Nullable FK to `seasons`. | External/Hall of Fame/Olympic calendar years are not guessed into NBA seasons. |
| `season_label_raw` | Raw | `PlayerAwards` | `SEASON` | Trim only; preserve provider label. | Audit attribute. | May be calendar year. |
| `season_mapping_status` | Derived | `PlayerAwards` | `SEASON` | `MAPPED` or `SEASON_MAPPING_UNKNOWN`. | Coverage attribute. | No inferred fallback. |
| `award_type` | Mapped | `PlayerAwards` | `DESCRIPTION` | Exact observed-string registry; unrecognized descriptions map to `OTHER`. | Controlled vocabulary. | Registry is versioned and exhaustive for this acquisition. |
| `award_level` | Derived | `PlayerAwards` | `ALL_NBA_TEAM_NUMBER` | `FIRST`, `SECOND`, or `THIRD` only for structured team awards. | Attribute. | No text inference. |
| `award_scope` | Mapped | `PlayerAwards` | `DESCRIPTION` | `LEAGUE`, `CONFERENCE`, `TEAM`, `EXTERNAL`, or `UNKNOWN`. | Attribute. | Scope is not award value. |
| `team_number` | Raw-normalized | `PlayerAwards` | `ALL_NBA_TEAM_NUMBER` | Integer 1/2/3 for All-NBA, All-Defense, All-Rookie, and Cup team. | Attribute. | Historical level absence is structural. |
| `conference` | Raw | `PlayerAwards` | `CONFERENCE` | Trim blank to NULL. | Attribute. | Source alternates team ID and East/West strings. |
| `month` | Raw | `PlayerAwards` | `MONTH` | Preserve provider value. | Repeated-event key component. | Format is source-specific. |
| `week` | Raw | `PlayerAwards` | `WEEK` | Preserve provider value. | Repeated-event key component. | Distinct weeks never collapse. |
| `source_description` | Raw | `PlayerAwards` | `DESCRIPTION` | Required verbatim value after whitespace trim. | Taxonomy evidence. | No raw description disappears. |
| `source_type` | Raw | `PlayerAwards` | `TYPE` | Nullable source field. | Audit attribute. | All observed values are `Award`. |
| `source_subtype1` | Raw | `PlayerAwards` | `SUBTYPE1` | Blank to NULL. | Audit attribute. | Sponsor/series semantics vary. |
| `source_subtype2` | Raw | `PlayerAwards` | `SUBTYPE2` | Blank to NULL. | Audit attribute. | Provider code is retained, not modeled directly. |
| `source_subtype3` | Raw | `PlayerAwards` | `SUBTYPE3` | Blank to NULL. | Audit attribute. | Sparse. |
| `source_team` | Raw | `PlayerAwards` | `TEAM` | Blank to NULL; not used as a relational key. | Diagnostic attribute. | Historical names may vary. |
| `taxonomy_status` | Mapped | STEP-0009 registry | `DESCRIPTION` | Core, secondary, recurring, non-player competitive, or unknown. | Coverage attribute. | Describes event category, never greatness value. |
| `source_event_fingerprint` | Derived | `PlayerAwards` | complete raw row | SHA-256 of sorted raw source fields. | Deduplication evidence. | Row order excluded. |
| `source_id` | Project metadata | Source manifest | — | `nba_stats:playerawards:nba_api:1.11.4`. | Provenance field. | — |
| `retrieved_at` | Project metadata | Acquisition checkpoint | — | Original request/cache evidence timestamp. | Provenance field. | Stable on cache-only rebuild. |
| `methodology_version` | Project metadata | STEP-0009 | — | `official-player-awards-canonical-v1`. | Version attribute. | Mapping changes require a new step/version. |
| `updated_at` | Project metadata | Pipeline | — | Equal to retrieval evidence timestamp for V1. | Audit field. | Timezone-aware. |

## `metric_coverage`

This is a project-authored Silver control table, not a direct NBA endpoint table. STEP-0003 defines its contract but does not seed “first reliable season” claims from raw minima. Rows require a documented coverage study or endpoint contract.

| Canonical field | Status | Evidence source | Transformation / null behavior | Key behavior | Known limitations |
|---|---|---|---|---|---|
| `canonical_entity` | Project metadata | Canonical schema | Exact entity name; required. | Composite key component. | Renames require schema migration. |
| `metric` | Project metadata | Canonical schema | Exact canonical field name; required. | Composite key component. | Must not use vendor field names. |
| `provider` | Project metadata | Source manifest | Stable provider/snapshot label. | Composite key component. | Multiple snapshots may need effective dating later. |
| `first_reliable_season` | Project methodology | Future endpoint/coverage study | Nullable; not inferred from first non-null. | Reliability window. | Not seeded in STEP-0003. |
| `last_reliable_season` | Project methodology | Future endpoint/coverage study | Nullable; must not precede first. | Reliability window. | Not seeded in STEP-0003. |
| `season_type` | Project methodology | Source coverage contract | Closed canonical type. | Composite key component. | Provider coverage can differ by type. |
| `coverage_status` | Project methodology | Audit/coverage evidence | `OBSERVED`, `PARTIAL`, `HISTORICALLY_UNAVAILABLE`, `SOURCE_UNAVAILABLE`, or `UNKNOWN`. | Status attribute. | Needs periodic review on new snapshots. |
| `metric_origin` | Project methodology | Lineage | `RAW` or `DERIVED`. | Lineage attribute. | Derived methodology must be named. |
| `cross_era_eligible` | Project methodology | Methodology review | Boolean; false until defensible comparability is established. | Eligibility control. | Eligibility may differ by model/feature version later. |
| `methodology` | Project metadata | Coverage study | Required textual definition/evidence. | Audit attribute. | Must be versioned when materially changed. |
| `notes` | Project metadata | Coverage study | Nullable supporting detail. | Audit attribute. | — |
| `source_id` | Project metadata | Source manifest / methodology version | Required. | Provenance field. | — |
| `updated_at` | Project metadata | Pipeline | Timezone-aware timestamp. | Audit field. | — |

## Source surfaces deliberately not mapped

- `game` contains team-level traditional statistics; these do not belong in `player_game_stats`.
- `play_by_play` contains event participants but cannot reproduce complete official player box scores reliably.
- `common_player_info.season_exp` is not used to calculate season participation or longevity.
- `common_player_info.team_*` is a stale snapshot attribute, not a historical player-team relationship.
- Dataset metadata descriptions of absent v4 tables are not treated as data.
