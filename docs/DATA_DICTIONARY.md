# Data dictionary

This document indexes project-owned data concepts. Historical Silver contracts remain in `docs/data/canonical-schema-v1.json`; STEP-0009 award-event evolution is exported to `docs/data/canonical-schema-v2.json`; STEP-0010 factual team/postseason contracts are exported to `docs/data/canonical-schema-v3.json`. Field-level source lineage is in `docs/data/NBADB_TO_CANONICAL_MAPPING.md`.

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

## GOATLAB-HIST-V1 physical corpus

The STEP-0006 frozen release applies the existing Silver contracts to every Regular Season and Playoff partition from 1946-47 through 2025-26:

- 160 `player_game_stats` partitions at canonical grain `(game_id, player_id, team_id)`.
- 160 `player_season_stats` partitions containing 40,553 TEAM and 37,472 TOTAL rows.
- 60 `player_season_advanced` TOTAL partitions from the empirical 1996-97 boundary.

The generated Parquet files remain ignored. `docs/data/historical-corpus-v1-manifest.json` is the committed physical catalog: it stores relative path, row/column count, byte size, and SHA-256 for each of 380 partitions plus an aggregate fingerprint. `historical_corpus_end_season` is fixed at `2025-26`; a post-cutoff partition is invalid for this corpus.

The ignored backfill checkpoint records one state for every request scope: `PENDING`, `SUCCESS_WITH_ROWS`, `SUCCESS_EMPTY`, `FAILED_RETRYABLE`, `FAILED_PERMANENT`, or `UNSUPPORTED`. Output state is tracked separately so acquisition success cannot be confused with a written/reconciled Silver partition.

Official-source-only `nba_player_id` values receive deterministic canonical IDs and a provenance-bearing provisional identity rather than losing their facts. Provisional describes incomplete biography metadata, not an unresolved relational key. Team crosswalk rows use official `nba_team_id` and observed name/version evidence; legacy validity-window conflicts are diagnostic.

The full empirical metric matrix contains 3,040 records using the unchanged qualification vocabulary. The full quality report separately counts source anomaly quarantine and pipeline error quarantine; only accepted Silver rows participate in aggregation.

## Gold era-normalization V1

Generated Gold is deterministic Parquet partitioned by season and season_type and remains Git-ignored.

| Entity | Grain / key | Purpose |
|---|---|---|
| league_season_context | season × season type | Qualified population counts/distributions, shooting references, accepted-game team scoring context, and eligible official advanced context. |
| player_season_feature_long | player × season × type × metric × rate basis | Authoritative primitive value, distribution statistics, normalization results, eligibility, qualification, sample size, and provenance. |
| player_season_normalized | player × season × type | Curated wide materialization of commonly consumed normalized primitives. |

Every Gold row carries corpus_id, corpus_fingerprint, and methodology_version. Only Silver TOTAL rows feed distributions. qualification_status is QUALIFIED or NOT_QUALIFIED, and non-qualified rows remain. Long-Gold coverage_status is a method eligibility result such as AVAILABLE, UNAVAILABLE_COVERAGE with a reason, UNAVAILABLE_POSSESSIONS, or a variance/denominator condition. It is not Silver coverage vocabulary or a performance score.

The long record includes identity and partition keys, metric/rate basis, raw and comparison values, population size, mean, median, standard deviation, MAD, z-scores, percentile, relative index, coverage/qualification, opportunity, sample games, methodology, corpus identity, and source lineage. Percentile uses [0,1] midrank ties.

The registry defines 16 primitives: games, minutes, PPG, points per 36/per 75, RPG/rebounds per 36, APG/assists per 36, SPG, BPG, FG%, FT%, 3P%, eFG%, and TS%. Per-36 requires reliable positive minutes. Per-75 requires official Advanced/Totals possessions and has no pre-1996 substitute. The feature registry and eligibility matrix form the legal input contract for later Gold/model work.

## Gold career trajectory V1

Generated career Gold is deterministically bucketed by player into 32 partitions per entity and remains Git-ignored.

| Entity | Grain / key | Purpose |
|---|---|---|
| player_career_summary | player | Participation, completion/active evidence, minutes coverage, and age availability across both season types. |
| player_career_trajectory | player × season type × elapsed season | Appeared seasons and explicit gaps, qualification, opportunity, feature count, minutes, age, and provenance. |
| player_career_features | player × season type × metric × normalization method | Metric-specific career distribution, best season, non-contiguous best sets, elite counts, cumulative dominance, and coverage. |
| player_peak_windows | player × season type × metric × method × window × variant | Complete contiguous 1/3/5-year quality and availability-adjusted peak records. |
| player_prime_runs | player × season type × metric × percentile threshold | Elite counts/proportions and longest consecutive 80th/90th/95th/99th-percentile runs. |

All entities carry career methodology version, normalization version/fingerprint, and corpus ID/fingerprint. Unavailable metric-career and peak combinations have explicit coverage status and NULL values. Gap rows use GAP_NO_APPEARANCE; games are observed zero for a season in which the player did not appear, while unavailable statistics remain NULL.

Career status vocabulary is ACTIVE_TO_CUTOFF, SOURCE_CONFIRMED_COMPLETE, and INDETERMINATE. Age fields use audited birth dates only. Peak variant vocabulary is QUALITY and AVAILABILITY_ADJUSTED. Non-contiguous top-three/top-five sets are stored separately in metric career summaries and never use peak-window naming.

## Silver awards and Gold accolades V1

`player_awards` is one official source event keyed by deterministic `award_id`. It carries canonical and NBA player IDs, nullable canonical season plus raw label/status, controlled award type/scope/level, month/week/conference, every raw description/subtype/team field, taxonomy status, source fingerprint, retrieval timestamp, methodology version, and provenance.

Taxonomy status is `CANONICAL_CORE`, `CANONICAL_SECONDARY`, `MINOR_RECURRING`, `NON_PLAYER_COMPETITIVE`, or `UNKNOWN`. Award acquisition status is `PENDING`, `SUCCESS_WITH_ROWS`, `SUCCESS_EMPTY`, `FAILED_RETRYABLE`, `FAILED_PERMANENT`, or `NOT_QUERIED`.

`player_career_accolades` is one row per master player. Supported event-type and structured-level fields are factual integer counts only for successful requests. Every count is NULL for `NOT_QUERIED`. It carries candidate/status/provenance fields and creates no composite value.

## Silver team success and Gold team context V1

Generated STEP-0010 outputs are deterministic Parquet and remain Git-ignored.

| Entity | Grain / key | Purpose |
|---|---|---|
| `team_season_results` | team × season | Regular/playoff W/L, scoring context, within-season strength primitives, champion/runner-up, and conditional series facts. |
| `finals_games` | validated Finals game | Champion/runner-up matchup, result, sequence number, venue-assignment evidence, and provenance. |
| `player_team_season_participation` | player × team × season | Regular/playoff/Finals games and coverage-qualified minutes/shares plus distinct champion participation semantics. |
| `player_team_success_primitives` | bucketed copy of player-team-season derived facts | Gold-facing factual primitives for later methodology. |
| `player_career_team_context` | player | Career playoff/Finals participation, team-strength context, and separate championship participation counts. |

`finalist` means the Finals runner-up and is mutually exclusive with `champion`; `champion OR finalist` means the team reached the Finals. `finals_opponent_team_id` is present for both Finals participants.

Postseason format status is `STANDARD_SERIES_BRACKET`, `NONSTANDARD_SERIES_FORMAT`, `ROUND_ROBIN_OR_MIXED`, or `UNCERTAIN`. Team-success coverage uses `RELIABLE`, `PARTIAL`, `UNAVAILABLE`, `FORMAT_BLOCKED`, and `UNKNOWN`. Conditional series fields are NULL when format-blocked.

Player championship facts are not interchangeable: regular-season membership, playoff participation, Finals participation, and official NBA Champion award event are separate fields. The award field is nullable because STEP-0009 did not query every player. Game shares use distinct player appearances divided by team games. Minute shares are NULL unless the underlying partition passes empirical coverage and positive-minute gates.

Canonical schema V3 adds `TeamSeasonResult`, `FinalsGame`, and `PlayerTeamSeasonParticipation`; it does not alter frozen GOATLAB-HIST-V1 player facts. Gold career rows create no subjective championship or team-success value.

## Silver All-Star/leader evidence and Gold factual counts V1

| Entity | Grain / key | Purpose |
|---|---|---|
| `player_all_star_evidence` | player × All-Star season | Independent official event-roster, game-participation, and nullable PlayerAwards evidence with contributing game IDs and provenance. |
| `player_stat_leaders` | player × season × category | Union of official-source rank one, raw per-game/total, and coverage-qualified leader evidence. |
| `player_career_all_star` | player with All-Star evidence | Explicit event-roster-season, game-participation, and nullable PlayerAwards-event counts. |
| `player_career_stat_titles` | player with leader evidence | Source-rank-one and derived-qualified counts by category; no value or weighting. |
| `player_career_accolades_complete` | master player | STEP-0009 counts extended with separately named STEP-0011 evidence fields. |

All-Star selection status is `ROSTER_LISTED`, `PLAYERAWARDS_EVENT`, `MULTIPLE_EVIDENCE`, or `PARTICIPATION_ONLY`. Participation status is `GAME_PARTICIPANT`, `DNP_ROSTERED`, or `NO_PARTICIPATION_EVIDENCE`. `roster_scope=OFFICIAL_EVENT_GAME_ROSTER` does not claim original-selection semantics.

Stat category is `PTS`, `REB`, `AST`, `STL`, or `BLK`. Reconciliation status is `EXACT_MATCH`, `TIE_MATCH`, `VALUE_MATCH`, `QUALIFICATION_DIFFERENCE`, `SOURCE_COVERAGE_GAP`, `DERIVED_COVERAGE_GAP`, or `UNRESOLVED`. `leader_semantics` names the evidence; an official source rank is not silently promoted to an official historical title.

Canonical schema V4 adds `PlayerAllStarEvidence` and `PlayerStatLeader`; existing schema exports and frozen Silver facts remain unchanged.

## Gold dimension candidate audit V1

Generated STEP-0012 Gold remains ignored and is partitioned by dimension/candidate.

| Entity | Grain / key | Purpose |
|---|---|---|
| `dimension_candidate_scores` | player × candidate × scaling × missingness policy | Internal diagnostic candidate value with population flags, career-completeness context, and coverage; never an overall or final score. |
| `dimension_candidate_coverage` | player × candidate | Expected/available component counts, core/optional coverage, confidence, and historical comparability. |
| `dimension_candidate_sensitivity` | candidate | Fixed-seed internal-weight variance, percentile IQR, and sampled ordering stability. |

Closed candidate dimensions are `PEAK`, `LONGEVITY`, `OFFENSE`, `DEFENSE`, `PLAYOFFS`, `ACCOLADES`, `WINNING`, and `ERA_DOMINANCE`. Scaling is `CAREER_UNIVERSE_PERCENTILE`, `ROBUST_STANDARDIZATION`, `STANDARD_Z`, or `EMPIRICAL_CDF`. Missingness is `CORE_FEATURE_ONLY`, `AVAILABLE_FEATURE_RENORMALIZATION`, `COVERAGE_THRESHOLD`, or `ERA_SPECIFIC_ENRICHMENT`. Coverage confidence is `STRONG`, `MODERATE`, `LIMITED`, or `UNAVAILABLE` and is never a quality penalty.

Candidate status may be `PROPOSED`, `VALIDATED_FOR_EXPERIMENT`, `REJECTED`, or `DEFERRED`; `FINAL` is prohibited in this methodology version. All rows carry corpus and methodology provenance. No table combines candidates across dimensions.
