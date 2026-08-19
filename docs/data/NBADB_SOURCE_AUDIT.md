# nbadb source audit

Audited Kaggle `wyattowalsh/basketball` version `238` retrieved at `2026-08-19T16:52:59Z`. All SQL checks were read-only.

## Publication/bundle reconciliation

| Check | Declared | Observed |
|---|---:|---:|
| Catalog tables | 235 | 16 SQLite tables |
| CSV exports | 0/235 | 16 files |
| DuckDB catalog objects | 235 implied | 0 |

The downloaded bundle does **not** contain the advertised v4 star schema. The 12 KiB DuckDB file has no user tables; the 2.35 GB SQLite file contains 16 legacy tables. The metadata describes current coverage, but observed games end in 2022-23. Mapping uses only the physical SQLite evidence and marks absent canonical inputs unavailable.

## Observed coverage

- Game dates: `1946-11-01 00:00:00` through `2023-06-12 00:00:00`.
- Season start years: `1946` through `2022` (77 distinct years).
- Raw season types: `All Star` (65), `All-Star` (63), `Playoffs` (3,842), `Pre Season` (1,536), `Regular Season` (60,192).
- No player game box-score, player-season aggregate, advanced, or award table exists in the physical bundle.

## Table inventory

No `dim_*`, `fact_*`, `agg_*`, or `analytics_*` tables were discovered.

| Physical table | Rows | Candidate key | Duplicate groups |
|---|---:|---|---:|
| `common_player_info` | 3,632 | `person_id` | 0 |
| `draft_combine_stats` | 1,633 | `season+player_id` | 0 |
| `draft_history` | 8,257 | `person_id+season+draft_type` | 0 |
| `game` | 65,698 | `game_id` | 56 |
| `game_info` | 58,053 | `game_id` | 40 |
| `game_summary` | 58,110 | `game_id` | 85 |
| `inactive_players` | 110,191 | `game_id+player_id` | 7 |
| `line_score` | 58,053 | `game_id` | 40 |
| `officials` | 70,971 | `game_id+official_id` | 30 |
| `other_stats` | 28,271 | `game_id` | 10 |
| `play_by_play` | 13,592,899 | `game_id+eventnum` | 7360 |
| `player` | 4,815 | `id` | 0 |
| `team` | 30 | `id` | 0 |
| `team_details` | 27 | `team_id` | 0 |
| `team_history` | 50 | `team_id+city+nickname+year_founded+year_active_till` | 0 |
| `team_info_common` | 0 | `team_id+season_year` | 0 |

Duplicate groups are source observations, not silently deduplicated facts. The 56 duplicate `game_id` groups are All-Star rows published under both `All Star` and `All-Star`; `play_by_play` has 7,360 duplicate `(game_id, eventnum)` groups.

## Important team-game metric observations

These are first/last *non-null observations*, not claims of reliable official coverage. Sparse anomalous pre-introduction values exist, so reliability must be set explicitly in `metric_coverage` rather than inferred from `MIN(season)`.

| Source field | First observed | Last observed | Nulls | Null rate |
|---|---:|---:|---:|---:|
| `pts_home` | 1946 | 2022 | 0 | 0.00% |
| `fgm_home` | 1946 | 2022 | 13 | 0.02% |
| `fga_home` | 1946 | 2022 | 15,447 | 23.51% |
| `fg3m_home` | 1947 | 2022 | 13,218 | 20.12% |
| `fg3a_home` | 1947 | 2022 | 18,683 | 28.44% |
| `ftm_home` | 1946 | 2022 | 16 | 0.02% |
| `fta_home` | 1946 | 2022 | 3,004 | 4.57% |
| `oreb_home` | 1973 | 2022 | 18,936 | 28.82% |
| `dreb_home` | 1973 | 2022 | 18,999 | 28.92% |
| `reb_home` | 1950 | 2022 | 15,729 | 23.94% |
| `ast_home` | 1947 | 2022 | 15,805 | 24.06% |
| `stl_home` | 1973 | 2022 | 18,849 | 28.69% |
| `blk_home` | 1973 | 2022 | 18,626 | 28.35% |
| `tov_home` | 1977 | 2022 | 18,684 | 28.44% |
| `pf_home` | 1946 | 2022 | 2,856 | 4.35% |
| `plus_minus_home` | 1946 | 2022 | 0 | 0.00% |

## Physical schemas

### `common_player_info`

| Column | Declared type | Nullable | Source PK ordinal |
|---|---|---:|---:|
| `person_id` | `TEXT` | yes | 0 |
| `first_name` | `TEXT` | yes | 0 |
| `last_name` | `TEXT` | yes | 0 |
| `display_first_last` | `TEXT` | yes | 0 |
| `display_last_comma_first` | `TEXT` | yes | 0 |
| `display_fi_last` | `TEXT` | yes | 0 |
| `player_slug` | `TEXT` | yes | 0 |
| `birthdate` | `TIMESTAMP` | yes | 0 |
| `school` | `TEXT` | yes | 0 |
| `country` | `TEXT` | yes | 0 |
| `last_affiliation` | `TEXT` | yes | 0 |
| `height` | `TEXT` | yes | 0 |
| `weight` | `TEXT` | yes | 0 |
| `season_exp` | `REAL` | yes | 0 |
| `jersey` | `TEXT` | yes | 0 |
| `position` | `TEXT` | yes | 0 |
| `rosterstatus` | `TEXT` | yes | 0 |
| `games_played_current_season_flag` | `TEXT` | yes | 0 |
| `team_id` | `INTEGER` | yes | 0 |
| `team_name` | `TEXT` | yes | 0 |
| `team_abbreviation` | `TEXT` | yes | 0 |
| `team_code` | `TEXT` | yes | 0 |
| `team_city` | `TEXT` | yes | 0 |
| `playercode` | `TEXT` | yes | 0 |
| `from_year` | `REAL` | yes | 0 |
| `to_year` | `REAL` | yes | 0 |
| `dleague_flag` | `TEXT` | yes | 0 |
| `nba_flag` | `TEXT` | yes | 0 |
| `games_played_flag` | `TEXT` | yes | 0 |
| `draft_year` | `TEXT` | yes | 0 |
| `draft_round` | `TEXT` | yes | 0 |
| `draft_number` | `TEXT` | yes | 0 |
| `greatest_75_flag` | `TEXT` | yes | 0 |

### `draft_combine_stats`

| Column | Declared type | Nullable | Source PK ordinal |
|---|---|---:|---:|
| `season` | `TEXT` | yes | 0 |
| `player_id` | `TEXT` | yes | 0 |
| `first_name` | `TEXT` | yes | 0 |
| `last_name` | `TEXT` | yes | 0 |
| `player_name` | `TEXT` | yes | 0 |
| `position` | `TEXT` | yes | 0 |
| `height_wo_shoes` | `REAL` | yes | 0 |
| `height_wo_shoes_ft_in` | `TEXT` | yes | 0 |
| `height_w_shoes` | `REAL` | yes | 0 |
| `height_w_shoes_ft_in` | `TEXT` | yes | 0 |
| `weight` | `TEXT` | yes | 0 |
| `wingspan` | `REAL` | yes | 0 |
| `wingspan_ft_in` | `TEXT` | yes | 0 |
| `standing_reach` | `REAL` | yes | 0 |
| `standing_reach_ft_in` | `TEXT` | yes | 0 |
| `body_fat_pct` | `TEXT` | yes | 0 |
| `hand_length` | `TEXT` | yes | 0 |
| `hand_width` | `TEXT` | yes | 0 |
| `standing_vertical_leap` | `REAL` | yes | 0 |
| `max_vertical_leap` | `REAL` | yes | 0 |
| `lane_agility_time` | `REAL` | yes | 0 |
| `modified_lane_agility_time` | `REAL` | yes | 0 |
| `three_quarter_sprint` | `REAL` | yes | 0 |
| `bench_press` | `REAL` | yes | 0 |
| `spot_fifteen_corner_left` | `TEXT` | yes | 0 |
| `spot_fifteen_break_left` | `TEXT` | yes | 0 |
| `spot_fifteen_top_key` | `TEXT` | yes | 0 |
| `spot_fifteen_break_right` | `TEXT` | yes | 0 |
| `spot_fifteen_corner_right` | `TEXT` | yes | 0 |
| `spot_college_corner_left` | `TEXT` | yes | 0 |
| `spot_college_break_left` | `TEXT` | yes | 0 |
| `spot_college_top_key` | `TEXT` | yes | 0 |
| `spot_college_break_right` | `TEXT` | yes | 0 |
| `spot_college_corner_right` | `TEXT` | yes | 0 |
| `spot_nba_corner_left` | `TEXT` | yes | 0 |
| `spot_nba_break_left` | `TEXT` | yes | 0 |
| `spot_nba_top_key` | `TEXT` | yes | 0 |
| `spot_nba_break_right` | `TEXT` | yes | 0 |
| `spot_nba_corner_right` | `TEXT` | yes | 0 |
| `off_drib_fifteen_break_left` | `TEXT` | yes | 0 |
| `off_drib_fifteen_top_key` | `TEXT` | yes | 0 |
| `off_drib_fifteen_break_right` | `TEXT` | yes | 0 |
| `off_drib_college_break_left` | `TEXT` | yes | 0 |
| `off_drib_college_top_key` | `TEXT` | yes | 0 |
| `off_drib_college_break_right` | `TEXT` | yes | 0 |
| `on_move_fifteen` | `TEXT` | yes | 0 |
| `on_move_college` | `TEXT` | yes | 0 |

### `draft_history`

| Column | Declared type | Nullable | Source PK ordinal |
|---|---|---:|---:|
| `person_id` | `TEXT` | yes | 0 |
| `player_name` | `TEXT` | yes | 0 |
| `season` | `TEXT` | yes | 0 |
| `round_number` | `INTEGER` | yes | 0 |
| `round_pick` | `INTEGER` | yes | 0 |
| `overall_pick` | `INTEGER` | yes | 0 |
| `draft_type` | `TEXT` | yes | 0 |
| `team_id` | `TEXT` | yes | 0 |
| `team_city` | `TEXT` | yes | 0 |
| `team_name` | `TEXT` | yes | 0 |
| `team_abbreviation` | `TEXT` | yes | 0 |
| `organization` | `TEXT` | yes | 0 |
| `organization_type` | `TEXT` | yes | 0 |
| `player_profile_flag` | `TEXT` | yes | 0 |

### `game`

| Column | Declared type | Nullable | Source PK ordinal |
|---|---|---:|---:|
| `season_id` | `TEXT` | yes | 0 |
| `team_id_home` | `TEXT` | yes | 0 |
| `team_abbreviation_home` | `TEXT` | yes | 0 |
| `team_name_home` | `TEXT` | yes | 0 |
| `game_id` | `TEXT` | yes | 0 |
| `game_date` | `TIMESTAMP` | yes | 0 |
| `matchup_home` | `TEXT` | yes | 0 |
| `wl_home` | `TEXT` | yes | 0 |
| `min` | `INTEGER` | yes | 0 |
| `fgm_home` | `REAL` | yes | 0 |
| `fga_home` | `REAL` | yes | 0 |
| `fg_pct_home` | `REAL` | yes | 0 |
| `fg3m_home` | `REAL` | yes | 0 |
| `fg3a_home` | `REAL` | yes | 0 |
| `fg3_pct_home` | `REAL` | yes | 0 |
| `ftm_home` | `REAL` | yes | 0 |
| `fta_home` | `REAL` | yes | 0 |
| `ft_pct_home` | `REAL` | yes | 0 |
| `oreb_home` | `REAL` | yes | 0 |
| `dreb_home` | `REAL` | yes | 0 |
| `reb_home` | `REAL` | yes | 0 |
| `ast_home` | `REAL` | yes | 0 |
| `stl_home` | `REAL` | yes | 0 |
| `blk_home` | `REAL` | yes | 0 |
| `tov_home` | `REAL` | yes | 0 |
| `pf_home` | `REAL` | yes | 0 |
| `pts_home` | `REAL` | yes | 0 |
| `plus_minus_home` | `INTEGER` | yes | 0 |
| `video_available_home` | `INTEGER` | yes | 0 |
| `team_id_away` | `TEXT` | yes | 0 |
| `team_abbreviation_away` | `TEXT` | yes | 0 |
| `team_name_away` | `TEXT` | yes | 0 |
| `matchup_away` | `TEXT` | yes | 0 |
| `wl_away` | `TEXT` | yes | 0 |
| `fgm_away` | `REAL` | yes | 0 |
| `fga_away` | `REAL` | yes | 0 |
| `fg_pct_away` | `REAL` | yes | 0 |
| `fg3m_away` | `REAL` | yes | 0 |
| `fg3a_away` | `REAL` | yes | 0 |
| `fg3_pct_away` | `REAL` | yes | 0 |
| `ftm_away` | `REAL` | yes | 0 |
| `fta_away` | `REAL` | yes | 0 |
| `ft_pct_away` | `REAL` | yes | 0 |
| `oreb_away` | `REAL` | yes | 0 |
| `dreb_away` | `REAL` | yes | 0 |
| `reb_away` | `REAL` | yes | 0 |
| `ast_away` | `REAL` | yes | 0 |
| `stl_away` | `REAL` | yes | 0 |
| `blk_away` | `REAL` | yes | 0 |
| `tov_away` | `REAL` | yes | 0 |
| `pf_away` | `REAL` | yes | 0 |
| `pts_away` | `REAL` | yes | 0 |
| `plus_minus_away` | `INTEGER` | yes | 0 |
| `video_available_away` | `INTEGER` | yes | 0 |
| `season_type` | `TEXT` | yes | 0 |

### `game_info`

| Column | Declared type | Nullable | Source PK ordinal |
|---|---|---:|---:|
| `game_id` | `TEXT` | yes | 0 |
| `game_date` | `TIMESTAMP` | yes | 0 |
| `attendance` | `INTEGER` | yes | 0 |
| `game_time` | `TEXT` | yes | 0 |

### `game_summary`

| Column | Declared type | Nullable | Source PK ordinal |
|---|---|---:|---:|
| `game_date_est` | `TIMESTAMP` | yes | 0 |
| `game_sequence` | `INTEGER` | yes | 0 |
| `game_id` | `TEXT` | yes | 0 |
| `game_status_id` | `INTEGER` | yes | 0 |
| `game_status_text` | `TEXT` | yes | 0 |
| `gamecode` | `TEXT` | yes | 0 |
| `home_team_id` | `TEXT` | yes | 0 |
| `visitor_team_id` | `TEXT` | yes | 0 |
| `season` | `TEXT` | yes | 0 |
| `live_period` | `INTEGER` | yes | 0 |
| `live_pc_time` | `TEXT` | yes | 0 |
| `natl_tv_broadcaster_abbreviation` | `TEXT` | yes | 0 |
| `live_period_time_bcast` | `TEXT` | yes | 0 |
| `wh_status` | `INTEGER` | yes | 0 |

### `inactive_players`

| Column | Declared type | Nullable | Source PK ordinal |
|---|---|---:|---:|
| `game_id` | `TEXT` | yes | 0 |
| `player_id` | `TEXT` | yes | 0 |
| `first_name` | `TEXT` | yes | 0 |
| `last_name` | `TEXT` | yes | 0 |
| `jersey_num` | `TEXT` | yes | 0 |
| `team_id` | `TEXT` | yes | 0 |
| `team_city` | `TEXT` | yes | 0 |
| `team_name` | `TEXT` | yes | 0 |
| `team_abbreviation` | `TEXT` | yes | 0 |

### `line_score`

| Column | Declared type | Nullable | Source PK ordinal |
|---|---|---:|---:|
| `game_date_est` | `TIMESTAMP` | yes | 0 |
| `game_sequence` | `INTEGER` | yes | 0 |
| `game_id` | `TEXT` | yes | 0 |
| `team_id_home` | `TEXT` | yes | 0 |
| `team_abbreviation_home` | `TEXT` | yes | 0 |
| `team_city_name_home` | `TEXT` | yes | 0 |
| `team_nickname_home` | `TEXT` | yes | 0 |
| `team_wins_losses_home` | `TEXT` | yes | 0 |
| `pts_qtr1_home` | `TEXT` | yes | 0 |
| `pts_qtr2_home` | `TEXT` | yes | 0 |
| `pts_qtr3_home` | `TEXT` | yes | 0 |
| `pts_qtr4_home` | `TEXT` | yes | 0 |
| `pts_ot1_home` | `INTEGER` | yes | 0 |
| `pts_ot2_home` | `INTEGER` | yes | 0 |
| `pts_ot3_home` | `INTEGER` | yes | 0 |
| `pts_ot4_home` | `INTEGER` | yes | 0 |
| `pts_ot5_home` | `INTEGER` | yes | 0 |
| `pts_ot6_home` | `INTEGER` | yes | 0 |
| `pts_ot7_home` | `INTEGER` | yes | 0 |
| `pts_ot8_home` | `INTEGER` | yes | 0 |
| `pts_ot9_home` | `INTEGER` | yes | 0 |
| `pts_ot10_home` | `INTEGER` | yes | 0 |
| `pts_home` | `REAL` | yes | 0 |
| `team_id_away` | `TEXT` | yes | 0 |
| `team_abbreviation_away` | `TEXT` | yes | 0 |
| `team_city_name_away` | `TEXT` | yes | 0 |
| `team_nickname_away` | `TEXT` | yes | 0 |
| `team_wins_losses_away` | `TEXT` | yes | 0 |
| `pts_qtr1_away` | `INTEGER` | yes | 0 |
| `pts_qtr2_away` | `TEXT` | yes | 0 |
| `pts_qtr3_away` | `TEXT` | yes | 0 |
| `pts_qtr4_away` | `INTEGER` | yes | 0 |
| `pts_ot1_away` | `INTEGER` | yes | 0 |
| `pts_ot2_away` | `INTEGER` | yes | 0 |
| `pts_ot3_away` | `INTEGER` | yes | 0 |
| `pts_ot4_away` | `INTEGER` | yes | 0 |
| `pts_ot5_away` | `INTEGER` | yes | 0 |
| `pts_ot6_away` | `INTEGER` | yes | 0 |
| `pts_ot7_away` | `INTEGER` | yes | 0 |
| `pts_ot8_away` | `INTEGER` | yes | 0 |
| `pts_ot9_away` | `INTEGER` | yes | 0 |
| `pts_ot10_away` | `INTEGER` | yes | 0 |
| `pts_away` | `REAL` | yes | 0 |

### `officials`

| Column | Declared type | Nullable | Source PK ordinal |
|---|---|---:|---:|
| `game_id` | `TEXT` | yes | 0 |
| `official_id` | `TEXT` | yes | 0 |
| `first_name` | `TEXT` | yes | 0 |
| `last_name` | `TEXT` | yes | 0 |
| `jersey_num` | `TEXT` | yes | 0 |

### `other_stats`

| Column | Declared type | Nullable | Source PK ordinal |
|---|---|---:|---:|
| `game_id` | `TEXT` | yes | 0 |
| `league_id` | `TEXT` | yes | 0 |
| `team_id_home` | `TEXT` | yes | 0 |
| `team_abbreviation_home` | `TEXT` | yes | 0 |
| `team_city_home` | `TEXT` | yes | 0 |
| `pts_paint_home` | `INTEGER` | yes | 0 |
| `pts_2nd_chance_home` | `INTEGER` | yes | 0 |
| `pts_fb_home` | `INTEGER` | yes | 0 |
| `largest_lead_home` | `INTEGER` | yes | 0 |
| `lead_changes` | `INTEGER` | yes | 0 |
| `times_tied` | `INTEGER` | yes | 0 |
| `team_turnovers_home` | `INTEGER` | yes | 0 |
| `total_turnovers_home` | `INTEGER` | yes | 0 |
| `team_rebounds_home` | `INTEGER` | yes | 0 |
| `pts_off_to_home` | `INTEGER` | yes | 0 |
| `team_id_away` | `TEXT` | yes | 0 |
| `team_abbreviation_away` | `TEXT` | yes | 0 |
| `team_city_away` | `TEXT` | yes | 0 |
| `pts_paint_away` | `INTEGER` | yes | 0 |
| `pts_2nd_chance_away` | `INTEGER` | yes | 0 |
| `pts_fb_away` | `INTEGER` | yes | 0 |
| `largest_lead_away` | `INTEGER` | yes | 0 |
| `team_turnovers_away` | `INTEGER` | yes | 0 |
| `total_turnovers_away` | `INTEGER` | yes | 0 |
| `team_rebounds_away` | `INTEGER` | yes | 0 |
| `pts_off_to_away` | `INTEGER` | yes | 0 |

### `play_by_play`

| Column | Declared type | Nullable | Source PK ordinal |
|---|---|---:|---:|
| `game_id` | `TEXT` | yes | 0 |
| `eventnum` | `INTEGER` | yes | 0 |
| `eventmsgtype` | `INTEGER` | yes | 0 |
| `eventmsgactiontype` | `INTEGER` | yes | 0 |
| `period` | `INTEGER` | yes | 0 |
| `wctimestring` | `TEXT` | yes | 0 |
| `pctimestring` | `TEXT` | yes | 0 |
| `homedescription` | `TEXT` | yes | 0 |
| `neutraldescription` | `TEXT` | yes | 0 |
| `visitordescription` | `TEXT` | yes | 0 |
| `score` | `TEXT` | yes | 0 |
| `scoremargin` | `TEXT` | yes | 0 |
| `person1type` | `REAL` | yes | 0 |
| `player1_id` | `TEXT` | yes | 0 |
| `player1_name` | `TEXT` | yes | 0 |
| `player1_team_id` | `TEXT` | yes | 0 |
| `player1_team_city` | `TEXT` | yes | 0 |
| `player1_team_nickname` | `TEXT` | yes | 0 |
| `player1_team_abbreviation` | `TEXT` | yes | 0 |
| `person2type` | `REAL` | yes | 0 |
| `player2_id` | `TEXT` | yes | 0 |
| `player2_name` | `TEXT` | yes | 0 |
| `player2_team_id` | `TEXT` | yes | 0 |
| `player2_team_city` | `TEXT` | yes | 0 |
| `player2_team_nickname` | `TEXT` | yes | 0 |
| `player2_team_abbreviation` | `TEXT` | yes | 0 |
| `person3type` | `REAL` | yes | 0 |
| `player3_id` | `TEXT` | yes | 0 |
| `player3_name` | `TEXT` | yes | 0 |
| `player3_team_id` | `TEXT` | yes | 0 |
| `player3_team_city` | `TEXT` | yes | 0 |
| `player3_team_nickname` | `TEXT` | yes | 0 |
| `player3_team_abbreviation` | `TEXT` | yes | 0 |
| `video_available_flag` | `TEXT` | yes | 0 |

### `player`

| Column | Declared type | Nullable | Source PK ordinal |
|---|---|---:|---:|
| `id` | `TEXT` | yes | 0 |
| `full_name` | `TEXT` | yes | 0 |
| `first_name` | `TEXT` | yes | 0 |
| `last_name` | `TEXT` | yes | 0 |
| `is_active` | `INTEGER` | yes | 0 |

### `team`

| Column | Declared type | Nullable | Source PK ordinal |
|---|---|---:|---:|
| `id` | `TEXT` | yes | 0 |
| `full_name` | `TEXT` | yes | 0 |
| `abbreviation` | `TEXT` | yes | 0 |
| `nickname` | `TEXT` | yes | 0 |
| `city` | `TEXT` | yes | 0 |
| `state` | `TEXT` | yes | 0 |
| `year_founded` | `REAL` | yes | 0 |

### `team_details`

| Column | Declared type | Nullable | Source PK ordinal |
|---|---|---:|---:|
| `team_id` | `TEXT` | yes | 0 |
| `abbreviation` | `TEXT` | yes | 0 |
| `nickname` | `TEXT` | yes | 0 |
| `yearfounded` | `REAL` | yes | 0 |
| `city` | `TEXT` | yes | 0 |
| `arena` | `TEXT` | yes | 0 |
| `arenacapacity` | `REAL` | yes | 0 |
| `owner` | `TEXT` | yes | 0 |
| `generalmanager` | `TEXT` | yes | 0 |
| `headcoach` | `TEXT` | yes | 0 |
| `dleagueaffiliation` | `TEXT` | yes | 0 |
| `facebook` | `TEXT` | yes | 0 |
| `instagram` | `TEXT` | yes | 0 |
| `twitter` | `TEXT` | yes | 0 |

### `team_history`

| Column | Declared type | Nullable | Source PK ordinal |
|---|---|---:|---:|
| `team_id` | `TEXT` | yes | 0 |
| `city` | `TEXT` | yes | 0 |
| `nickname` | `TEXT` | yes | 0 |
| `year_founded` | `INTEGER` | yes | 0 |
| `year_active_till` | `INTEGER` | yes | 0 |

### `team_info_common`

| Column | Declared type | Nullable | Source PK ordinal |
|---|---|---:|---:|
| `team_id` | `TEXT` | yes | 0 |
| `season_year` | `TEXT` | yes | 0 |
| `team_city` | `TEXT` | yes | 0 |
| `team_name` | `TEXT` | yes | 0 |
| `team_abbreviation` | `TEXT` | yes | 0 |
| `team_conference` | `TEXT` | yes | 0 |
| `team_division` | `TEXT` | yes | 0 |
| `team_code` | `TEXT` | yes | 0 |
| `team_slug` | `TEXT` | yes | 0 |
| `w` | `INTEGER` | yes | 0 |
| `l` | `INTEGER` | yes | 0 |
| `pct` | `REAL` | yes | 0 |
| `conf_rank` | `INTEGER` | yes | 0 |
| `div_rank` | `INTEGER` | yes | 0 |
| `min_year` | `INTEGER` | yes | 0 |
| `max_year` | `INTEGER` | yes | 0 |
| `league_id` | `TEXT` | yes | 0 |
| `season_id` | `TEXT` | yes | 0 |
| `pts_rank` | `INTEGER` | yes | 0 |
| `pts_pg` | `REAL` | yes | 0 |
| `reb_rank` | `INTEGER` | yes | 0 |
| `reb_pg` | `REAL` | yes | 0 |
| `ast_rank` | `INTEGER` | yes | 0 |
| `ast_pg` | `REAL` | yes | 0 |
| `opp_pts_rank` | `INTEGER` | yes | 0 |
| `opp_pts_pg` | `REAL` | yes | 0 |

## Reproduction

```bash
.venv/bin/python pipelines/ingest/audit_nbadb.py \
  --data-dir data/bronze/nbadb \
  --kaggle-version 238 \
  --retrieved-at 2026-08-19T16:52:59Z
```

SQLite SHA-256: `65b6412234d2d8817678d04f7cd2548aec82fec02b6c5b86679cade7572c21c7`.
